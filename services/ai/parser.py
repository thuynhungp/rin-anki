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
            raise AIParseError(f"Dòng {index} không phải object.")

        language = str(item.get("language", "")).strip().upper()
        if language not in LANGUAGES:
            raise AIParseError(f"Dòng {index} có ngôn ngữ chưa hỗ trợ: '{language}'.")

        word = str(item.get("word", "")).strip()
        meaning = str(item.get("meaning", "")).strip()
        if not word or not meaning:
            raise AIParseError(f"Dòng {index} phải có từ và nghĩa.")

        try:
            confidence = float(item.get("confidence", 0))
        except (TypeError, ValueError) as exc:
            raise AIParseError(f"Dòng {index} có độ tin cậy không hợp lệ.") from exc

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
