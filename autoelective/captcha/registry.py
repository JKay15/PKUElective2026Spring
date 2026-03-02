#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# filename: registry.py

from .captcha import Captcha
from ..config import AutoElectiveConfig
from ..exceptions import RecognizerError
from .targets import ALLOWED_CAPTCHA_PROVIDERS


class CaptchaRecognizer(object):
    name = None

    def recognize(self, raw):
        raise NotImplementedError


_REGISTRY = {}


def register_recognizer(cls):
    name = getattr(cls, "name", None)
    if not name:
        raise ValueError("Recognizer must define a non-empty 'name'")
    _REGISTRY[name] = cls
    aliases = getattr(cls, "aliases", None)
    if aliases:
        for alias in aliases:
            alias = (alias or "").strip()
            if not alias:
                continue
            _REGISTRY[alias] = cls
    return cls


def get_recognizer(name=None, model_name=None):
    if name is None:
        name = AutoElectiveConfig().captcha_provider
    name = (name or "").strip().lower()
    if not name:
        name = "openai"
    if name not in ALLOWED_CAPTCHA_PROVIDERS:
        allowed = ", ".join(ALLOWED_CAPTCHA_PROVIDERS)
        raise RecognizerError(
            msg="Unsupported captcha provider: %r. Allowed providers: %s."
            % (name, allowed)
        )
    if model_name is not None and name != "openai":
        raise RecognizerError(
            msg="Model override is only supported for provider 'openai', got %r."
            % name
        )

    if name == "openai" and model_name is not None:
        from .openai_api import build_openai_compat_recognizer

        return build_openai_compat_recognizer(model_name=model_name)

    cls = _REGISTRY.get(name)
    if cls is None:
        raise RecognizerError(msg="Recognizer not registered for provider %r." % name)
    return cls()


@register_recognizer
class DummyRecognizer(CaptchaRecognizer):
    name = "dummy"

    def recognize(self, raw):
        return Captcha("0000", None, None, None, None)
