#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import base64
import io
import os
import sys
from configparser import RawConfigParser

import requests
from PIL import Image, ImageDraw


def _load_keys():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(repo_root, "config.ini")
    parser = RawConfigParser()
    parser.read(config_path, encoding="utf-8-sig")

    api_key = None
    secret_key = None
    if parser.has_section("captcha"):
        api_key = parser.get("captcha", "baidu_api_key", fallback=None)
        secret_key = parser.get("captcha", "baidu_secret_key", fallback=None)

    api_key = api_key or os.getenv("BAIDU_OCR_API_KEY")
    secret_key = secret_key or os.getenv("BAIDU_OCR_SECRET_KEY")
    return api_key, secret_key


def _make_test_image():
    img = Image.new("RGB", (240, 80), "white")
    draw = ImageDraw.Draw(img)
    draw.text((10, 20), "TEST 123", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def main():
    api_key, secret_key = _load_keys()
    if not api_key or not secret_key:
        print("Baidu OCR keys not found in config.ini or environment.")
        return 2

    token_url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {
        "grant_type": "client_credentials",
        "client_id": api_key,
        "client_secret": secret_key,
    }

    try:
        resp = requests.post(token_url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print("Token request failed:", e)
        return 3

    token = data.get("access_token")
    if not token:
        print("Token response missing access_token:", data)
        return 4

    img_bytes = _make_test_image()
    img_b64 = base64.b64encode(img_bytes).decode("utf-8")

    ocr_url = (
        "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic"
        + "?access_token="
        + token
    )
    payload = {
        "image": img_b64,
        "detect_direction": "true",
        "paragraph": "false",
        "probability": "false",
        "multidirectional_recognize": "true",
    }

    try:
        ocr_resp = requests.post(ocr_url, data=payload, timeout=10)
        ocr_resp.raise_for_status()
        ocr_data = ocr_resp.json()
    except Exception as e:
        print("OCR request failed:", e)
        return 5

    if "error_code" in ocr_data:
        print("OCR error:", ocr_data)
        return 6

    words = ocr_data.get("words_result", [])
    print("OCR OK. words_result:", words)
    return 0


if __name__ == "__main__":
    sys.exit(main())
