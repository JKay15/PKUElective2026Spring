# Phase 1（抽签期）上线后 Runbook

适用场景：补退选时间表进入**第一阶段（抽签/非峰值）**，但教学网选课 UI 已经与“抢课阶段”一致。目标是在不冒险提高频率/不误触选课的前提下，尽快完成“真实 HTML + 验证码链路”的采样、回放、评估与回归测试补强。

## 核心原则（别踩坑）

1. **用临时 config 跑测试**：尽量不改动正式 `config.ini`。用 `main.py -c config.phase1.ini`、脚本 `-c config.phase1.ini`。
2. **只抓取/只验证，不提交选课**：优先使用“只读”脚本（抓页面、Draw+Validate）。避免触发 `electSupplement`（会真的提交选课）。
3. **低频优先**：抽签期时间充足，`--sleep` 设大一些（0.5–2s），不要试图提速。
4. **任何产物默认落在 `cache/`**：`cache/` 已被 `.gitignore` 忽略；不要把 raw 登录态/隐私数据提交进 git。
5. **脱敏再入库**：要把 HTML 变成 fixture/mock 时，只用 `--sanitize` 产物（或再二次检查）。

## 一键前置：全量离线回归

```bash
PY=python3
$PY -m unittest -q
```

预期：`OK (skipped=1)` 或类似。若失败，先修复再做线上采样（否则你不知道是“线上变了”还是“本地坏了”）。

## Step 1：抓取真实 HTML/JSON（生成可回放 fixtures）

用途：把真实页面结构沉淀成离线 fixture，后续学期改版时能第一时间在 CI/本地复现解析崩溃。

```bash
PY=python3
$PY scripts/capture_live_fixtures.py --sanitize --pages 3 --draw-count 5 --sleep 1.0
```

输出目录：
- `cache/live_fixtures/raw/`：原始响应（只用于本地排查，**不要提交**）
- `cache/live_fixtures/sanitized/`：脱敏响应（用于转成 tests fixture/mock）

如果你只想更新“时间表/帮助页”的 datagrid（用于 not-in-operation 动态退避），可以用：
```bash
$PY scripts/capture_live_fixtures.py --sanitize --help-only --sleep 1.0
```

当场做两件检查：
1. 打开 `cache/live_fixtures/sanitized/*helpcontroller*.html`，确认 datagrid 结构和列名是否变化。
2. 打开 `cache/live_fixtures/sanitized/*supplycancel*.html`，确认 `datagrid` 表头是否仍含 `课程名/班号/开课单位/限数/已选/补选` 这些列（顺序可以变，但名字最好别变）。

## Step 2：线上验证码真实评估（Draw + 识别 + Validate）

用途：不用“人工标注 ground truth”，直接用服务器 `Validate()` 作为判定（通过=识别正确）。这比合成验证码更接近真实。

```bash
PY=python3
$PY scripts/benchmark_captcha_validate_accuracy.py --providers baidu,qwen3-vl-flash,qwen3-vl-plus --samples 30 --sleep 0.5
```

观察指标（决定“抢课阶段默认链条”）：
- `validate_pass_rate`：通过率（核心）
- `total`：端到端耗时（Draw+识别+Validate）
- `p90/p95/max`：长尾，决定你“偶尔卡死一次”的风险

建议做两轮：
1. `--sleep 0.5` 跑一轮看稳定性
2. `--sleep 1.0` 再跑一轮确认长尾是否更健康（网络/服务端抖动时很常见）

## Step 3：测 H（Draw+Validate 的网络 RTT），用于 adaptive 冷启动

说明：`H` 是“只算网络/服务端”的时间（Draw+Validate），不含识别耗时。adaptive 打分里会用到它，冷启动填一个接近真实的 `adaptive_h_init` 可以减少误差。

```bash
PY=python3
$PY scripts/benchmark_captcha_http_rtt.py --samples 30 --sleep 0.2
```

把输出里的 `H_median` 或 `H_p90` 写到 `config.ini`（或 `config.phase1.ini`）：
- 偏保守：用 `H_p90`
- 偏激进：用 `H_median`

注意：这一步不会拖慢正式运行。代码里只会在需要时更新 EWMA；而“是否 not-in-operation”的时间表抓取只在触发 `NotInOperationTimeError` 时才会用到，并且有 TTL 缓存，不会每轮解析。

## Step 4：把真实 HTML 变成离线 fixture（阶段 1 当天最值钱的产物）

建议流程（手工/半自动都行）：
1. 从 `cache/live_fixtures/sanitized/` 里挑 2–6 个最关键页面：
   - `helpcontroller`（时间表 datagrid）
   - `supplycancel`（第一页）
   - `supplement_p2`（以及你常用的页，比如 p3）
2. 放到 `tests/fixtures/`（建议新建目录：`tests/fixtures/2026_phase1/`）。
3. 增加/更新离线测试：用这些 fixture 跑 `parser.get_courses_with_detail()`、`hook.check_elective_title()`、`hook.check_elective_tips()` 等，确保“学期小改版”第一时间在测试里炸出来。
4. 再跑一次全量测试：

```bash
PY=python3
$PY -m unittest -q
```

## 可选：观测 OFFLINE/探针/观测期（谨慎）

如果你想观察 `OFFLINE 冷却态 -> 探测失败 -> 探测成功 -> 观测期 -> 恢复` 的日志走势：
- 建议在抽签期用临时 config 把 `not-in-operation` 的长睡上限调小，避免“刚启动就睡 10–30 分钟”导致看不到日志。
- 但这会在“真的 not-in-operation”时增加请求频率，所以只建议阶段 1 用于观测验证，跑完换回正式 config。

我建议用 `config.phase1.ini` 做这些改动（示例）：
- `[offline] observe_seconds=30`
- `[runtime] report_interval=50`（每 50 轮打印一次 runtime 关键指标）
- `[captcha] probe_enabled=true` 且 `probe_share_pool=true`
- `[resilience] not_in_operation_dynamic_long_sleep_max=300`（只用于观测）

然后跑：
```bash
PY=python3
$PY main.py -c config.phase1.ini
```

风险提示：`main.py` 会按你的课程目标真的发起选课提交（遇到可选名额时）。如果你不希望任何自动提交，请不要跑这一步，改用上面的只读脚本。

## 阶段 1 当天的“最小闭环”

如果你只想在阶段 1 用最少时间完成最关键准备，按下面顺序做就够了：
1. `python -m unittest -q`
2. `scripts/capture_live_fixtures.py --sanitize`
3. `scripts/benchmark_captcha_validate_accuracy.py`
4. `scripts/benchmark_captcha_http_rtt.py` 并回填 `adaptive_h_init`
5. 用抓到的 sanitized HTML 补 2–3 个 fixture 测试，再跑 `python -m unittest -q`

