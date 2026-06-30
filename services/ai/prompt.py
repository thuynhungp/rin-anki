LANGUAGES = ("KR", "EN", "JP", "CN")


def build_extraction_prompt(input_kind: str, text: str | None = None) -> str:
    source = "ảnh ghi chú viết tay" if input_kind == "image" else "văn bản được dán"
    pasted = f"\n\nVăn bản được dán:\n{text}" if text else ""
    return f"""
Bạn trích xuất các mục từ vựng từ {source}.

Quy tắc:
- Tự nhận diện ngôn ngữ, chỉ dùng một trong các mã: KR, EN, JP, CN.
- Chỉ trả về JSON. Không Markdown. Không giải thích.
- Luôn trả về một mảng JSON, kể cả khi chỉ có một mục.
- Dùng chuỗi rỗng cho trường tùy chọn bị thiếu.
- confidence phải là số từ 0 đến 1.
- Không bịa thêm mục không nhìn thấy hoặc không có trong đầu vào.

Định dạng mỗi mục:
{{
  "language": "KR",
  "word": "먹다",
  "meaning": "An",
  "example": "밥을 먹어요.",
  "note": "",
  "confidence": 0.99
}}
{pasted}
""".strip()
