# Baidu OCR Benchmark Report (Synthetic Captcha-like Images)

Date: 2026-02-04

## Setup
- Generator: `scripts/generate_captcha_like.py`
- Benchmark: `scripts/benchmark_baidu_ocr.py`
- Images: 40 synthetic captcha-like samples
- Image size: 140x48
- Text length: 4
- Sleep between requests: 0.05s
- Timeout: 10s

## Results

### Mode: `general_basic`
- ok: 40, fail: 0
- latency (s): avg 0.245, median 0.233, p90 0.300, min 0.177, max 0.529
- accuracy (label from filename, alnum+upper normalized): exact 0.400, char 0.659
- sample outputs:
  - `synth_0000_TVG2.jpg` -> `3A1`
  - `synth_0001_S6WS.jpg` -> `S6WS`
  - `synth_0002_XO71.jpg` -> `o71`
  - `synth_0003_1U7D.jpg` -> `1V1D`
  - `synth_0004_71FG.jpg` -> `71FG`

### Mode: `accurate_basic`
- ok: 40, fail: 0
- latency (s): avg 0.290, median 0.286, p90 0.337, min 0.240, max 0.395
- accuracy (label from filename, alnum+upper normalized): exact 0.425, char 0.644
- sample outputs:
  - `synth_0000_TVG2.jpg` -> `TvG2`
  - `synth_0001_S6WS.jpg` -> `sMos`
  - `synth_0002_XO71.jpg` -> `4071`
  - `synth_0003_1U7D.jpg` -> `1U1D`
  - `synth_0004_71FG.jpg` -> `7AG`

## Observations
- Both modes succeeded on all 40 synthetic samples.
- `general_basic` was faster on average (~0.245s vs ~0.290s).
- Exact-match accuracy is low for both modes (~40-42.5%), with per-character accuracy around ~0.64-0.66.
- Accuracy is measured by taking the ground-truth label from the filename, normalizing to `[A-Z0-9]`, and scoring exact match and per-position character match.
- Given these are synthetic and real captchas are likely harder, production accuracy could be worse.

## Recommendation (based on speed + accuracy)
- Use `general_basic` as the default for faster response.
- Do not rely on `accurate_basic` alone for meaningful accuracy gains; it is slightly slower and only marginally better on this synthetic set.
- If production success rate needs to be >80%, consider a dedicated captcha-recognition service or a human-in-the-loop fallback.
