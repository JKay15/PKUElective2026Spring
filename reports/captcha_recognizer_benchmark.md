# Captcha Recognizer Benchmark (Synthetic Captcha-like Images)

Date: 2026-02-04

## Setup
- Generator: `scripts/generate_captcha_like.py`
- Benchmark: `scripts/benchmark_captcha_recognizers.py`
- Images: 40 synthetic captcha-like samples (`cache/captcha_synth`)
- Image size: 140x48
- Label source: filename suffix (e.g. `synth_0000_TVG2.jpg` -> `TVG2`)
- Normalization: keep `[A-Za-z0-9]` and uppercase before scoring
- Metrics:
  - `exact`: full-string match rate
  - `char`: per-position match rate with length mismatch penalty

Commands:
```bash
python3 scripts/benchmark_captcha_recognizers.py \
  --images-dir cache/captcha_synth --providers qwen3-vl-flash,qwen3-vl-flash-2026-01-22,qwen3-vl-plus,qwen3-vl-plus-2025-12-19,qwen-vl-max,qwen-vl-plus,qwen2.5-vl-32b-instruct,qwen2.5-vl-7b-instruct --max 40 --sleep 0.05

python3 scripts/benchmark_captcha_recognizers.py \
  --images-dir cache/captcha_synth --providers qwen-vl-ocr-2025-11-20,baidu --max 40 --sleep 0.05

python3 scripts/benchmark_captcha_recognizers.py \
  --images-dir cache/captcha_synth --providers baidu --max 40 --sleep 0.05
```

## Results

### Provider: `qwen3-vl-flash`
- ok: 40, fail: 0
- latency (s): avg 0.736, median 0.609, p90 1.263, min 0.430, max 1.690
- accuracy: exact 0.650, char 0.850 (labeled=40)

### Provider: `qwen3-vl-flash-2026-01-22`
- ok: 38, fail: 2
- latency (s): avg 0.691, median 0.362, p90 1.856, min 0.308, max 3.632
- accuracy: exact 0.579, char 0.842 (labeled=38)

### Provider: `qwen3-vl-plus`
- ok: 40, fail: 0
- latency (s): avg 1.209, median 0.957, p90 2.247, min 0.662, max 5.257
- accuracy: exact 0.725, char 0.869 (labeled=40)

### Provider: `qwen3-vl-plus-2025-12-19`
- ok: 40, fail: 0
- latency (s): avg 1.106, median 0.829, p90 1.875, min 0.600, max 3.907
- accuracy: exact 0.700, char 0.863 (labeled=40)

### Provider: `qwen-vl-max`
- ok: 40, fail: 0
- latency (s): avg 0.867, median 0.788, p90 1.266, min 0.613, max 1.418
- accuracy: exact 0.600, char 0.838 (labeled=40)

### Provider: `qwen-vl-plus`
- ok: 40, fail: 0
- latency (s): avg 0.480, median 0.447, p90 0.665, min 0.339, max 1.002
- accuracy: exact 0.525, char 0.836 (labeled=40)

### Provider: `qwen2.5-vl-32b-instruct`
- ok: 40, fail: 0
- latency (s): avg 0.804, median 0.800, p90 0.869, min 0.727, max 0.919
- accuracy: exact 0.550, char 0.744 (labeled=40)

### Provider: `qwen2.5-vl-7b-instruct`
- ok: 40, fail: 0
- latency (s): avg 0.516, median 0.510, p90 0.589, min 0.432, max 0.649
- accuracy: exact 0.400, char 0.561 (labeled=40)

### Provider: `qwen-vl-ocr-2025-11-20`
- ok: 40, fail: 0
- latency (s): avg 0.607, median 0.494, p90 0.900, min 0.405, max 2.918
- accuracy: exact 0.600, char 0.775 (labeled=40)

### Provider: `baidu`
Notes:
- This measures the repo's `baidu` recognizer as implemented in `autoelective/captcha/online.py` (currently `accurate_basic`).

- ok: 38, fail: 2
- latency (s): avg 0.286, median 0.280, p90 0.337, min 0.229, max 0.453
- accuracy: exact 0.421, char 0.704 (labeled=38)

### Provider: `gemini` (previous run)
- ok: 40, fail: 0
- latency (s): avg 3.076, median 2.350, p90 7.140, min 0.980, max 9.606
- accuracy: exact 0.650, char 0.881 (labeled=40)
- ok: 40, fail: 0
- latency (s): avg 0.809, median 0.779, p90 1.295, min 0.437, max 1.867
- accuracy: exact 0.650, char 0.850 (labeled=40)

## Analysis
- Best exact accuracy on this synthetic set: `qwen3-vl-plus` (0.725). It is slower than `qwen3-vl-flash` but still much faster than `gemini`.
- Best latency among Qwen models: `qwen-vl-plus` (~0.48s median) but with noticeably lower accuracy.
- `qwen-vl-ocr-2025-11-20` is faster than most Qwen-VL models but less accurate than `qwen3-vl-flash`/`qwen3-vl-plus`.
- `qwen3-vl-flash` is the best overall tradeoff for speed + accuracy.
- `baidu` remains the fastest overall but with the lowest accuracy of the set.
- `gemini` is the most accurate among non-Qwen in previous run, but much slower with high tail latency (p90 ~7s). It fits better as a fallback than as the primary recognizer.
