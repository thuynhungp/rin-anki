from __future__ import annotations

import json
import re
from typing import Any

from services.ai.prompt import LANGUAGES


class AIParseError(ValueError):
    """Lỗi khi phản hồi AI không dùng được làm JSON từ vựng."""


def _extract_json(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    match = re.search(r"\[[\s\S]*\]", cleaned)
    if not match:
        raise AIParseError("Phản hồi AI không chứa mảng JSON.")
    return match.group(0)


def parse_vocabulary_json(raw: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(_extract_json(raw))
    except json.JSONDecodeError as exc:
        raise AIParseError(f"Phản hồi AI không phải JSON hợp lệ: {exc}") from exc

    if not isinstance(data, list):
        raise AIParseError("Phản hồi AI phải là một mảng JSON.")

    entries: list[dict[str, Any]] = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            continue

        raw_lang = str(item.get("language", "")).strip().upper()
        if raw_lang in ("KO", "KOR"):
            language = "KR"
        elif raw_lang in ("EN", "ENG"):
            language = "EN"
        elif raw_lang in ("JP", "JPN", "JA"):
            language = "JP"
        elif raw_lang in ("CN", "CHI", "ZH"):
            language = "CN"
        else:
            language = raw_lang if raw_lang in LANGUAGES else "EN"

        word = str(item.get("word", "") or "").strip()
        meaning = str(item.get("meaning", "") or "").strip()
        
        # Skip completely empty rows
        if not word and not meaning:
            continue

        try:
            confidence = float(item.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5

        entries.append(
            {
                "language": language,
                "word": word,
                "meaning": meaning,
                "example": str(item.get("example", "") or "").strip(),
                "note": str(item.get("note", "") or "").strip(),
                "confidence": max(0.0, min(1.0, confidence)),
            }
        )

    return entries
