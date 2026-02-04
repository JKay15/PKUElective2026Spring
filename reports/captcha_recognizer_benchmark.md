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
  --images-dir cache/captcha_synth --providers gemini --max 40 --sleep 0.05

python3 scripts/benchmark_captcha_recognizers.py \
  --images-dir cache/captcha_synth --providers baidu --max 40 --sleep 0.05
```

## Results

### Provider: `gemini`
- ok: 40, fail: 0
- latency (s): avg 3.076, median 2.350, p90 7.140, min 0.980, max 9.606
- accuracy: exact 0.650, char 0.881 (labeled=40)

### Provider: `baidu`
Notes:
- This measures the repo's `baidu` recognizer as implemented in `autoelective/captcha/online.py` (currently `accurate_basic`).

- ok: 38, fail: 2
- latency (s): avg 0.286, median 0.289, p90 0.333, min 0.229, max 0.398
- accuracy: exact 0.421, char 0.704 (labeled=38)

## Analysis
- `gemini` is significantly more accurate on this synthetic set (+~23pp exact vs baidu), but much slower (~10x+ median latency) and has very large tail latency (p90 ~7s).
- For workflows where latency is the primary constraint, `gemini` is not suitable as the primary recognizer; it can still be useful as a fallback when correctness matters more than speed.

