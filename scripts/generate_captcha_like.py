#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import math
import os
import random
import string

from PIL import Image, ImageDraw, ImageFont, ImageFilter

DEFAULT_CHARS = string.ascii_uppercase + string.digits


def _random_text(length, chars=DEFAULT_CHARS):
    return "".join(random.choice(chars) for _ in range(length))


def _load_font(size):
    # Try common fonts, fall back to default
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_noise(draw, w, h, density=0.015):
    n = int(w * h * density)
    for _ in range(n):
        x = random.randint(0, w - 1)
        y = random.randint(0, h - 1)
        c = random.randint(0, 255)
        draw.point((x, y), fill=(c, c, c))


def _draw_lines(draw, w, h, count=3):
    for _ in range(count):
        x1 = random.randint(0, w)
        y1 = random.randint(0, h)
        x2 = random.randint(0, w)
        y2 = random.randint(0, h)
        c = random.randint(60, 160)
        draw.line((x1, y1, x2, y2), fill=(c, c, c), width=1)


def _distort(img):
    w, h = img.size
    # sinusoidal horizontal distortion
    dx = random.uniform(1.5, 3.5)
    dy = random.uniform(1.0, 2.5)
    x_period = random.uniform(80.0, 140.0)
    y_period = random.uniform(80.0, 140.0)
    x_phase = random.uniform(0, 2 * math.pi)
    y_phase = random.uniform(0, 2 * math.pi)

    def _shift(x, y):
        return (
            x + dx * math.sin(2 * math.pi * y / x_period + x_phase),
            y + dy * math.sin(2 * math.pi * x / y_period + y_phase),
        )

    dst = Image.new("RGB", (w, h), "white")
    for y in range(h):
        for x in range(w):
            sx, sy = _shift(x, y)
            sx = int(min(max(sx, 0), w - 1))
            sy = int(min(max(sy, 0), h - 1))
            dst.putpixel((x, y), img.getpixel((sx, sy)))
    return dst


def generate_one(text, w, h):
    img = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(img)
    font = _load_font(size=int(h * 0.65))

    # random placement per character
    spacing = w // (len(text) + 1)
    for i, ch in enumerate(text):
        x = spacing * (i + 1) - random.randint(6, 12)
        y = random.randint(0, max(0, h - int(h * 0.75)))
        angle = random.uniform(-25, 25)
        ch_img = Image.new("RGBA", (spacing, h), (255, 255, 255, 0))
        ch_draw = ImageDraw.Draw(ch_img)
        ch_draw.text((0, 0), ch, font=font, fill=(0, 0, 0))
        ch_img = ch_img.rotate(angle, resample=Image.BICUBIC, expand=1)
        img.paste(ch_img, (x, y), ch_img)

    _draw_lines(draw, w, h, count=random.randint(2, 4))
    _draw_noise(draw, w, h, density=random.uniform(0.01, 0.02))

    img = _distort(img)
    img = img.filter(ImageFilter.SMOOTH)
    return img


def main():
    parser = argparse.ArgumentParser(description="Generate captcha-like images")
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--out", default="cache/captcha_synth")
    parser.add_argument("--width", type=int, default=140)
    parser.add_argument("--height", type=int, default=48)
    parser.add_argument("--length", type=int, default=4)
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    for i in range(args.count):
        text = _random_text(args.length)
        img = generate_one(text, args.width, args.height)
        path = os.path.join(args.out, f"synth_{i:04d}_{text}.jpg")
        img.save(path, quality=90)

    print(f"Saved {args.count} captcha-like images to {args.out}")


if __name__ == "__main__":
    main()
