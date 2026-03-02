#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

ALLOWED_CAPTCHA_PROVIDERS = ("openai", "baidu", "gemini", "dummy")


def format_target(provider: str, model_name: str | None = None) -> str:
    provider = (provider or "").strip().lower()
    model_name = (model_name or "").strip()
    if provider == "openai" and model_name:
        return "%s:%s" % (provider, model_name)
    return provider


def parse_target_token(token: str) -> tuple[str, str | None]:
    raw = (token or "").strip()
    if not raw:
        raise ValueError("empty target token")
    if ":" in raw:
        provider, model_name = raw.split(":", 1)
        provider = provider.strip().lower()
        model_name = model_name.strip()
    else:
        provider = raw.lower()
        model_name = None

    if provider not in ALLOWED_CAPTCHA_PROVIDERS:
        raise ValueError(
            "Unsupported captcha provider %r. Allowed providers: %s."
            % (provider, ", ".join(ALLOWED_CAPTCHA_PROVIDERS))
        )

    if provider != "openai" and model_name is not None:
        raise ValueError(
            "Provider %r does not support model override in target %r."
            % (provider, raw)
        )

    if provider == "openai" and model_name is not None and model_name == "":
        raise ValueError("Empty model override in target %r." % raw)

    if provider != "openai":
        model_name = None
    return provider, model_name


def parse_targets_csv(text: str) -> list[tuple[str, str | None]]:
    tokens = [s.strip() for s in str(text or "").split(",") if s.strip()]
    if not tokens:
        raise ValueError("No targets specified.")
    out = []
    seen = set()
    for t in tokens:
        provider, model_name = parse_target_token(t)
        key = (provider, model_name or "")
        if key in seen:
            continue
        seen.add(key)
        out.append((provider, model_name))
    return out


def default_targets_from_config(config) -> list[tuple[str, str | None]]:
    providers = [config.captcha_provider] + list(config.captcha_fallback_providers or [])
    out = []
    seen = set()
    for provider in providers:
        provider = (provider or "").strip().lower()
        if not provider:
            continue
        if provider not in ALLOWED_CAPTCHA_PROVIDERS:
            raise ValueError(
                "Unsupported captcha provider %r in config. Allowed providers: %s."
                % (provider, ", ".join(ALLOWED_CAPTCHA_PROVIDERS))
            )
        key = (provider, "")
        if key in seen:
            continue
        seen.add(key)
        out.append((provider, None))
    if not out:
        raise ValueError("No captcha providers configured.")
    return out
