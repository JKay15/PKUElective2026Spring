#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .captcha.targets import ALLOWED_CAPTCHA_PROVIDERS

_LEGACY_KEY_MIGRATIONS = {
    "openai_model": "model_name",
    "openai_api_key": "api_key",
    "openai_base_url": "base_url",
    "openai_timeout": "request_timeout",
    "openai_max_output_tokens": "max_output_tokens",
    "dashscope_api_key": "api_key",
    "dashscope_base_url": "base_url",
    "dashscope_timeout": "request_timeout",
    "dashscope_max_output_tokens": "max_output_tokens",
    "dashscope_model": "model_name",
    "dashscope_model_flash": "model_name",
    "dashscope_model_plus": "model_name",
    "dashscope_model_ocr": "model_name",
    "code_length": "code_length_min/code_length_max",
}


@dataclass(frozen=True)
class PreflightIssue:
    level: str  # "ERROR" | "WARN"
    code: str
    message: str
    key_path: Optional[str] = None


def _is_blank(s) -> bool:
    return s is None or str(s).strip() == ""


def _normalized_provider(name: str) -> str:
    n = (name or "").strip().lower()
    if not n:
        return "unknown"
    if n in ALLOWED_CAPTCHA_PROVIDERS:
        return n
    return "invalid"


def _required_key_paths(provider: str) -> list[str]:
    if provider == "baidu":
        return ["captcha.baidu_api_key", "captcha.baidu_secret_key"]
    if provider == "gemini":
        return ["captcha.gemini_api_key"]
    return []


def _get_key_value(config, key_path: str):
    # Keep this mapping explicit to avoid accidentally touching network-heavy code paths.
    if key_path == "captcha.baidu_api_key":
        return config.baidu_api_key
    if key_path == "captcha.baidu_secret_key":
        return config.baidu_secret_key
    if key_path == "captcha.gemini_api_key":
        return config.gemini_api_key
    if key_path == "captcha.api_key":
        return config.captcha_api_key
    if key_path == "captcha.base_url":
        return config.captcha_base_url
    if key_path == "captcha.model_name":
        return config.captcha_model_name
    raise KeyError(key_path)


def _has_openai_compat_key(config) -> bool:
    return not _is_blank(getattr(config, "captcha_api_key", None))


def _has_openai_model_target(config) -> bool:
    model_name = (getattr(config, "captcha_model_name", None) or "").strip()
    if model_name:
        return True
    try:
        models = list(getattr(config, "captcha_openai_models", None) or [])
    except Exception:
        models = []
    for m in models:
        if (m or "").strip():
            return True
    return False


def _openai_base_url(config) -> str:
    v = getattr(config, "captcha_base_url", None) or "https://dashscope.aliyuncs.com/compatible-mode/v1"
    return str(v).strip().lower()


def _is_local_base_url(base_url: str) -> bool:
    u = (base_url or "").strip().lower()
    return (
        u.startswith("http://127.0.0.1")
        or u.startswith("https://127.0.0.1")
        or u.startswith("http://localhost")
        or u.startswith("https://localhost")
        or u.startswith("http://0.0.0.0")
        or u.startswith("https://0.0.0.0")
    )


