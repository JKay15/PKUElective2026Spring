# Phase 1（抽签期）上线后 Runbook

适用场景：补退选时间表进入**第一阶段（抽签/非峰值）**，但教学网选课 UI 已经与“抢课阶段”一致。目标是在不冒险提高频率/不误触选课的前提下，尽快完成“真实 HTML + 验证码链路”的采样、回放、评估与回归测试补强。

## 核心原则（别踩坑）

1. **用临时 config 跑测试**：尽量不改动正式 `config.ini`。用 `main.py -c config.phase1.ini`、脚本 `-c config.phase1.ini`。
2. **只抓取/只验证，不提交选课**：优先使用“只读”脚本（抓页面、Draw+Validate）。避免触发 `electSupplement`（会真的提交选课）。
3. **低频优先**：抽签期时间充足，`--sleep` 设大一些（0.5–2s），不要试图提速。
4. **任何产物默认落在 `cache/`**：`cache/` 已被 `.gitignore` 忽略；不要把 raw 登录态/隐私数据提交进 git。
5. **脱敏再入库**：要把 HTML 变成 fixture/mock 时，只用 `--sanitize` 产物（或再二次检查）。

## 变量约定（复制就能跑）

在项目根目录执行以下内容（建议直接整段复制）：

```bash
PY=python3
CFG=config.phase1.ini
export AUTOELECTIVE_CONFIG_INI="$CFG"
```

说明：
- `AUTOELECTIVE_CONFIG_INI` 会强制本进程使用指定 config（包括被脚本/模块“过早 import”触发的单例配置）。
- 仓库已将 `config.phase1.ini` 加入 `.gitignore`，避免误提交包含账号/密钥的文件。

## Step 0：准备 `config.phase1.ini`（最小歧义版）

推荐做法（最省事）：直接复制你可用的 `config.ini`，避免课程/互斥/延迟配置漏项。

```bash
cp config.ini "$CFG"
```

如果你还没有可用的 `config.ini`，用样例起步：

```bash
cp config.sample.ini "$CFG"
```

然后确保至少填好（否则脚本会直接报错）：
- `[user] student_id / password / dual_degree / identity`
- 你要测试的识别器密钥：
  - `baidu`: `[captcha] baidu_api_key / baidu_secret_key`
  - `qwen*`: `[captcha] dashscope_api_key`（可选填 `dashscope_base_url`）
  - `gemini`: `[captcha] gemini_api_key`

快速自检（确认 `config.phase1.ini` 能被读取）：

```bash
$PY -c "from autoelective.config import AutoElectiveConfig as C; c=C(); print('student_id=', c.iaaa_id, 'provider=', c.captcha_provider)"
```

## Step 0.5：全量离线回归（先确保本地没坏）

```bash
$PY -m unittest -q
```

预期：`OK (skipped=1)` 或类似。若失败，先修复再做线上采样（否则你不知道是“线上变了”还是“本地坏了”）。

## Step 1：抓取真实 HTML/JSON（生成可回放 fixtures）

用途：把真实页面结构沉淀成离线 fixture，后续学期改版时能第一时间在 CI/本地复现解析崩溃。

```bash
$PY scripts/capture_live_fixtures.py -c "$CFG" --sanitize --pages 3 --draw-count 5 --sleep 1.0
```

输出目录：
- `cache/live_fixtures/raw/`：原始响应（只用于本地排查，**不要提交**）
- `cache/live_fixtures/sanitized/`：脱敏响应（用于转成 tests fixture/mock）

如果你只想更新“时间表/帮助页”的 datagrid（用于 not-in-operation 动态退避），可以用：
```bash
$PY scripts/capture_live_fixtures.py -c "$CFG" --sanitize --help-only --sleep 1.0
```

当场做两件检查：
1. 打开 `cache/live_fixtures/sanitized/*helpcontroller*.html`，确认 datagrid 结构和列名是否变化。
2. 打开 `cache/live_fixtures/sanitized/*supplycancel*.html`，确认 `datagrid` 表头是否仍含 `课程名/班号/开课单位/限数/已选/补选` 这些列（顺序可以变，但名字最好别变）。

## Step 1.1：Fixture 覆盖清单（必须项 + 风险点）

建议至少准备以下 fixture（优先级从高到低）：

