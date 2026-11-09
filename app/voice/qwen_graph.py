"""
Qwen3-TTS through CUDA graphs: replaces `talker.generate` (the frame loop)
with two captured graphs. Runs inside the Qwen worker process (see
qwen_worker.py).

Each audio frame needs one pass of the 28-layer talker and 15 passes of the
5-layer code predictor: about 500 tiny GPU kernels, each launched from
Python, so the CPU, not the GPU, sets the speed. torch.cuda.CUDAGraph records
a step once and replays all its kernels as a single launch. It needs static
memory addresses and shapes, hence StaticCache and explicit masks and
position ids instead of what the model builds per step. Prompt building,
the prefill (a normal forward pass) and the audio decode stay in the vendored
model; only the step-by-step loop changes.

Requires CUDA and transformers 5's StaticCache. Anything unexpected raises
from `install` and the worker falls back to torch.compile.
"""
import types

import torch


def _sample(logits, do_sample, top_k, top_p, temperature):
    """Next code from logits (batch, vocab): temperature, top-k, top-p."""
    if not do_sample:
        return logits.argmax(dim=-1, keepdim=True)
    logits = logits.float() / max(float(temperature or 1.0), 1e-5)
    if top_k and top_k > 0:
        kth = torch.topk(logits, min(int(top_k), logits.size(-1)), dim=-1).values[..., -1, None]
        logits = logits.masked_fill(logits < kth, float("-inf"))
    if top_p is not None and top_p < 1.0:
        sorted_logits, sorted_idx = torch.sort(logits, descending=True, dim=-1)
        cum = torch.softmax(sorted_logits, dim=-1).cumsum(dim=-1)
        remove = cum > top_p
        remove[..., 1:] = remove[..., :-1].clone()
        remove[..., 0] = False
        logits = logits.masked_fill(remove.scatter(-1, sorted_idx, remove), float("-inf"))
    return torch.multinomial(torch.softmax(logits, dim=-1), num_samples=1)


def _capture(body, warmups: int = 3):
    """Runs `body` a few times (lazy allocations, kernel caches), then records it."""
    for _ in range(warmups):
        body()
    torch.cuda.synchronize()
    graph = torch.cuda.CUDAGraph()
    stream = torch.cuda.Stream()
    stream.wait_stream(torch.cuda.current_stream())
    with torch.cuda.stream(stream):
        body()
        torch.cuda.synchronize()
        with torch.cuda.graph(graph):
            body()
    torch.cuda.current_stream().wait_stream(stream)
    torch.cuda.synchronize()
    return graph


