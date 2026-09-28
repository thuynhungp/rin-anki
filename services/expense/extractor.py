from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any, Optional
from dotenv import load_dotenv
from PIL import Image

MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
]

EXPENSE_PROMPT = """Bạn là trợ lý AI kế toán cá nhân thông minh.
Nhiệm vụ của bạn là đọc và phân tích kỹ lưỡng các hình ảnh chụp màn hình lịch sử giao dịch ngân hàng / ví điện tử (ACB, MSB, Momo, ShopeePay, v.v.).

Hãy trích xuất tất cả các giao dịch xuất hiện trong ảnh thành một danh sách JSON.
Với mỗi giao dịch, hãy tạo một JSON object với các trường sau:
- "date": Chuỗi ngày theo định dạng "YYYY-MM-DD". Nếu trên ảnh chỉ có ngày và tháng (hoặc ngày trong tháng hiện tại), hãy suy luận dựa trên ngữ cảnh hoặc dùng năm hiện tại.
- "bank_name": Chuỗi tên ngân hàng/ví hiển thị trên giao diện (ví dụ: "MSB", "ACB", "Momo", "Shopee", "Tiền mặt").
- "type": "expense" (nếu là tiền chi ra, chuyển tiền đi, thanh toán, trừ tiền, có dấu trừ '-') hoặc "income" (nếu là tiền nhận về, nạp tiền vào, cộng tiền, có dấu cộng '+').
- "amount": Số tiền (số dương kiểu float hoặc integer, ví dụ 41000, 150000, 2089368). Loại bỏ ký hiệu đ, VND, dấu phẩy, dấu chấm ngăn cách hàng nghìn.
- "description": Tên người nhận, nơi mua hàng, hoặc nội dung giao dịch vắn tắt (ví dụ: "Grab", "Marukame Udon", "Hasaki", "Cơm trưa", "Spotify", "Xăng"...).
- "category": Phân loại tự động chính xác vào 1 trong các nhóm sau:
  + "Ăn uống" (đồ ăn, nước uống, quán ăn, siêu thị đồ ăn, GrabFood, cafe, trà sữa...)
  + "Mua sắm" (mỹ phẩm, đồ trang điểm, shopee, quần áo, phụ kiện...)
  + "Thiết yếu" (xăng, điện nước, nạp tiền điện thoại...)
  + "Subscription" (iCloud, Spotify, Claude, Netflix, phí SMS, phí ngân hàng...)
  + "Giải trí" (làm tóc, makeup, gội đầu dưỡng sinh, sách truyện, ridi...)
  + "Y tế" (thuốc, nha khoa, sữa Ensure, chăm sóc sức khỏe...)
  + "Ngoài lề" (tiền gửi xe, phí linh tinh...)
  + "Nợ" (cho mượn, trả nợ...)
  + "Lương" (tiền lương từ công ty)
  + "Khác"
- "balance_after": Số dư tài khoản sau giao dịch (nếu ảnh có hiển thị số dư, ví dụ: 5001052. Nếu ảnh không hiển thị thì để null).

QUAN TRỌNG: Chỉ trả về duy nhất khối JSON dạng ```json [ ... ] ```, không kèm theo lời dẫn giải thích.
"""


class GeminiExpenseExtractor:
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

    def extract_from_images(self, images: list[Image.Image]) -> list[dict[str, Any]]:
        keys = self._available_keys()
        if not keys:
            raise RuntimeError("Chưa tìm thấy Gemini API key. Hãy kiểm tra file .env.")

        contents: list[Any] = [EXPENSE_PROMPT]
        for img in images:
            contents.append(img)

        last_error = None
        for key_name, api_key in keys:
            for model in MODELS:
                try:
                    raw_text = self._generate(model=model, api_key=api_key, contents=contents)
                    parsed = self._parse_json_response(raw_text)
                    if isinstance(parsed, list):
                        return parsed
                except Exception as exc:
                    last_error = exc
                    continue

        raise RuntimeError(f"Không thể bóc tách giao dịch qua AI: {last_error}")

    def _parse_json_response(self, text: str) -> list[dict[str, Any]]:
        # Tìm khối ```json ... ```
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        clean_text = json_match.group(1).strip() if json_match else text.strip()

        data = json.loads(clean_text)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "transactions" in data:
            return data["transactions"]
        return []
