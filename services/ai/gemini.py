from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from PIL import Image

from services.ai.parser import parse_vocabulary_json
from services.ai.prompt import build_extraction_prompt

MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
]


@dataclass
class AttemptError:
    model: str
    key_name: str
    message: str


class GeminiVocabularyExtractor:
    def __init__(self) -> None:
        load_dotenv()
        self.keys = [
            (f"GEMINI_API_KEY_{index}", os.getenv(f"GEMINI_API_KEY_{index}", "").strip())
            for index in range(1, 5)
        ]

    def _available_keys(self) -> list[tuple[str, str]]:
        return [(name, key) for name, key in self.keys if key]

    def _generate(self, model: str, api_key: str, contents: list[Any]) -> str:
        from google import genai

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model=model, contents=contents)
        text = getattr(response, "text", None)
        if not text:
            raise RuntimeError("Gemini trả về phản hồi rỗng.")
        return text

    def extract_from_text(self, text: str) -> list[dict[str, Any]]:
        prompt = build_extraction_prompt("text", text=text)
        return self._extract([prompt])

    def extract_from_image(self, image: Image.Image) -> list[dict[str, Any]]:
        prompt = build_extraction_prompt("image")
        return self._extract([prompt, image])

    def _extract(self, contents: list[Any]) -> list[dict[str, Any]]:
        keys = self._available_keys()
        if not keys:
            raise RuntimeError("Chưa tìm thấy Gemini API key. Hãy thêm key vào file .env trước.")

        errors: list[AttemptError] = []
        for model in MODELS:
            for key_name, api_key in keys:
                try:
                    raw = self._generate(model, api_key, contents)
                    return parse_vocabulary_json(raw)
                except Exception as exc:  # Gemini failures and parse errors both fall through.
                    errors.append(AttemptError(model, key_name, str(exc)))

        detail = "\n".join(
            f"- {error.model} with {error.key_name}: {error.message}" for error in errors
        )
        raise RuntimeError(f"Tất cả model/key Gemini đều thất bại:\n{detail}")