class _Predictor:
    """The 15 remaining codes of a frame, given the talker's hidden state and
    the first code. All of it (sampling included) is one graph: positions and
    shapes never change."""

    def __init__(self, talker, sampling: dict):
        from transformers import StaticCache

        self.net = talker.code_predictor
        self.first_embed = talker.get_input_embeddings()
        self.steps = talker.config.num_code_groups - 1
        self.sampling = sampling
        device, dtype = talker.device, talker.dtype
        hidden = talker.config.hidden_size
        self.hidden_buf = torch.zeros(1, 1, hidden, dtype=dtype, device=device)
        self.first_buf = torch.zeros(1, 1, dtype=torch.long, device=device)
        self.codes_out = torch.zeros(1, self.steps, dtype=torch.long, device=device)
        self.embed_out = torch.zeros(1, 1, hidden, dtype=dtype, device=device)
        length = self.steps + 2
        self.cache = StaticCache(config=self.net.model.config, max_cache_len=length)
        self.positions = torch.arange(length, device=device)
        # Bool 4D masks (query, keys): each position sees itself and the past.
        full = torch.tril(torch.ones(length, length, dtype=torch.bool, device=device))
        self.prefill_mask = full[:2].unsqueeze(0).unsqueeze(0).contiguous()
        self.step_masks = [full[i:i + 1].unsqueeze(0).unsqueeze(0).contiguous() for i in range(2, length)]
        self.graph = None

    def _masks(self, mask):
        # Layers look up their mask by attention type when given a dict.
        return {"full_attention": mask, "sliding_attention": mask}

    def body(self):
        self.cache.reset()
        last_embed = self.first_embed(self.first_buf)
        out = self.net.forward(
            inputs_embeds=torch.cat((self.hidden_buf, last_embed), dim=1), past_key_values=self.cache, use_cache=True,
            attention_mask=self._masks(self.prefill_mask), cache_position=self.positions[:2])
        tokens = []
        for i in range(self.steps):
            token = _sample(out.logits[:, -1, :], **self.sampling)
            tokens.append(token)
            if i == self.steps - 1:
                break
            out = self.net.forward(
                input_ids=token, past_key_values=self.cache, use_cache=True, generation_steps=out.generation_steps,
                attention_mask=self._masks(self.step_masks[i]), cache_position=self.positions[2 + i:3 + i])
        codes = torch.cat(tokens, dim=-1)
        self.codes_out.copy_(codes)
        embeds = self.net.get_input_embeddings()
        total = last_embed
        for i in range(self.steps):
            total = total + embeds[i](codes[..., i:i + 1])
        self.embed_out.copy_(total)

    def capture(self):
        self._init_cache()
        self.graph = _capture(self.body)

    def _init_cache(self):
        cfg = self.net.model.config
        heads = getattr(cfg, "num_key_value_heads", cfg.num_attention_heads)
        head_dim = getattr(cfg, "head_dim", cfg.hidden_size // cfg.num_attention_heads)
        dummy = torch.zeros(1, heads, 1, head_dim, dtype=self.hidden_buf.dtype, device=self.hidden_buf.device)
        for layer in self.cache.layers:
            if not layer.is_initialized:
                layer.lazy_initialization(dummy, dummy)

    def run(self, hidden, first):
        self.hidden_buf.copy_(hidden)
        self.first_buf.copy_(first)
        self.graph.replay()
        return self.codes_out, self.embed_out


class _TalkerStep:
    """One talker decode step, with a position that changes every frame: it
    lives in buffers that are written before each replay."""

    def __init__(self, talker, max_len: int):
        from transformers import StaticCache

        self.net = talker.model
        self.max_len = max_len
        device, dtype = talker.device, talker.dtype
        hidden = talker.config.hidden_size
        self.window = getattr(self.net.config, "sliding_window", None)
        self.in_buf = torch.zeros(1, 1, hidden, dtype=dtype, device=device)
        self.out_buf = torch.zeros(1, 1, hidden, dtype=dtype, device=device)
        self.cache = StaticCache(config=self.net.config, max_cache_len=max_len)
        self.cache_position = torch.zeros(1, dtype=torch.long, device=device)
        self.position_ids = torch.zeros(3, 1, 1, dtype=torch.long, device=device)
        self.mask = torch.zeros(1, 1, 1, max_len, dtype=torch.bool, device=device)
        self.graph = None

    def body(self):
        out = self.net(inputs_embeds=self.in_buf, attention_mask=self.mask, position_ids=self.position_ids,
                       past_key_values=self.cache, cache_position=self.cache_position, use_cache=True)
        self.out_buf.copy_(out.last_hidden_state)

    def _init_cache(self):
        cfg = self.net.config
        heads = getattr(cfg, "num_key_value_heads", cfg.num_attention_heads)
        head_dim = getattr(cfg, "head_dim", cfg.hidden_size // cfg.num_attention_heads)
        dummy = torch.zeros(1, heads, 1, head_dim, dtype=self.in_buf.dtype, device=self.in_buf.device)
        for layer in self.cache.layers:
            if not layer.is_initialized:
                layer.lazy_initialization(dummy, dummy)

    def _set_position(self, pos: int, delta: int):
        self.cache_position.fill_(pos)
        self.position_ids.fill_(pos + delta)
        self.mask.zero_()
        start = max(0, pos - self.window + 1) if self.window else 0
        self.mask[..., start:pos + 1] = True

    def capture(self):
        self._init_cache()
        self.cache.reset()
        self._set_position(50, 0)
        self.graph = _capture(self.body)
        self.cache.reset()

    def load_prefill(self, past) -> int:
        """Copies the prefill's dynamic cache into the static one."""
        self.cache.reset()
        length = 0
        for index, layer in enumerate(past.layers):
            length = layer.keys.shape[2]
            self.cache.layers[index].update(layer.keys, layer.values)
        return length

    def run(self, embeds, pos: int, delta: int):
        self.in_buf.copy_(embeds)
        self._set_position(pos, delta)
        self.graph.replay()
        return self.out_buf


class GraphGenerator:
    """Drop-in for `talker.generate` in Qwen3TTSForConditionalGeneration.generate."""

    def __init__(self, talker, max_seq_len: int, sampling: dict):
        self.talker = talker
        self.original = talker.generate
        self.max_seq_len = max_seq_len
        self.sampling = sampling
        self.predictor = _Predictor(talker, sampling)
        self.step = _TalkerStep(talker, max_seq_len)

    @torch.inference_mode()
    def capture(self):
        self.predictor.capture()
        self.step.capture()

    def _same_sampling(self, kw: dict) -> bool:
        s = self.sampling
        return (bool(kw.get("subtalker_dosample", True)) == s["do_sample"] and kw.get("subtalker_top_k", 50) == s["top_k"]
                and kw.get("subtalker_top_p", 1.0) == s["top_p"] and kw.get("subtalker_temperature", 0.9) == s["temperature"])

    @torch.inference_mode()
    def __call__(self, inputs_embeds, attention_mask, trailing_text_hidden, tts_pad_embed, **kw):
        # A batch or other sub-sampling values: the captured graphs don't apply.
        if inputs_embeds.shape[0] != 1 or not self._same_sampling(kw):
            return self.original(inputs_embeds=inputs_embeds, attention_mask=attention_mask,
                                 trailing_text_hidden=trailing_text_hidden, tts_pad_embed=tts_pad_embed, **kw)
        from transformers.cache_utils import DynamicCache

        talker = self.talker
        eos = kw["eos_token_id"]
        max_new = int(kw.get("max_new_tokens") or 2048)
        penalty = float(kw.get("repetition_penalty") or 1.0)
        sampling = {"do_sample": bool(kw.get("do_sample", True)), "top_k": kw.get("top_k", 50),
                    "top_p": kw.get("top_p", 1.0), "temperature": kw.get("temperature", 0.9)}
        suppress = torch.tensor(kw.get("suppress_tokens") or [], dtype=torch.long, device=inputs_embeds.device)

        length = inputs_embeds.shape[1]
        out = talker(inputs_embeds=inputs_embeds, attention_mask=attention_mask, past_key_values=DynamicCache(),
                     use_cache=True, cache_position=torch.arange(length, device=inputs_embeds.device),
                     trailing_text_hidden=trailing_text_hidden, tts_pad_embed=tts_pad_embed)
        max_new = min(max_new, self.max_seq_len - length)
        if max_new <= 0:
            raise RuntimeError(f"prompt too long for the static cache ({length} tokens)")
        self.step.load_prefill(out.past_key_values)
        logits = out.logits[:, -1, :].float()
        hidden = out.past_hidden
        delta = int(talker.rope_deltas.reshape(-1)[0])
        placeholder = torch.zeros(1, 1, 1, device=inputs_embeds.device)
        frames, seen = [], []
        for step in range(max_new):
            if penalty != 1.0 and seen:
                ids = torch.tensor(seen, device=logits.device).unique()
                score = logits[:, ids]
                logits[:, ids] = torch.where(score < 0, score * penalty, score / penalty)
            if suppress.numel():
                logits[:, suppress] = float("-inf")
            first = _sample(logits, **sampling)
            code = int(first)
            seen.append(code)
            codes, embed_sum = self.predictor.run(hidden, first)
            frames.append(torch.cat((first, codes.clone()), dim=-1))
            if code == eos:
                break
            text = trailing_text_hidden[:, step].unsqueeze(1) if step < trailing_text_hidden.shape[1] else tts_pad_embed
            hidden = self.step.run(embed_sum + text, length + step, delta)
            logits = talker.codec_head(hidden)[:, -1, :].float()
        # What Qwen3TTSForConditionalGeneration.generate reads: codes in
        # [-1] of each item, and a hidden state nobody downstream uses.
        items = [((placeholder,), frame) for frame in frames] + [((placeholder,), None)]
        return types.SimpleNamespace(hidden_states=items)


def install(model, max_seq_len: int = 1536) -> GraphGenerator:
    """Captures both graphs and replaces `talker.generate` on the loaded
    Qwen3TTSModel. Raises on anything unexpected (nothing is replaced then)."""
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA graphs need CUDA")
    from transformers import StaticCache  # noqa: F401 — fails early on old transformers

    talker = model.model.talker
    defaults = model.generate_defaults or {}
    sampling = {"do_sample": bool(defaults.get("subtalker_dosample", True)), "top_k": defaults.get("subtalker_top_k", 50),
                "top_p": defaults.get("subtalker_top_p", 1.0), "temperature": defaults.get("subtalker_temperature", 0.9)}
    generator = GraphGenerator(talker, max_seq_len, sampling)
    generator.capture()
    talker.generate = generator
    return generator
