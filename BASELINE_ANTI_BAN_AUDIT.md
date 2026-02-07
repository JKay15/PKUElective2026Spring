# PKUElective Baseline Anti-Ban / Stability Audit (baseline-antiban)

This document is the "source of truth" for what we treat as baseline (pre-Codex) behaviors that are likely relevant to:

- avoiding server-side anti-bot escalation (to the extent we can infer from code + observed prompts)
- maintaining stable sessions (avoid relogin storms)
- keeping request footprint conservative (avoid unnecessary endpoints / bursts)

We cannot reliably test "ban thresholds" offline. Therefore we lock down **baseline behaviors as an upper bound** and use regression tests to ensure the current version is not more aggressive by default.

## 1. Baseline Version定位

- Baseline git commit/tag: `baseline-antiban`
- Baseline scope: `autoelective/**/*.py` (and config defaults)

How to regenerate the audit report (offline, deterministic):

```bash
python scripts/audit_baseline_antiban.py --baseline baseline-antiban
```

Default outputs:

- `cache/audit/baseline_antiban_audit.json`
- Markdown summary printed to stdout

## 2. 基线反封号/稳态相关实现全清单（按类别）

### 2.1 指纹形态类（UA / headers / referer / cookie / random QS）

- UA set per session (do not randomize per-loop)
- Baseline default headers on both IAAA and Elective clients
- SupplyCancel referer: `HelpController`
- Action endpoints referer: `SupplyCancel`
- SSO login carries a dummy Cookie `JSESSIONID=JSESSIONID` (placeholder; runtime shape is `<52 chars>!<digits>`, avoids 101)
- Random query parameters to reduce cache and match browser behavior (`_rand`, `Rand`)

### 2.2 频率与请求足迹类（refresh / jitter / endpoint budget / pool）

- Refresh sleep uses jitter: `refresh_interval +/- refresh_interval*random_deviation`
- No-availability rounds touch only list pages (`SupplyCancel` / `supplement.jsp`)
- Availability burst only: `DrawServlet` -> `validate.do` -> `electSupplement.do`
- Requests are distributed across a bounded elective client pool

### 2.3 会话与登录类（cookie persist / max_life / relogin floor）

- Hook exceptions may stop `requests.Session.send()` before cookies are extracted; baseline manually `persist_cookies` on exceptions
- Session expiry management (`elective_client_max_life`)
- `login_loop_interval` ensures relogin attempts are not too frequent

### 2.4 并发与线程类（避免额外会话占用）

- Baseline is effectively 2-loop model: IAAA login loop + elective loop
- No background captcha traffic by default

### 2.5 异常与恢复类（分类准确，避免“误判导致请求变多”）

- `CaughtCheatingError` treated as critical
- `NotInOperationTimeError` is **non-failure** and should trigger backoff, not html-parse failure
- HTML parse failures trigger controlled recovery (dump, retry, cooldown/reset), not tight loops

### 2.6 日志与数据安全类（避免 token/cookie 泄露）

- Request dump tooling exists but must remain OFF by default
- Dump paths must stay under gitignored directories
- Fixtures must be sanitized before being promoted to tracked `tests/fixtures/`
- A tracked-file secret scan blocks `token/sida/xh/JSESSIONID` leakage

## 3. 基线与当前实现对照表（每条：基线证据、当前证据、状态、是否优化、冲突点）

