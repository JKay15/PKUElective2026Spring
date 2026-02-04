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
    # Normalize to a small JPEG payload so the API sees a stable format.
    im = Image.open(BytesIO(raw))
    try:
        if getattr(im, "is_animated", False):
            im.seek(getattr(im, "n_frames", 1) - 1)
    except Exception:
        pass
    buf = BytesIO()
    im.convert("RGB").save(buf, format="JPEG")
    return buf.getvalue()


def _extract_text_from_gemini_response(data):
    # Response shape is typically: candidates[0].content.parts[*].text
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    content = (candidates[0] or {}).get("content") or {}
    parts = content.get("parts") or []
    texts = []
    for p in parts:
        t = (p or {}).get("text")
        if t:
            texts.append(t)
    return "".join(texts).strip()

def _extract_code_candidate(text, min_len, max_len):
    if not text:
        return ""

    # Try to pull JSON key first (works even if extra text wraps the JSON).
    # Examples:
    #   {"text":"AB12"}
    #   JSON: {"text": "AB12"}
    for pat in (
        r'"text"\s*:\s*"([A-Za-z0-9]+)"',
        r"'text'\s*:\s*'([A-Za-z0-9]+)'",
    ):
        m = re.search(pat, text)
        if m:
            return m.group(1)

    # Otherwise, take the last alnum token within range.
    tokens = re.findall(r"[A-Za-z0-9]+", text)
    candidates = [t for t in tokens if min_len <= len(t) <= max_len]
    return candidates[-1] if candidates else ""


@register_recognizer
class GeminiVLMRecognizer(CaptchaRecognizer):
    name = "gemini"

    def __init__(self):
        cfg = AutoElectiveConfig()
        self._api_key = (
            cfg.gemini_api_key
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
        )
        self._model = (cfg.gemini_model or os.getenv("GEMINI_MODEL") or "gemini-2.0-flash").strip()
        self._timeout = cfg.gemini_timeout
        self._max_output_tokens = cfg.gemini_max_output_tokens
        self._min_len = cfg.captcha_code_length_min
        self._max_len = cfg.captcha_code_length_max
        if self._min_len > self._max_len:
            self._min_len, self._max_len = self._max_len, self._min_len
        self._session = requests.Session()

        if not self._api_key:
            raise RecognizerError(
                msg="Gemini API key not configured. Set [captcha] gemini_api_key or env GEMINI_API_KEY/GOOGLE_API_KEY."
            )

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
        url = "https://generativelanguage.googleapis.com/v1beta/models/" + self._model + ":generateContent"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": base64.b64encode(img).decode("utf-8"),
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": int(self._max_output_tokens),
            },
        }
        headers = {
            "Content-Type": "application/json",
            "X-goog-api-key": self._api_key,
        }

        # Retry on rate-limit / transient network errors.
        backoff = 1.0
        last_exc = None
        resp = None
        data = None
        for attempt in range(3):
            try:
                resp = self._session.post(url, headers=headers, json=payload, timeout=self._timeout)
            except (requests.Timeout, requests.ConnectionError) as e:
                last_exc = e
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
                # Respect Retry-After when present; otherwise exponential backoff.
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
            # Shouldn't happen, but keep error messages consistent.
            raise OperationFailedError(msg="Unable to connect to the recognizer")

        if data is None:
            raise RecognizerError(msg="Recognizer ERROR: Invalid JSON response")

        if resp.status_code != 200:
            err = (data.get("error") or {}).get("message") or data
            raise RecognizerError(msg="Recognizer ERROR: %s" % err)

        text = _extract_text_from_gemini_response(data)
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
            # As a last resort, try to extract from the full model text (helps when it adds wrappers like "JSON:").
            fallback = _extract_code_candidate(text, self._min_len, self._max_len)
            fallback = _normalize_code(fallback)
            if fallback and self._min_len <= len(fallback) <= self._max_len:
                code = fallback
            else:
                raise RecognizerError(msg="Recognizer ERROR: Unexpected code length: %r" % code)
        return Captcha(code, None, None, None, None)
