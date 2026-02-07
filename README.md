# PKUElective2026Spring (Hardened / 2026+)

![Bark Notification](./assets/bark-notification.jpeg)

北大选课辅助工具（强化版）：在经典 `PKUElective2022Spring`/`PKUAutoElective` 系列的基础上，补齐了“上线前预检、只读演练、抽签期（Phase 1）Runbook、离线 fixtures 回放测试、验证码多识别器评估”这一整套可回归流程，并对稳态与错误恢复做了增强。

## 相比原版的主要改进

- **配置预检（静态、0联网）**：`main.py --preflight` / `scripts/preflight_config.py`，提前发现常见误配置（provider/密钥/刷新间隔/探针开关等）。
- **只读演练（Read-only rehearsal）**：`scripts/rehearsal_readonly.py`，用于在不触发真实选课提交的前提下验证登录、抓页、验证码链路等。
- **抽签期（Phase 1）一套可复制 Runbook**：`PHASE1_PRESTART.md` + `PHASE1_RUNBOOK.md`，把“抓取真实 HTML + 脱敏 + 提升为 fixture + 回归测试”流程固化。
- **离线回放测试与 fixtures 工具链**：支持抓取/脱敏/提升 fixtures，并通过 `unittest` 离线回归覆盖解析容错、退避策略、验证码策略等关键路径。
- **多验证码识别器 + 评估脚本**：Baidu / Qwen VL（DashScope）/ Gemini，可用 `validate.do` 做在线准确率评估与 RTT 基准测量。
- **更保守的稳态与恢复**：支持 not-in-operation 动态退避、会话重置冷却、离线断路器、线程守护重启等，减少“异常导致紧循环”的风险。
- **安全护栏**：`cache/`、`config.ini`、`apikey.json` 默认已在 `.gitignore`；并通过测试对 tracked fixtures 做敏感信息扫描，避免 token/cookie/student_id 泄露。

## 小白版教程（旧版入口，仍可参考）

参见 [Arthals' Docs](https://docs.arthals.ink/docs/pku-auto-elective)。

## 安装

> 运行环境：建议 Python 3.10+（优先 3.11/3.12）。

```bash
git clone https://github.com/JKay15/PKUElective2026Spring.git
cd PKUElective2026Spring
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 配置（必读）

首次使用请先复制 `config.sample.ini` 为 `config.ini`：

```bash
cp config.sample.ini config.ini
```

至少需要填写：

- `[user] student_id / password / dual_degree / identity`
- `[captcha] provider` 以及对应 provider 的 key（**不要提交真实密钥**）

如果你需要“临时配置文件”（推荐用于抽签期/线上采样），可以用：

```bash
cp config.ini config.phase1.ini
export AUTOELECTIVE_CONFIG_INI=config.phase1.ini
```

说明：`AUTOELECTIVE_CONFIG_INI` 会强制本进程使用指定配置，避免“模块过早 import 导致单例配置先初始化、-c 失效”的问题。

## 快速开始（主程序）

1) 先跑静态预检（不联网）：

```bash
python3 main.py --preflight
```

2) 启动主程序：

```bash
python3 main.py
```

可选：启动本地监控线程（默认 `127.0.0.1:7074`，具体见 `[monitor]`）：

```bash
python3 main.py -m
```

停止：`Ctrl + C`。

## 只读演练（强烈推荐先跑）

只读演练不会触发 `electSupplement`（即不会真实提交选课），用于确认“登录/抓页/验证码链路”在当前学期可用。

```bash
python3 scripts/rehearsal_readonly.py -c config.ini
```

默认输出在 `cache/rehearsal/<timestamp>/`（已被 `.gitignore` 忽略）。

## 抽签期（Phase 1）使用方法

抽签期建议按文档执行：

- `PHASE1_PRESTART.md`：上线前检查清单（预检 + 离线回归 + 基线审计 + 只读真实测试）
- `PHASE1_RUNBOOK.md`：抓取真实页面、脱敏、提升 fixture、回归测试与验证码评估

最常用的一条命令是“一键抓取 + 提升 + 脱敏扫描 + 回归”：

```bash
python3 scripts/phase1_capture_replay.py -c config.phase1.ini --pages 3 --draw-count 5 --sleep 1.0 --strict
```

## 验证码识别器与评估

支持 provider：`baidu` / `qwen3-vl-flash` / `qwen3-vl-plus` / `gemini` / `dummy`。

建议用“在线 Validate 通过率”做评估（更贴近真实），示例：

```bash
python3 scripts/benchmark_captcha_validate_accuracy.py \
  -c config.ini \
  --providers baidu,qwen3-vl-flash,qwen3-vl-plus \
  --samples 30 \
  --sleep 0.5
```

RTT 评估（用于 `adaptive_h_init` 冷启动）：

```bash
python3 scripts/benchmark_captcha_http_rtt.py -c config.ini --samples 30 --sleep 0.2
```

## Bark 通知（可选）

在 [Bark App](https://bark.day.app/)（仅 iOS）的示例请求中获得推送 Key（注意不是设置里的 Device Token），然后修改 `config.ini` 的 `[notification]`：

```ini
[notification]
disable_push=false
token=TOKEN
verbosity=1
minimum_interval=0
```

测试推送：

```bash
python3 scripts/test_bark_notify.py
```

## 测试（离线回归）

```bash
python3 -m unittest -q
```

重测试（soak / fault / concurrency）默认不会跑；只有显式设置才会启用：

```bash
AUTOELECTIVE_HEAVY_TESTS=1 SOAK_SECONDS=180 python3 -m unittest -q
```

## 安全与注意事项

- 请在遵守学校规定与系统规则的前提下使用；任何风险请自行评估与承担。
- 请勿提交包含真实账号/密钥/会话信息的文件：`config.ini`、`config.phase1.ini`、`apikey.json`、`cache/` 已默认加入 `.gitignore`，但发布到 GitHub 前仍建议复查 git 历史与 staged 变更。
- 本仓库包含“更保守请求足迹/稳态行为”的基线审计文档：`BASELINE_ANTI_BAN_AUDIT.md`（面向维护者）。

## 致谢

感谢 `PKUElective2022Spring`、`PKUAutoElective` 及相关 fork 的作者与贡献者（zhongxinghong / Mzhhh / KingOfDeBug / Totoro-Li 等）。本仓库的增强功能主要聚焦于可回归与稳态工程化。
