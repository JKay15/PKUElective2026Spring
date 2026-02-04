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
- latency (s): avg 0.255, median 0.242, p90 0.304, min 0.192, max 0.638
- sample outputs:
  - `synth_0000_TVG2.jpg` -> `3A1`
  - `synth_0001_S6WS.jpg` -> `S6WS`
  - `synth_0002_XO71.jpg` -> `o71`
  - `synth_0003_1U7D.jpg` -> `1V1D`
  - `synth_0004_71FG.jpg` -> `71FG`

### Mode: `accurate_basic`
- ok: 40, fail: 0
- latency (s): avg 0.288, median 0.285, p90 0.326, min 0.218, max 0.455
- sample outputs:
  - `synth_0000_TVG2.jpg` -> `TvG2`
  - `synth_0001_S6WS.jpg` -> `sMos`
  - `synth_0002_XO71.jpg` -> `4071`
  - `synth_0003_1U7D.jpg` -> `1U1D`
  - `synth_0004_71FG.jpg` -> `7AG`

## Observations
- Both modes succeeded on all 40 synthetic samples.
- `general_basic` was faster on average (~0.255s vs ~0.288s).
- Recognition accuracy on these synthetic samples is mixed for both modes (sample outputs show errors), which is expected because the generator adds distortions/noise.

## Recommendation (based on speed)
- Use `general_basic` as the default for faster response.
- Keep `accurate_basic` as a fallback for repeated validation failures.
