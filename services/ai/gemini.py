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

    def _ocr_image(self, image: Image.Image) -> str:
        keys = self._available_keys()
        if not keys:
            raise RuntimeError("Chưa tìm thấy Gemini API key. Hãy thêm key vào file .env trước.")

        prompt = "Hãy đọc và sao chép lại chính xác toàn bộ văn bản/chữ viết tay có trong hình ảnh này. Giữ nguyên cấu trúc dòng để dễ đọc."
        contents = [prompt, image]
        
        errors: list[AttemptError] = []
        for model in MODELS:
            for key_name, api_key in keys:
                try:
                    return self._generate(model, api_key, contents)
                except Exception as exc:
                    errors.append(AttemptError(model, key_name, str(exc)))

        detail = "\n".join(
            f"- {error.model} with {error.key_name}: {error.message}" for error in errors
        )
        raise RuntimeError(f"Tất cả model/key Gemini đều thất bại khi quét OCR ảnh:\n{detail}")

    def extract_from_image(self, image: Image.Image) -> list[dict[str, Any]]:
        raw_text = self._ocr_image(image)
        return self.extract_from_text(raw_text)

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

    def conjugate_korean_words(self, words: list[str]) -> list[dict[str, str]]:
        if not words:
            return []
            
        keys = self._available_keys()
        if not keys:
            raise RuntimeError("Chưa tìm thấy Gemini API key. Hãy thêm key vào file .env trước.")

        import json
        p1 = "Bạn là một chuyên gia ngôn ngữ tiếng Hàn. Hãy chia các từ tiếng Hàn sau đây sang 3 dạng:\n"
        p2 = "1. Dạng thân mật/đời thường \"아/어/여\" (ví dụ: động từ ăn là 먹다 -> ăn: 먹어, đi là 가다 -> đi: 가).\n"
        p3 = "2. Dạng định ngữ \"은/는\" (ví dụ: động từ ăn là 먹다 -> định ngữ là 먹는, đi là 가다 -> định ngữ là 가는; tính từ đẹp là 예쁘다 -> định ngữ là 예쁜).\n"
        p4 = "3. Dạng nguyên nhân \"(으)니까\" (ví dụ: động từ ăn là 먹다 -> 먹으니까, đi là 가다 -> 가니까).\n\n"
        p5 = (
            "Quy tắc:\n"
            "- Chỉ trả về duy nhất một mảng JSON. Không Markdown, không giải thích gì thêm.\n"
            "- Với mỗi từ, nếu không chia được, điền dạng chia là chuỗi rỗng \"\".\n"
            "- Định dạng mảng JSON phải đúng như sau:\n"
            "[\n"
            "  {\n"
            "    \"word\": \"từ_gốc\",\n"
            "    \"a_eo_yeo\": \"dạng_chia_1\",\n"
            "    \"eun_neun\": \"dạng_chia_2\",\n"
            "    \"eu_ni_kka\": \"dạng_chia_3\"\n"
            "  }\n"
            "]\n\n"
            "Danh sách từ cần chia:\n"
        )
        prompt = p1 + p2 + p3 + p4 + p5 + json.dumps(words, ensure_ascii=False)
        contents = [prompt]
        errors = []
        for model in MODELS:
            for key_name, api_key in keys:
                try:
                    raw = self._generate(model, api_key, contents)
                    cleaned = raw.strip()
                    if cleaned.startswith("```"):
                        import re
                        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
                        cleaned = re.sub(r"```$", "", cleaned).strip()
                    import re
                    match = re.search(r"\[[\s\S]*\]", cleaned)
                    if not match:
                        raise ValueError("Không tìm thấy mảng JSON trong phản hồi.")
                    data = json.loads(match.group(0))
                    if not isinstance(data, list):
                        raise ValueError("Phản hồi không phải là một mảng JSON.")
                    return data
                except Exception as exc:
                    errors.append(AttemptError(model, key_name, str(exc)))
        detail = "\n".join(
            f"- {error.model} with {error.key_name}: {error.message}" for error in errors
        )
        raise RuntimeError(f"Tất cả model/key Gemini đều thất bại khi chia động từ:\n{detail}")

    def extract_grammar_note(self, image: Image.Image, known_words: list[str] = None) -> str:
        keys = self._available_keys()
        if not keys:
            raise RuntimeError("Chưa tìm thấy Gemini API key. Hãy thêm key vào file .env trước.")

        known_words_str = ""
        if known_words:
            known_words_str = f"\nDanh sách từ vựng người học đã biết (hãy ưu tiên sử dụng các từ này hoặc các từ đơn giản tương đương để đặt ví dụ):\n{', '.join(known_words)}\n"

        prompt = f"""
Bạn là một trợ lý AI học tập xuất sắc. Hãy đọc hình ảnh ghi chú viết tay này và trích xuất nội dung thành định dạng Markdown sạch đẹp.

Quy tắc định dạng:
1. Dòng đầu tiên của phản hồi phải luôn là tiêu đề chính tóm tắt ngắn gọn điểm ngữ pháp hoặc chủ đề chính của ghi chú, bắt đầu bằng dấu '#' (ví dụ: '# Ngữ pháp -아/어/여야 하다' hoặc '# Cách dùng V + (u)니까').
2. Dòng thứ hai trở đi: Giữ nguyên cấu trúc phân cấp (dùng tiêu đề Markdown thích hợp ## hoặc ### cho các phần nội dung bên dưới).
3. Tự động nhận diện các điểm ngữ pháp cấu trúc, công thức, quy tắc hoặc ví dụ quan trọng và định dạng chúng nổi bật:
   - Dùng chữ in đậm (**chữ**) cho cấu trúc ngữ pháp chính hoặc từ khóa quan trọng.
   - Dùng thẻ highlight (<mark>chữ</mark>) để làm nổi bật các phần lưu ý quan trọng, quy tắc bất quy tắc hoặc thông tin cốt lõi cần ghi nhớ.
4. Với mỗi điểm cấu trúc ngữ pháp được trích xuất, hãy tự động tạo ra đúng 2 ví dụ thực tế (kèm theo bản dịch nghĩa tiếng Việt) để minh họa rõ nét cách dùng, ngay cả khi ghi chú gốc không ghi ví dụ.{known_words_str}
5. Nếu ghi chú viết tay quá ngắn hoặc chỉ chứa công thức ngữ pháp thô (thiếu lời giải thích), hãy chủ động bổ sung phần giải thích chi tiết về ý nghĩa, cách sử dụng, đối tượng đi kèm (động từ, tính từ, hay danh từ) và các lưu ý quan trọng để ghi chú hoàn thiện và dễ học hơn.
6. Toàn bộ phần giải thích, chú thích và tựa đề của ghi chú phải được viết bằng tiếng Việt. Các câu ví dụ viết bằng tiếng Hàn (kèm dịch nghĩa tiếng Việt ngay bên dưới).
7. Bảo toàn tối đa nội dung ghi chú gốc, dịch giải nghĩa sang tiếng Việt nếu ghi chú gốc dùng ngôn ngữ khác.
8. Trả về trực tiếp nội dung dưới dạng Markdown, không bao quanh bằng khối code ```markdown.
"""
        contents = [prompt, image]
        errors: list[AttemptError] = []
        for model in MODELS:
            for key_name, api_key in keys:
                try:
                    return self._generate(model, api_key, contents)
                except Exception as exc:
                    errors.append(AttemptError(model, key_name, str(exc)))

        detail = "\n".join(
            f"- {error.model} with {error.key_name}: {error.message}" for error in errors
        )
        raise RuntimeError(f"Tất cả model/key Gemini đều thất bại khi quét OCR ghi chú ngữ pháp:\n{detail}")

    def suggest_tags_for_title(self, title: str, existing_tags: list[str]) -> list[str]:
        keys = self._available_keys()
        if not keys:
            raise RuntimeError("Chưa tìm thấy Gemini API key. Hãy thêm key vào file .env trước.")

        import json
        existing_tags_str = ", ".join(existing_tags) if existing_tags else "Không có thẻ nào"
        
        prompt = (
            "Bạn là một trợ lý giáo dục ngôn ngữ xuất sắc chuyên phân tích và gắn thẻ ngữ pháp.\n"
            f"Hãy phân tích tiêu đề ghi chú ngữ pháp sau đây: \"{title}\"\n\n"
            f"Danh sách các thẻ (tags) hiện có trong hệ thống của người học:\n{existing_tags_str}\n\n"
            "Nhiệm vụ:\n"
            "1. Phân tích tiêu đề ngữ pháp này và xác định 1-3 thẻ (nhãn) phù hợp nhất.\n"
            "2. Hãy ƯU TIÊN tối đa việc chọn thẻ phù hợp từ danh sách các thẻ hiện có nếu có sự tương đồng cao về nghĩa.\n"
            "3. Nếu không có thẻ nào hiện có phù hợp, hoặc cần thêm thẻ mới để phân loại chính xác hơn, bạn có thể tự đề xuất thêm thẻ mới (ví dụ: cấp độ 'sơ cấp', 'trung cấp', hoặc chủ đề 'kính ngữ', 'giả định', 'nguyên nhân', v.v.).\n"
            "4. Định dạng của thẻ phải là chữ thường, ngắn gọn, súc tích (1-3 từ).\n\n"
            "Quy tắc phản hồi:\n"
            "- Trả về duy nhất một mảng JSON chứa các chuỗi đại diện cho tên các thẻ được gán (ví dụ: [\"sơ cấp\", \"kính ngữ\"]).\n"
            "- Không Markdown, không giải thích gì thêm, không bao quanh bằng khối code ```json.\n"
        )
        
        contents = [prompt]
        errors = []
        for model in MODELS:
            for key_name, api_key in keys:
                try:
                    raw = self._generate(model, api_key, contents)
                    cleaned = raw.strip()
                    if cleaned.startswith("```"):
                        import re
                        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
                        cleaned = re.sub(r"```$", "", cleaned).strip()
                    
                    import re
                    match = re.search(r"\[[\s\S]*\]", cleaned)
                    if not match:
                        raise ValueError("Không tìm thấy mảng JSON trong phản hồi.")
                    data = json.loads(match.group(0))
                    if not isinstance(data, list):
                        raise ValueError("Phản hồi không phải là một mảng JSON.")
                    
                    # Convert to lowercase and clean up
                    cleaned_tags = [str(t).strip().lower() for t in data if t]
                    return list(set(cleaned_tags))
                except Exception as exc:
                    errors.append(AttemptError(model, key_name, str(exc)))
                    
        detail = "\n".join(
            f"- {error.model} with {error.key_name}: {error.message}" for error in errors
        )
        raise RuntimeError(f"Tất cả model/key Gemini đều thất bại khi gợi ý thẻ cho ngữ pháp:\n{detail}")

    def shorten_grammar_content(self, content: str) -> str:
        keys = self._available_keys()
        if not keys:
            raise RuntimeError("Chưa tìm thấy Gemini API key. Hãy thêm key vào file .env trước.")

        prompt = (
            "Bạn là một trợ lý giáo dục ngôn ngữ xuất sắc. Hãy rút gọn nội dung ghi chú ngữ pháp sau đây thành phiên bản ngắn gọn nhưng đầy đủ thông tin quan trọng.\n\n"
            "Yêu cầu:\n"
            "1. Tóm tắt ý nghĩa cốt lõi.\n"
            "2. Đưa ra công thức/cấu trúc ngữ pháp rõ ràng.\n"
            "3. BẮT BUỘC giữ lại tất cả các trường hợp ngoại lệ, lưu ý đặc biệt, lỗi sai thường gặp, và sự khác biệt với cấu trúc tương tự (nếu có trong bản gốc). Đây là phần quan trọng nhất, KHÔNG ĐƯỢC lược bỏ.\n"
            "4. Giữ lại 1-2 ví dụ minh họa tiêu biểu nhất (kèm bản dịch tiếng Việt).\n"
            "5. Loại bỏ phần giải thích dài dòng, lặp lại, hoặc mở rộng không cần thiết.\n"
            "6. Định dạng bằng Markdown sạch đẹp.\n"
            "7. Trả về trực tiếp nội dung Markdown, không bao quanh bằng khối code ```markdown.\n\n"
            "Nội dung ghi chú cần rút gọn:\n"
            f"{content}"
        )
        
        contents = [prompt]
        errors = []
        for model in MODELS:
            for key_name, api_key in keys:
                try:
                    return self._generate(model, api_key, contents)
                except Exception as exc:
                    errors.append(AttemptError(model, key_name, str(exc)))
                    
        detail = "\n".join(
            f"- {error.model} with {error.key_name}: {error.message}" for error in errors
        )
        raise RuntimeError(f"Tất cả model/key Gemini đều thất bại khi rút gọn ghi chú:\n{detail}")



