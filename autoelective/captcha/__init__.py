#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# filename: __init__.py
# modified: 2019-09-08

from .captcha import Captcha
from .registry import CaptchaRecognizer, get_recognizer
from .online import TTShituRecognizer, BaiduOCRRecognizer
from .gemini import GeminiVLMRecognizer

__all__ = [
    "Captcha",
    "CaptchaRecognizer",
    "get_recognizer",
    "TTShituRecognizer",
    "BaiduOCRRecognizer",
    "GeminiVLMRecognizer",
]