def run_preflight(config) -> list[PreflightIssue]:
    """
    Run static config validation. This MUST NOT:
    - perform any network request
    - instantiate captcha recognizers (which may talk to OCR vendors)
    """
    issues: list[PreflightIssue] = []

    def _add(level: str, code: str, message: str, key_path: str | None = None):
        issues.append(PreflightIssue(level=level, code=code, message=message, key_path=key_path))

    for old_key, new_key in _LEGACY_KEY_MIGRATIONS.items():
        try:
            v = config.get_optional("captcha", old_key, None)
        except Exception:
            v = None
        if v is not None:
            _add(
                "ERROR",
                "captcha_legacy_key_unsupported",
                "Unsupported legacy config key captcha.%s; migrate to captcha.%s."
                % (old_key, new_key),
                "captcha.%s" % old_key,
            )

    try:
        models = list(getattr(config, "captcha_openai_models", None) or [])
    except Exception as e:
        models = []
        _add(
            "ERROR",
            "captcha_openai_models_read_failed",
            f"Unable to read captcha.openai_models: {e}",
            "captcha.openai_models",
        )
    for m in models:
        if _is_blank(m):
            _add(
                "ERROR",
                "captcha_openai_models_invalid",
                "captcha.openai_models contains an empty model entry.",
                "captcha.openai_models",
            )
            break

    # [captcha] code length range
    try:
        v_min = config.captcha_code_length_min
        v_max = config.captcha_code_length_max
        if v_min > v_max:
            _add(
                "ERROR",
                "captcha_code_length_range_invalid",
                f"captcha.code_length_min ({v_min}) > captcha.code_length_max ({v_max})",
                key_path="captcha.code_length_min",
            )
    except Exception as e:
        _add("ERROR", "captcha_code_length_range_read_failed", f"Unable to read captcha code length range: {e}")

    # [client] refresh / deviation / pool size
    try:
        refresh = config.refresh_interval
        if refresh <= 0:
            _add("ERROR", "refresh_interval_invalid", f"client.refresh_interval must be > 0, got {refresh!r}", "client.refresh_interval")
        elif refresh < 1.0:
            _add("WARN", "refresh_interval_low", f"client.refresh_interval is {refresh}s (< 1.0s). This may be too aggressive.", "client.refresh_interval")
    except Exception as e:
        _add("ERROR", "refresh_interval_read_failed", f"Unable to read client.refresh_interval: {e}", "client.refresh_interval")

    try:
        dev = config.refresh_random_deviation
        if dev < 0:
            _add("ERROR", "random_deviation_invalid", f"client.random_deviation must be >= 0, got {dev!r}", "client.random_deviation")
    except Exception as e:
        _add("ERROR", "random_deviation_read_failed", f"Unable to read client.random_deviation: {e}", "client.random_deviation")

    try:
        pool = config.elective_client_pool_size
        if pool <= 0:
            _add(
                "ERROR",
                "elective_client_pool_size_invalid",
                f"client.elective_client_pool_size must be > 0, got {pool!r}",
                "client.elective_client_pool_size",
            )
    except Exception as e:
        _add(
            "ERROR",
            "elective_client_pool_size_read_failed",
            f"Unable to read client.elective_client_pool_size: {e}",
            "client.elective_client_pool_size",
        )

    # Provider + key requirements
    try:
        provider = (config.captcha_provider or "").strip().lower()
    except Exception as e:
        provider = ""
        _add("ERROR", "captcha_provider_read_failed", f"Unable to read captcha.provider: {e}", "captcha.provider")

    provider_norm = _normalized_provider(provider)
    if provider_norm == "invalid":
        _add(
            "ERROR",
            "captcha_provider_invalid",
            "Unsupported captcha.provider %r. Allowed providers: %s."
            % (provider, ", ".join(ALLOWED_CAPTCHA_PROVIDERS)),
            "captcha.provider",
        )

    if provider and provider_norm in ALLOWED_CAPTCHA_PROVIDERS:
        for kp in _required_key_paths(provider_norm):
            try:
                v = _get_key_value(config, kp)
            except Exception as e:
                _add("ERROR", "captcha_key_read_failed", f"Unable to read {kp}: {e}", kp)
                continue
            if _is_blank(v):
                _add("ERROR", "captcha_key_missing", f"Missing required credential for provider {provider!r}: {kp}", kp)
        if provider_norm == "openai":
            base_url = _openai_base_url(config)
            if _is_blank(base_url):
                _add(
                    "ERROR",
                    "captcha_key_missing",
                    "Missing required config for OpenAI-compatible provider: captcha.base_url",
                    "captcha.base_url",
                )
            if not _has_openai_model_target(config):
                _add(
                    "ERROR",
                    "captcha_key_missing",
                    "Missing required config when captcha.provider=openai: captcha.model_name or captcha.openai_models",
                    "captcha.model_name",
                )
            if not _has_openai_compat_key(config):
                if _is_local_base_url(base_url):
                    _add(
                        "WARN",
                        "captcha_openai_key_missing",
                        (
                            "captcha.api_key is empty. This is allowed for local/self-hosted endpoints without auth."
                        ),
                        "captcha.api_key",
                    )
                else:
                    _add(
                        "ERROR",
                        "captcha_key_missing",
                        (
                            "Missing required config for OpenAI-compatible provider: captcha.api_key."
                        ),
                        "captcha.api_key",
                    )

    # fallback providers: validate provider names + required keys.
    try:
        fallbacks = list(config.captcha_fallback_providers or [])
    except Exception as e:
        fallbacks = []
        _add("ERROR", "captcha_fallback_read_failed", f"Unable to read captcha.fallback_providers: {e}", "captcha.fallback_providers")

    for fp in fallbacks:
        fp = (fp or "").strip().lower()
        if not fp:
            continue
        fp_norm = _normalized_provider(fp)
        if fp_norm == "invalid":
            _add(
                "ERROR",
                "captcha_fallback_provider_invalid",
                "Unsupported captcha fallback provider %r. Allowed providers: %s."
                % (fp, ", ".join(ALLOWED_CAPTCHA_PROVIDERS)),
                "captcha.fallback_providers",
            )
            continue

        for kp in _required_key_paths(fp_norm):
            try:
                v = _get_key_value(config, kp)
            except Exception as e:
                _add("ERROR", "captcha_fallback_key_read_failed", f"Unable to read {kp} for fallback {fp!r}: {e}", kp)
                continue
            if _is_blank(v):
                _add(
                    "ERROR",
                    "captcha_fallback_key_missing",
                    f"Missing required credential for fallback {fp!r}: {kp}",
                    kp,
                )
        if fp_norm == "openai":
            base_url = _openai_base_url(config)
            if _is_blank(base_url):
                _add(
                    "ERROR",
                    "captcha_fallback_key_missing",
                    "Missing required config for OpenAI-compatible fallback 'openai': captcha.base_url",
                    "captcha.base_url",
                )
            if not _has_openai_model_target(config):
                _add(
                    "ERROR",
                    "captcha_fallback_key_missing",
                    "Missing required config for fallback 'openai': captcha.model_name or captcha.openai_models",
                    "captcha.model_name",
                )
            if not _has_openai_compat_key(config):
                if _is_local_base_url(base_url):
                    _add(
                        "WARN",
                        "captcha_fallback_openai_key_missing",
                        (
                            f"captcha.api_key is empty for fallback {fp!r}. "
                            "This is allowed for local/self-hosted endpoints without auth."
                        ),
                        "captcha.api_key",
                    )
                else:
                    _add(
                        "ERROR",
                        "captcha_fallback_key_missing",
                        (
                            f"Missing required config for OpenAI-compatible fallback {fp!r}: captcha.api_key."
                        ),
                        "captcha.api_key",
                    )

    # WARN: probe enabled increases background requests; probe_share_pool=false implies extra session slot usage.
    try:
        probe_enabled = bool(config.captcha_probe_enabled)
    except Exception as e:
        probe_enabled = False
        _add("ERROR", "captcha_probe_enabled_read_failed", f"Unable to read captcha.probe_enabled: {e}", "captcha.probe_enabled")

    if probe_enabled:
        _add("WARN", "captcha_probe_enabled", "captcha.probe_enabled=true will add low-frequency background captcha requests.", "captcha.probe_enabled")
        try:
            share_pool = bool(config.captcha_probe_share_pool)
        except Exception as e:
            share_pool = True  # don't double-warn when we cannot read it
            _add("ERROR", "captcha_probe_share_pool_read_failed", f"Unable to read captcha.probe_share_pool: {e}", "captcha.probe_share_pool")
        if not share_pool:
            _add(
                "WARN",
                "captcha_probe_share_pool_false",
                "captcha.probe_share_pool=false may occupy extra login/session slots. Prefer sharing the main pool unless you have quota.",
                "captcha.probe_share_pool",
            )

    # WARN: rate limit safety net may slow down burst if misconfigured.
    try:
        if bool(config.rate_limit_enable):
            _add("WARN", "rate_limit_enabled", "rate_limit.enable=true may slow burst; enable only as a safety net.", "rate_limit.enable")
    except Exception as e:
        _add("ERROR", "rate_limit_enable_read_failed", f"Unable to read rate_limit.enable: {e}", "rate_limit.enable")

    return issues