1. `helpcontroller.html`（时间表 datagrid）
- 风险点：列名/顺序/分页结构变动导致 `not-in-operation` 误判或退避策略异常。
- 对应测试：`tests/offline/test_phase1_fixtures_optional_offline.py::test_helpcontroller_fixture_optional`

2. `supplycancel.html`（补选列表首页）
- 风险点：表头变动、缺列、`onclick/href` 结构改变导致选课链接解析失败。
- 对应测试：
  - `tests/offline/test_phase1_fixtures_optional_offline.py::test_supplycancel_fixture_optional`
  - `tests/offline/test_parser_supplycancel_onclick_fallback_offline.py`

3. `supplement_p2.html`（补选列表非首页）
- 风险点：分页结构/参数变动导致 `get_supplement` 只能抓第一页。
- 对应测试：`tests/offline/test_supplement_page_retry_offline.py`

4. `electSupplement` 返回页（真实提交返回 HTML）
- 风险点：`tips/系统提示文本`变动导致失败原因分类/重试策略错误。
- 对应测试：`tests/offline/test_supply_cancel_safe_parse_success_offline.py` 等竞态/重试用例
 - 建议 fixture（示例）：`electsupplement_tips_quota.html` / `electsupplement_tips_failed.html` / `electsupplement_tips_timeout.html` / `electsupplement_tips_mutex.html` / `electsupplement_tips_success.html`
 - 对应测试：`tests/offline/test_phase1_electsupplement_tips_offline.py`

抓取后，先用 `promote_live_fixtures.py` 提升，再跑 `python -m unittest -q`，确认解析路径没有被新 HTML 打爆。

## Step 2：线上验证码真实评估（Draw + 识别 + Validate）

用途：不用“人工标注 ground truth”，直接用服务器 `Validate()` 作为判定（通过=识别正确）。这比合成验证码更接近真实。

```bash
$PY scripts/benchmark_captcha_validate_accuracy.py -c "$CFG" --providers baidu,qwen3-vl-flash,qwen3-vl-plus --samples 30 --sleep 0.5
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
$PY scripts/benchmark_captcha_http_rtt.py -c "$CFG" --samples 30 --sleep 0.2
```

把输出里的 `H_median` 或 `H_p90` 写到 `config.ini`（或 `config.phase1.ini`）：
- 偏保守：用 `H_p90`
- 偏激进：用 `H_median`

注意：这一步不会拖慢正式运行。代码里只会在需要时更新 EWMA；而“是否 not-in-operation”的时间表抓取只在触发 `NotInOperationTimeError` 时才会用到，并且有 TTL 缓存，不会每轮解析。

## Step 4：一键把 sanitized HTML “提升”为可提交的 fixture

目的：把 `cache/live_fixtures/sanitized/` 中“带时间戳的抓取文件”转换为稳定文件名，方便写测试和 code review。

```bash
$PY scripts/promote_live_fixtures.py \
  --src cache/live_fixtures/sanitized \
  --dst tests/fixtures/2026_phase1 \
  --names helpcontroller,supplycancel,supplement_p2 \
  --strict
```

产物：
- `tests/fixtures/2026_phase1/helpcontroller.html`
- `tests/fixtures/2026_phase1/supplycancel.html`
- `tests/fixtures/2026_phase1/supplement_p2.html`
- `tests/fixtures/2026_phase1/MANIFEST.json`（记录来源与时间戳）

可选：如果你希望直接覆盖旧 fixture（例如第二天又抓了一次），加 `--force`：

```bash
$PY scripts/promote_live_fixtures.py --src cache/live_fixtures/sanitized --dst tests/fixtures/2026_phase1 --names helpcontroller,supplycancel,supplement_p2 --strict --force
```

### Step 4.1：脱敏复查（避免把真实 token/sida/student_id 提交进 git）

推荐用 `rg -P` 做一次快速扫描（有命中就先别提交）：

```bash
rg -n -P "sida=(?!SIDA)[0-9a-fA-F]{32}|token=(?!TOKEN)\\S+|\\bxh=\\d{6,}" tests/fixtures/2026_phase1 || true
```

## Step 5：再跑一次全量离线回归（确认 fixture 没把解析搞炸）

```bash
$PY -m unittest -q
```

