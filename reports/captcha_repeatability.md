# Captcha Repeatability Benchmark

Date: 2026-02-04

## Setup
- Script: `scripts/benchmark_repeatability.py`
- Images: 20 synthetic samples (`cache/captcha_synth`)
- Repeats per image: 5
- Sleep between attempts: 0.05s
- Provider: `qwen3-vl-flash`
- Label source: filename suffix, normalized to `[A-Z0-9]`

Command:
```bash
python3 scripts/benchmark_repeatability.py \
  --images-dir cache/captcha_synth --providers qwen3-vl-flash --max 20 --repeats 5 --sleep 0.05
```

## Results
- attempts: 100, ok: 100, fail: 0
- latency (s): avg 0.597, median 0.558, p90 0.844, min 0.400, max 1.067
- accuracy (first): exact 0.600, char 0.825 (labeled=20)
- accuracy (best-of-5): exact 0.650, char 0.863
- gain: exact +0.050, char +0.038
- any-success rate: 1.000
- avg attempts to first success: 1.00

## Interpretation
- Repeating the **same image** improves exact-match by ~5pp and char accuracy by ~3.8pp.
- This improvement is modest relative to the 5x cost in time/requests.
- For speed-critical flows, it’s likely **not worth repeating the same image**; better to refresh the captcha and retry.
