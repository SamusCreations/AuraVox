# Código de terceros

- `qwen_tts/`: paquete de inferencia de Qwen3-TTS (Alibaba Qwen, licencia
  Apache-2.0), copiado tal cual del nodo qwen3-tts-comfyui (la versión adaptada a transformers 5). Se usa SOLO desde
  `app/voice/qwen_worker.py`, que corre en un Python aparte con `torch`
  (ver `qwen_tts.python` en `config/voice_settings.yaml`).

  Cambio propio (marcado `[assistant]`): en
  `core/models/modeling_qwen3_tts.py`, el sub-modelo de códigos usa un
  bucle de muestreo directo (`_fast_predict`) en vez de `generate()` de
  Hugging Face por cada cuadro de audio. `QWEN_TTS_FAST=0` vuelve al
  original.
