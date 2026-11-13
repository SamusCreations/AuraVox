"""
Downloads the Qwen3-TTS models (Base for cloned voices, CustomVoice for the
predefined speakers) from Hugging Face into cache/qwen-tts/<name>/, on
demand and with progress (see hf_hub.Job). Files go to
<name>.part/ first and the folder is renamed when everything is there, so a
half-finished download never looks like a usable model.

    python -m app.voice.qwen_download Qwen3-TTS-12Hz-0.6B-CustomVoice
"""
import os
import shutil
import sys

from app import paths
from app.core import hf_hub

REPO_OWNER = "Qwen"


def model_path(name: str) -> str:
    return os.path.join(paths.QWEN_TTS_MODELS_DIR, name)


def is_downloaded(name: str) -> bool:
    folder = model_path(name)
    return (os.path.isfile(os.path.join(folder, "config.json"))
            and os.path.isfile(os.path.join(folder, "model.safetensors"))
            and os.path.isfile(os.path.join(folder, "speech_tokenizer", "model.safetensors")))


def download(name: str, job=None) -> str:
    """Downloads the whole repo Qwen/<name>. `job` (hf_hub.Job) gets
    completed/total bytes and can cancel. Returns the model folder."""
    final = model_path(name)
    if is_downloaded(name):
        return final
    repo = f"{REPO_OWNER}/{name}"
    files = [f for f in hf_hub.repo_files(repo)["files"] if not f["path"].startswith(".")]
    total = sum(f["size"] or 0 for f in files)
    part = final + ".part"
    os.makedirs(part, exist_ok=True)
    done_before = 0
    if job:
        job.update(total=total, completed=0)
    for f in files:
        dest = os.path.join(part, *f["path"].split("/"))
        if os.path.isfile(dest) and (not f["size"] or os.path.getsize(dest) == f["size"]):
            done_before += f["size"] or 0  # already there from an interrupted download
            continue
        base = done_before

        def progress(done, _total, base=base):
            if job:
                job.update(completed=base + done, file=f["path"])
            elif done % (64 << 20) < (1 << 20):
                print(f"  {f['path']}: {done >> 20} MiB", flush=True)

        hf_hub.download(repo, f["path"], dest, progress=progress, cancel=job.cancelled if job else None)
        done_before += f["size"] or os.path.getsize(dest)
    if os.path.isdir(final):
        shutil.rmtree(final, ignore_errors=True)
    os.replace(part, final)
    if job:
        job.update(completed=total)
    return final


if __name__ == "__main__":
    sys.path.insert(0, paths.ROOT)
    print(download(sys.argv[1]))
