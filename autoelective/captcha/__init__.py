#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# filename: __init__.py
# modified: 2019-09-08

from .captcha import Captcha
from .registry import CaptchaRecognizer, get_recognizer
from .online import BaiduOCRRecognizer
from .gemini import GeminiVLMRecognizer
from .qwen import OpenAICompatRecognizer

__all__ = [
    "Captcha",
    "CaptchaRecognizer",
    "get_recognizer",
    "BaiduOCRRecognizer",
    "GeminiVLMRecognizer",
    "OpenAICompatRecognizer",
]
