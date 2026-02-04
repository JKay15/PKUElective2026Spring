#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import base64
import json
import os
import re
import time
from io import BytesIO

import requests
from PIL import Image

from .captcha import Captcha
from .registry import CaptchaRecognizer, register_recognizer
from ..config import AutoElectiveConfig
from ..exceptions import OperationFailedError, OperationTimeoutError, RecognizerError


def _normalize_code(text):
    if text is None:
        return ""
    return "".join(ch for ch in str(text) if ch.isalnum()).upper()


def _to_jpeg_bytes(raw):
    im = Image.open(BytesIO(raw))
    try:
        if getattr(im, "is_animated", False):
            im.seek(getattr(im, "n_frames", 1) - 1)
    except Exception:
        pass
    buf = BytesIO()
    im.convert("RGB").save(buf, format="JPEG")
    return buf.getvalue()


def _extract_text_from_response(data):
    choices = data.get("choices") or []
    if not choices:
        return ""
    msg = (choices[0] or {}).get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts = []
        for part in content:
            if not isinstance(part, dict):
                continue
            t = part.get("text")
            if t:
                texts.append(t)
        return "".join(texts).strip()
    return ""


def _extract_code_candidate(text, min_len, max_len):
    if not text:
        return ""
    for pat in (
        r'"text"\s*:\s*"([A-Za-z0-9]+)"',
        r"'text'\s*:\s*'([A-Za-z0-9]+)'",
    ):
        m = re.search(pat, text)
        if m:
            return m.group(1)
    tokens = re.findall(r"[A-Za-z0-9]+", text)
    candidates = [t for t in tokens if min_len <= len(t) <= max_len]
    return candidates[-1] if candidates else ""


class _QwenVLBase(CaptchaRecognizer):
    name = None
    default_model = None

    def __init__(self):
        cfg = AutoElectiveConfig()
        self._api_key = cfg.dashscope_api_key or os.getenv("DASHSCOPE_API_KEY")
        self._base_url = (cfg.dashscope_base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")
        self._timeout = cfg.dashscope_timeout
        self._max_output_tokens = cfg.dashscope_max_output_tokens
        self._min_len = cfg.captcha_code_length_min
        self._max_len = cfg.captcha_code_length_max
        if self._min_len > self._max_len:
            self._min_len, self._max_len = self._max_len, self._min_len
        self._session = requests.Session()

        if not self._api_key:
            raise RecognizerError(
                msg="DashScope API key not configured. Set [captcha] dashscope_api_key or env DASHSCOPE_API_KEY."
            )

        # Model selection: per-provider override first, then generic, then default.
        model_override = cfg.dashscope_model
        if self.name == "qwen3_vl_flash":
            model_override = cfg.dashscope_model_flash or model_override
        elif self.name == "qwen3_vl_plus":
            model_override = cfg.dashscope_model_plus or model_override
        self._model = (model_override or self.default_model).strip()

    def recognize(self, raw):
        img = _to_jpeg_bytes(raw)
        if self._min_len == self._max_len:
            len_rule = f"exactly {self._min_len} characters"
        else:
            len_rule = f"between {self._min_len} and {self._max_len} characters"

        prompt = (
            "You are an OCR engine. Read the captcha text from the image.\n"
            "Return STRICT JSON with a single key 'text'.\n"
            f"The value must be {len_rule} (A-Z, 0-9) with no spaces.\n"
            "If uncertain, make your best guess.\n"
        )

        url = self._base_url + "/chat/completions"
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/jpeg;base64," + base64.b64encode(img).decode("utf-8")
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "temperature": 0,
            "max_tokens": int(self._max_output_tokens),
        }

        headers = {
            "Authorization": "Bearer " + self._api_key,
            "Content-Type": "application/json",
        }

        backoff = 1.0
        resp = None
        data = None
        for attempt in range(3):
            try:
                resp = self._session.post(url, headers=headers, json=payload, timeout=self._timeout)
            except (requests.Timeout, requests.ConnectionError) as e:
                if attempt < 2:
                    time.sleep(backoff)
                    backoff = min(8.0, backoff * 2)
                    continue
                if isinstance(e, requests.Timeout):
                    raise OperationTimeoutError(msg="Recognizer connection time out")
                raise OperationFailedError(msg="Unable to connect to the recognizer")
            except requests.RequestException as e:
                raise OperationFailedError(msg="Recognizer request failed: %s" % e)

            try:
                data = resp.json()
            except ValueError:
                data = None

            if resp.status_code in (429, 500, 503):
                if attempt < 2:
                    ra = resp.headers.get("Retry-After")
                    try:
                        sleep_s = float(ra) if ra else backoff
                    except Exception:
                        sleep_s = backoff
                    time.sleep(sleep_s)
                    backoff = min(8.0, backoff * 2)
                    continue
            break

        if resp is None:
            raise OperationFailedError(msg="Unable to connect to the recognizer")
        if data is None:
            raise RecognizerError(msg="Recognizer ERROR: Invalid JSON response")
        if resp.status_code != 200:
            err = (data.get("error") or {}).get("message") or data
            raise RecognizerError(msg="Recognizer ERROR: %s" % err)

        text = _extract_text_from_response(data)
        code_src = text
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                for k in ("text", "captcha", "code", "result"):
                    v = obj.get(k)
                    if isinstance(v, str) and v.strip():
                        code_src = v
                        break
            elif isinstance(obj, str):
                code_src = obj
        except Exception:
            pass

        if not code_src:
            code_src = _extract_code_candidate(text, self._min_len, self._max_len)

        code = _normalize_code(code_src)
        if not code:
            raise RecognizerError(msg="Recognizer ERROR: Empty result")
        if len(code) < self._min_len or len(code) > self._max_len:
            fallback = _extract_code_candidate(text, self._min_len, self._max_len)
            fallback = _normalize_code(fallback)
            if fallback and self._min_len <= len(fallback) <= self._max_len:
                code = fallback
            else:
                raise RecognizerError(msg="Recognizer ERROR: Unexpected code length: %r" % code)

        return Captcha(code, None, None, None, None)


@register_recognizer
class Qwen3VlFlashRecognizer(_QwenVLBase):
    name = "qwen3_vl_flash"
    default_model = "qwen3-vl-flash"


@register_recognizer
class Qwen3VlPlusRecognizer(_QwenVLBase):
    name = "qwen3_vl_plus"
    default_model = "qwen3-vl-plus"