## 可选：一键完成“抓取 + 提升 + 脱敏扫描 + 回归”

如果你希望一条命令跑完核心流程（含两次 unittest），可以用：

```bash
$PY scripts/phase1_capture_replay.py -c "$CFG" --pages 3 --draw-count 5 --sleep 1.0 --strict
```

说明：
- 默认会跑两次 `unittest`（前后各一次）。
- 会自动对 `tests/fixtures/2026_phase1` 做脱敏扫描，发现疑似 token 会直接报错退出。
- 如需覆盖旧 fixture，加 `--force`。
- 如需跳过 unittest，加 `--skip-unittest`（不推荐）。

## Step 6（可选）：列出 electSupplement 链接（不提交，只用于观察）

用途：从你刚抓的 `supplycancel` fixture 里解析出 `electSupplement` 的 href，**默认只打印**，不发任何选课请求。

```bash
$PY scripts/list_electsupplement_hrefs.py \
  --fixture tests/fixtures/2026_phase1/supplycancel.html \
  --limit 10
```

如果你 **明确确认允许触发 electSupplement**（可能会提交选课），需要显式加双重确认：

```bash
$PY scripts/list_electsupplement_hrefs.py \
  --fixture tests/fixtures/2026_phase1/supplycancel.html \
  --config "$CFG" \
  --fetch \
  --confirm-elect \
  --limit 1 \
  --sleep 1.0
```

## Step 7（可选）：Bark 通知自检

```bash
$PY scripts/test_bark_notify.py -c "$CFG"
```

预期：手机收到 `[测试] This is a test.`，终端无异常。若没有收到，检查 `config.phase1.ini` 的 `[notification] token`。

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
$PY main.py -c "$CFG"
```

风险提示：`main.py` 会按你的课程目标真的发起选课提交（遇到可选名额时）。如果你不希望任何自动提交，请不要跑这一步，改用上面的只读脚本。

## 阶段 1 当天的“最小闭环”

如果你只想在阶段 1 用最少时间完成最关键准备，按下面顺序做就够了：
1. `python -m unittest -q`
2. `scripts/capture_live_fixtures.py -c "$CFG" --sanitize`
3. `scripts/benchmark_captcha_validate_accuracy.py -c "$CFG" ...`
4. `scripts/benchmark_captcha_http_rtt.py -c "$CFG" ...` 并回填 `adaptive_h_init`
5. `scripts/promote_live_fixtures.py ...` + `rg -P` 脱敏复查
6. `python -m unittest -q`

## 常见问题与处理（Phase 1 现场最常见）

1. `capture supplycancel failed: NotInOperationTimeError(...)`
- 含义：教学网还没开放补退选（或你不在该身份/阶段）。
- 处理：先跑 `--help-only` 抓时间表；等进入“UI 已开放的抽签阶段”再抓 `SupplyCancel`。

2. `benchmark_captcha_validate_accuracy.py` 里出现 `Not in operation time`
- 含义：`Validate()` 在当前阶段不可用（或你还没进入补退选 UI）。
- 处理：先用 Step 1 抓 `SupplyCancel` 确认页面可访问；必要时只先跑 Step 3（测 H）和抓 HTML。

3. 识别器报 `DashScope API key not configured / Baidu OCR keys not configured`
- 含义：`config.phase1.ini` 没填密钥。
- 处理：补齐 `[captcha] ...` 对应 key；再次运行 Step 2。

4. 识别器大量 429/503 或耗时长尾很大
- 含义：服务端限流/抖动（很常见）。
- 处理：把 `--sleep` 调大（例如 1.0–2.0），样本数减少但更贴近真实稳定性；并优先关注 `p90/p95/max`。

5. promoted fixture 里仍出现真实 `xh=学号` 或 32 位 `sida`
- 含义：脱敏规则遗漏或页面包含新的字段。
- 处理：不要提交；把命中的片段贴出来（只贴 sanitized 文件片段），我们补脱敏规则/或改 capture 脚本再抓一次。

6. `list_electsupplement_hrefs.py --fetch` 报错或卡住
- 含义：`electSupplement` 本质上是选课提交，可能被服务端拒绝或不在操作阶段。
- 处理：优先只做“打印链接”，不要 fetch；确需 fetch 时务必在抽签期低频验证，并严格 `--limit 1`。
