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


def _repo_root_dir():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _local_vlm_prompt_path():
    custom = (os.getenv("AUTOELECTIVE_VLM_PROMPT_FILE") or "").strip()
    if custom:
        return custom
    return os.path.join(_repo_root_dir(), "captcha_vlm_prompt.local.txt")


def _load_local_vlm_prompt():
    path = _local_vlm_prompt_path()
    try:
        with open(path, "r", encoding="utf-8") as fp:
            return fp.read().strip()
    except OSError:
        return ""


def _is_likely_ocr_model(model_name):
    return "ocr" in str(model_name or "").lower()


@register_recognizer
class OpenAICompatRecognizer(CaptchaRecognizer):
    """
    Generic OpenAI-compatible OCR recognizer.

    Supports:
    - provider=openai + [captcha] model_name/api_key/base_url
    """

    name = "openai"
    aliases = []

    def __init__(self, runtime_model=None):
        cfg = AutoElectiveConfig()
        self._api_key = (
            cfg.captcha_api_key
            or os.getenv("OPENAI_API_KEY")
        )
        self._base_url = (
            cfg.captcha_base_url
            or os.getenv("OPENAI_BASE_URL")
            or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ).rstrip("/")
        self._timeout = cfg.captcha_request_timeout
        self._max_output_tokens = cfg.captcha_max_output_tokens
        self._min_len = cfg.captcha_code_length_min
        self._max_len = cfg.captcha_code_length_max
        if self._min_len > self._max_len:
            self._min_len, self._max_len = self._max_len, self._min_len

        model = (runtime_model or "").strip() or (cfg.captcha_model_name or "").strip()
        if not model:
            raise RecognizerError(
                msg=(
                    "Model not configured for OpenAI-compatible captcha OCR. "
                    "Set [captcha] model_name."
                )
            )
        self._model = model
        self._is_ocr_model = _is_likely_ocr_model(self._model)
        if self._is_ocr_model:
            self._prompt = ""
        else:
            self._prompt = _load_local_vlm_prompt()
        self._session = requests.Session()

        if not self._api_key and "dashscope.aliyuncs.com" in self._base_url:
            raise RecognizerError(
                msg=(
                    "API key missing for DashScope-compatible endpoint. "
                    "Set [captcha] api_key (or OPENAI_API_KEY)."
                )
            )

    def recognize(self, raw):
        img = _to_jpeg_bytes(raw)
        url = self._base_url + "/chat/completions"
        content = [
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/jpeg;base64,"
                    + base64.b64encode(img).decode("utf-8")
                },
            }
        ]
        if self._prompt:
            content.append({"type": "text", "text": self._prompt})
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": content,
                }
            ],
            "temperature": 0,
            "max_tokens": int(self._max_output_tokens),
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = "Bearer " + self._api_key

        backoff = 1.0
        resp = None
        data = None
        for attempt in range(3):
            try:
                resp = self._session.post(
                    url, headers=headers, json=payload, timeout=self._timeout
                )
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
                raise RecognizerError(
                    msg="Recognizer ERROR: Unexpected code length: %r" % code
                )

        return Captcha(code, None, None, None, None)


def build_openai_compat_recognizer(model_name=None):
    return OpenAICompatRecognizer(runtime_model=model_name)
