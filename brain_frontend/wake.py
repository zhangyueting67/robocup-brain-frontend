"""ASR-based wake phrase detection for the microphone demo."""

from __future__ import annotations

import re

WAKE_PHRASE = "豆包豆包"
_LEADING_WORDS = ("你好", "您好", "嘿", "嗨", "喂")
_SEPARATORS = " \t\r\n，,。.!！?？:：、"
_WAKE_PATTERN = re.compile(r"^豆包[，,。.!！?？:：、]*豆包")


def extract_wake_command(transcript: str) -> str | None:
    """Return text after the wake phrase; empty means wake-only, None means no wake."""
    text = re.sub(r"\s+", "", transcript).lstrip(_SEPARATORS)
    for word in _LEADING_WORDS:
        if text.startswith(word):
            text = text[len(word):].lstrip(_SEPARATORS)
            break
    match = _WAKE_PATTERN.match(text)
    if match is None:
        return None
    return text[match.end():].lstrip(_SEPARATORS).strip()
