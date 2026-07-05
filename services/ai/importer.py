from __future__ import annotations

from typing import Any

import pandas as pd

REQUIRED_COLUMNS = ["language", "word", "meaning", "example", "note"]


def entries_to_preview_frame(entries: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for entry in entries:
        confidence = float(entry.get("confidence", 0))
        note_val = str(entry.get("note") or "").strip()
        example_val = str(entry.get("example") or "").strip()
        
        combined_note = note_val
        if example_val:
            if combined_note:
                combined_note = f"{combined_note}\nVí dụ: {example_val}"
            else:
                combined_note = f"Ví dụ: {example_val}"
                
        rows.append(
            {
                "import": True,
                "language": entry.get("language", ""),
                "word": entry.get("word", ""),
                "meaning": entry.get("meaning", ""),
                "note": combined_note,
                "confidence": confidence,
                "needs_review": confidence < 0.7,
            }
        )
    return pd.DataFrame(rows)


def valid_import_rows(frame: pd.DataFrame) -> list[dict[str, str]]:
    if frame.empty:
        return []

    selected = frame[frame["import"] == True].copy()  # noqa: E712
    rows: list[dict[str, str]] = []
    for _, row in selected.iterrows():
        word = str(row.get("word", "")).strip()
        meaning = str(row.get("meaning", "")).strip()
        language = str(row.get("language", "")).strip().upper()
        if not word or not meaning or language not in {"KR", "EN", "JP", "CN"}:
            continue
        rows.append(
            {
                "language": language,
                "word": word,
                "meaning": meaning,
                "example": str(row.get("example", "") or "").strip(),
                "note": str(row.get("note", "") or "").strip(),
            }
        )
    return rows