| 类别 | 条目 | 基线证据 | 当前证据 | 状态 | 优化 | 冲突点/备注 |
|---|---|---|---|---|---|---|
| 指纹 | UA per session | `baseline-antiban:autoelective/loop.py` | `autoelective/loop.py` | inherited | no | 不要每轮随机 UA（更可疑） |
| 指纹 | IAAA default headers | `baseline-antiban:autoelective/iaaa.py` | `autoelective/iaaa.py` | inherited | no | `tests/offline/test_request_fingerprint_baseline_offline.py` |
| 指纹 | Elective default headers | `baseline-antiban:autoelective/elective.py` | `autoelective/elective.py` | inherited | no | 同上 |
| 指纹 | Referer(SupplyCancel=Help) | `baseline-antiban:autoelective/elective.py` | `autoelective/elective.py` | inherited | no | 同上 |
| 指纹 | Referer(Action=SupplyCancel) | `baseline-antiban:autoelective/elective.py` | `autoelective/elective.py` | inherited | no | 同上 |
| 指纹 | Dummy JSESSIONID on SSO | `baseline-antiban:autoelective/elective.py::sso_login` | `autoelective/elective.py::sso_login` | inherited | no | 同上 |
| 指纹 | Random QS (`_rand`/`Rand`) | `baseline-antiban:autoelective/elective.py` | `autoelective/elective.py` | inherited | no | 兼容/缓存 |
| 频率 | Refresh jitter | `baseline-antiban:autoelective/loop.py::_get_refresh_interval` | `autoelective/loop.py::_get_refresh_interval` | inherited | no | `tests/offline/test_refresh_jitter_offline.py` |
| 频率 | Idle budget (no Draw/Validate/Elect) | `baseline-antiban:autoelective/loop.py` | `autoelective/loop.py` | inherited | no | `tests/offline/test_request_budget_offline.py` |
| 会话 | persist_cookies on hook exceptions | `baseline-antiban:autoelective/client.py::persist_cookies` | `autoelective/client.py::persist_cookies` | inherited | no | 防止会话莫名过期 |
| 恢复 | NotInOperation treated as non-failure | `baseline-antiban:autoelective/hook.py` | `autoelective/loop.py` | inherited | yes | 当前增加动态长睡，更保守 |
| 安全 | Debug dump default OFF | `baseline-antiban:autoelective/hook.py` | `autoelective/hook.py` | inherited | no | `tests/offline/test_debug_dump_safety_offline.py` |
| 安全 | Tracked secret scan | n/a | `tests/offline/test_fixture_secret_scan_offline.py` | added | yes | 防止 fixture/doc 泄露 |
| 新增 | Captcha degrade->monitor-only | n/a | `autoelective/loop.py` | added | yes | `tests/offline/test_captcha_chain_policy_offline.py` |
| 新增 | Captcha probe thread | n/a | `autoelective/loop.py` | added (OFF) | yes | 必须 OFF by default；共享 pool |
| 新增 | Token bucket rate limit | n/a | `autoelective/rate_limit.py` | added (OFF) | yes | Burst 不应被误配拖慢 |
| 新增 | OFFLINE circuit breaker | n/a | `autoelective/loop.py` | added | yes | 更保守，断网降低请求 |

## 4. 冲突矩阵（新增特性 vs 基线约束）

| 新特性 | 默认状态 | 潜在冲突 | 约束/测试 |
|---|---:|---|---|
| captcha probe thread | OFF | 增加 Draw+Validate 背景请求 | `tests/offline/test_probe_isolation_offline.py`, `tests/offline/test_request_budget_offline.py` |
| rate limit token bucket | OFF | 误配导致 burst 变慢 | `tests/offline/test_rate_limit_integration_offline.py` |
| not-in-operation dynamic long sleep | ON | 无（更保守） | `tests/offline/test_not_in_operation_backoff_offline.py` |
| client pool reset/cooldown | ON | 阈值不当导致 relogin 变多 | heavy soak tests + budget tests |
| captcha degrade monitor-only | ON | 可用名额时会“只通知不提交” | `tests/offline/test_captcha_chain_policy_offline.py` |

## 5. 结论与行动项（持续更新）

Action items are driven by `scripts/audit_baseline_antiban.py` output:

1. Any "missing baseline behavior" is a P0 fix.
2. Any "added behavior" must be justified as more conservative, or gated by config default OFF.
3. Any feature that can increase background traffic must have:
   - default OFF
   - strict budget tests
   - heavy soak tests (explicitly enabled) for concurrency/reset paths
