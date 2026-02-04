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
  --images-dir cache/captcha_synth --providers qwen3_vl_flash,qwen3_vl_plus,baidu --max 40 --sleep 0.05

python3 scripts/benchmark_captcha_recognizers.py \
  --images-dir cache/captcha_synth --providers gemini --max 40 --sleep 0.05
```

## Results

### Provider: `qwen3_vl_flash`
- ok: 40, fail: 0
- latency (s): avg 0.809, median 0.779, p90 1.295, min 0.437, max 1.867
- accuracy: exact 0.650, char 0.850 (labeled=40)

### Provider: `qwen3_vl_plus`
- ok: 40, fail: 0
- latency (s): avg 1.131, median 0.907, p90 1.923, min 0.648, max 3.939
- accuracy: exact 0.700, char 0.863 (labeled=40)

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

## Analysis
- `qwen3_vl_flash` is much faster than `gemini` and notably more accurate than `baidu` on this synthetic set.
- `qwen3_vl_plus` improves accuracy slightly over flash but is slower; flash is a better speed/accuracy tradeoff for time-sensitive runs.
- `baidu` remains the fastest but lowest-accuracy option here.
- `gemini` is the most accurate among those tested, but much slower with very high tail latency (p90 ~7s). It fits better as a fallback than as the primary recognizer.
