#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import re
from typing import Optional, Tuple

from requests.exceptions import RequestException

from .exceptions import (
    AutoElectiveClientException,
    CaughtCheatingError,
    IAAAException,
    InvalidTokenError,
    NotAgreedToSelectionAgreement,
    NotInOperationTimeError,
    ServerError,
    SessionExpiredError,
    SharedSessionError,
    StatusCodeError,
)

_RE_OP_WINDOW = re.compile(
    r"([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}).*?"
    r"([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2})"
)


def extract_operation_window(exc: BaseException) -> Optional[str]:
    """
    Best-effort extraction for messages like:
    "...阶段时间: 2026-02-27 15:00:00 至 2026-03-10 10:00:00"
    """
    msg = str(exc) or ""
    m = _RE_OP_WINDOW.search(msg)
    if not m:
        return None
    return f"{m.group(1)} -> {m.group(2)}"


def classify_rehearsal_error(exc: BaseException) -> Tuple[str, bool]:
    """
    Return (kind, strict_only).

    - strict_only=True: treated as failure only when `--strict` is enabled.
    - strict_only=False: always treated as failure.
    """
    if isinstance(exc, NotInOperationTimeError):
        return ("not_in_operation", True)

    if isinstance(exc, (SessionExpiredError, InvalidTokenError, SharedSessionError)):
        return ("session", False)

    if isinstance(exc, NotAgreedToSelectionAgreement):
        return ("not_agreed", False)

    if isinstance(exc, CaughtCheatingError):
        return ("caught_cheating", False)

    if isinstance(exc, (ServerError, StatusCodeError)):
        return ("http_status", False)

    if isinstance(exc, RequestException):
        return ("network", False)

    if isinstance(exc, IAAAException):
        return ("iaaa", False)

    if isinstance(exc, AutoElectiveClientException):
        return ("autoelective", False)

    return ("unknown", False)
