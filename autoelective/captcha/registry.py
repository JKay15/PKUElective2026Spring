#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# filename: registry.py

from ..exceptions import RecognizerError
from .captcha import Captcha
from ..config import AutoElectiveConfig


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
    return cls


def get_recognizer(name=None):
    if name is None:
        name = AutoElectiveConfig().captcha_provider
    name = (name or "").strip().lower()
    if not name:
        name = "baidu"
    cls = _REGISTRY.get(name)
    if cls is None:
        raise RecognizerError(msg="Unknown captcha provider: %s" % name)
    return cls()


@register_recognizer
class DummyRecognizer(CaptchaRecognizer):
    name = "dummy"

    def recognize(self, raw):
        return Captcha("0000", None, None, None, None)
