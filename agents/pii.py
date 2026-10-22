"""
PII redaction for text that is about to be sent to a third-party LLM.

Customers type card numbers, Aadhaar numbers, phone numbers and even OTPs into
complaints and chats. The model never needs those to classify a complaint or
answer a policy question, so they are masked before any prompt is built. The
original text stays in our own database (an admin may need it); only the copy
that leaves for the LLM is redacted.

Pattern-based, so it catches structured identifiers and misses free-text ones
such as people's names or addresses. Amounts are deliberately left alone:
priority depends on them, and an amount without 9+ digits is never matched.
"""
from __future__ import annotations

import re
from collections import Counter

_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_UPI = re.compile(r"(?<![\w.])[\w.\-]{2,}@[A-Za-z]{2,}\b")
_PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
_IFSC = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")
_SECRET = re.compile(r"(?i)\b(otp|pin|cvv|cvc|password|passcode)\b([^0-9\n]{0,15})(\d{3,8})\b")
_CARD = re.compile(r"(?<!\d)(?:\d[ \-]?){13,19}(?!\d)")
_AADHAAR = re.compile(r"(?<!\d)[2-9]\d{3}[ \-]?\d{4}[ \-]?\d{4}(?!\d)")
_PHONE = re.compile(r"(?<!\d)(?:\+?91[ \-]?)?[6-9]\d{4}[ \-]?\d{5}(?!\d)")
_ACCOUNT = re.compile(r"(?<!\d)\d{9,18}(?!\d)")


def _luhn_ok(digits: str) -> bool:
    total, flip = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if flip:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
        flip = not flip
    return total % 10 == 0


def redact(text: str) -> tuple[str, dict[str, int]]:
    """Returns (redacted_text, {label: count}). Reference numbers (UUIDs) are
    kept intact so the model can still see that one was mentioned."""
    counts: Counter[str] = Counter()

    keep: list[str] = []

    def stash(m: re.Match) -> str:
        keep.append(m.group(0))
        return f"\x00{len(keep) - 1}\x00"

    out = _UUID.sub(stash, text)

    def sub(pattern: re.Pattern, label: str, s: str, check=None) -> str:
        def repl(m: re.Match) -> str:
            if check and not check(m):
                return m.group(0)
            counts[label] += 1
            return f"[{label}]"

        return pattern.sub(repl, s)

    out = sub(_EMAIL, "EMAIL", out)
    out = sub(_UPI, "UPI_ID", out)

    def secret(m: re.Match) -> str:
        counts["SECRET"] += 1
        return f"{m.group(1)}{m.group(2)}[SECRET]"

    out = _SECRET.sub(secret, out)
    out = sub(_PAN, "PAN", out)
    out = sub(_IFSC, "IFSC", out)
    out = sub(_CARD, "CARD", out, check=lambda m: _luhn_ok(re.sub(r"\D", "", m.group(0))) and len(re.sub(r"\D", "", m.group(0))) >= 13)
    out = sub(_AADHAAR, "AADHAAR", out)
    out = sub(_PHONE, "PHONE", out)
    out = sub(_ACCOUNT, "ACCOUNT_NO", out)

    out = re.sub(r"\x00(\d+)\x00", lambda m: keep[int(m.group(1))], out)
    return out, dict(counts)


def redact_text(text: str) -> str:
    return redact(text)[0]
