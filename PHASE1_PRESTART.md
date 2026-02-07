# Phase 1 前（抽签 UI 开放前）Prestart Checklist

适用场景：补退选时间表还没进入“可操作阶段”，或刚进入阶段一但你不想冒险跑主循环。目标是把“上线前必踩坑”变成可重复、可回归、可一键执行的流程，尽量把风险与不确定性都前置消化。

## 硬约束（必须遵守）

1. **不运行主循环做真实选课提交**：阶段一前的“真实测试”默认只做只读采样（抓 HTML、Draw+Validate、RTT），不触发 `electSupplement`。
2. **不提频、不加并发**：任何测试都不应默认开启会增加后台请求的开关（例如 probe），更不要提高刷新频率。
3. **重测试显式开启**：长时间 soak / 故障注入 / 极端并发只在 `AUTOELECTIVE_HEAVY_TESTS=1` 时运行。
4. **不允许敏感信息进入 git tracked 文件**：fixture / 文档里出现真实 `token/sida/xh/JSESSIONID` 必须视为 P0。

## 统一变量约定（复制就能跑）

在项目根目录执行：

```bash
PY=python3
CFG=config.phase1.ini
export AUTOELECTIVE_CONFIG_INI="$CFG"
```

说明：
- 用 `AUTOELECTIVE_CONFIG_INI` 强制本进程使用临时 config（避免单例配置被过早初始化）。
- 建议用临时 config 跑所有阶段一前的测试，避免误改正式 `config.ini`。

## Step 1：准备临时配置 `config.phase1.ini`

推荐直接复制你可用的 `config.ini`（最省事，课程/互斥/延迟配置不会漏项）：

```bash
cp config.ini "$CFG"
```

如果你还没有可用 `config.ini`：

```bash
cp config.sample.ini "$CFG"
```

必须确认至少填好（否则脚本会失败）：
- `[user] student_id / password / dual_degree / identity`
- 你计划使用的识别器密钥（不提交真实密钥）：
  - `baidu`: `[captcha] baidu_api_key / baidu_secret_key`
  - `qwen*`: `[captcha] dashscope_api_key`
  - `gemini`: `[captcha] gemini_api_key`

## Step 2：配置预检（必跑，静态检查）

这是纯静态检查：**不联网、不实例化 OCR**，用于防止误配置导致线上直接炸。

```bash
$PY scripts/preflight_config.py -c "$CFG"
echo "exit=$?"
```

预期：
- `exit=0`：通过（可能会打印 WARN，但默认不阻塞）
- `exit=2`：有 ERROR，先修配置再继续

如果你希望把 WARN 也当失败（更严格）：

```bash
$PY scripts/preflight_config.py -c "$CFG" --strict
echo "exit=$?"
```

预期：
- `exit=0`：无 ERROR/WARN
- `exit=1`：只有 WARN
- `exit=2`：有 ERROR

## Step 3：全量离线回归（必跑）

```bash
$PY -m unittest -q
```

预期：`OK`（heavy tests 默认 skip，不会分钟级）。

## Step 4：基线反封号审计回归（必跑）

目的：确认当前版本没有“更激进”的请求足迹，并且没有破坏基线的反封号 envelope。

```bash
$PY scripts/audit_baseline_antiban.py --baseline baseline-antiban
```

预期：
- 生成/更新 `cache/audit/` 下的审计产物（默认在 `.gitignore` 内）
- 输出对照表中，新增行为必须是“更保守”或“默认关闭”的特性

## Step 5（可选）：重测试（soak/fault/probe/reset）显式开启

只在你明确需要时跑（会更慢）：

```bash
AUTOELECTIVE_HEAVY_TESTS=1 SOAK_SECONDS=180 $PY -m unittest -q
```

如果你只想跑其中一套（避免每次都跑满），用 `AUTOELECTIVE_HEAVY_SUITE` 精确选择：

```bash
AUTOELECTIVE_HEAVY_TESTS=1 AUTOELECTIVE_HEAVY_SUITE=concurrency SOAK_SECONDS=180 $PY -m unittest -q
AUTOELECTIVE_HEAVY_TESTS=1 AUTOELECTIVE_HEAVY_SUITE=fault_probe_reset SOAK_SECONDS=180 $PY -m unittest -q
```

预期：仍然 `OK`。如果出现 flake，要先修被测代码或降低并发窗口的随机性，不要“改测试迎合实现”。

## Step 6：线上只读“真实测试”（不跑主循环）

### 6.0 只读 rehearsal（推荐，最小流量）

默认只会：登录 + 抓 `HelpController`，不触发 `electSupplement`，且把输出写入 `cache/rehearsal/`。

```bash
$PY scripts/rehearsal_readonly.py -c "$CFG"
echo "exit=$?"
```

### 6.1 抓真实 HTML fixture（脱敏）

```bash
$PY scripts/capture_live_fixtures.py -c "$CFG" --sanitize --pages 3 --draw-count 5 --sleep 1.0
```

产物：
- `cache/live_fixtures/raw/`：原始响应（只用于本地排查，**不要提交**）
- `cache/live_fixtures/sanitized/`：脱敏响应（可用于 promote 成 tests fixture）

如果当前还没到可操作阶段，只抓时间表：

```bash
$PY scripts/capture_live_fixtures.py -c "$CFG" --sanitize --help-only --sleep 1.0
```

### 6.2 验证码链路评估（Draw + 识别 + Validate，不 elect）

```bash
$PY scripts/benchmark_captcha_validate_accuracy.py -c "$CFG" --providers baidu,qwen3-vl-flash,qwen3-vl-plus --samples 30 --sleep 0.5
```

### 6.3 RTT 评估（用于 adaptive 冷启动）

```bash
$PY scripts/benchmark_captcha_http_rtt.py -c "$CFG" --samples 30 --sleep 0.2
```

把输出的 `H_median` 或 `H_p90` 回填到 `config.phase1.ini` 的 `[captcha] adaptive_h_init`（越接近真实越好，能降低冷启动误差）。

## Step 7（可选）：一键完成“抓取 + 提升 + 脱敏扫描 + 回归”

这个脚本会在 capture 前做一次 preflight，并对 promoted fixtures 做脱敏扫描。

```bash
$PY scripts/phase1_capture_replay.py -c "$CFG" --pages 3 --draw-count 5 --sleep 1.0 --strict
```

## 输出位置与安全

1. 所有运行期产物默认落在 `cache/`（已被 `.gitignore` 忽略）。
2. 任何要提交到 `tests/fixtures/` 的 HTML 必须来自 `--sanitize` 或二次脱敏，且必须通过 `python -m unittest -q` 里的 secret scan。
3. 提交前建议跑：

```bash
git status --porcelain
```

预期：不出现 `config.ini/config.phase1.ini/apikey.json/cache/` 之类敏感或本地文件的 staged 变更。
