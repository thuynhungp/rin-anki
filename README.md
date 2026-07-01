# Rin Anki

Ứng dụng web ôn tập từ vựng gọn nhẹ, xây bằng Python, Streamlit, SQLite, SQLAlchemy, Pandas và Gemini.

## Tính năng nổi bật & Cải tiến mới

- **Hai người học cố định**: Rin và Châu.
- **Chọn hồ sơ kiểu Netflix mượt mà**: Nhấp trực tiếp vào avatar để truy cập nhanh, kèm theo hiệu ứng hover phóng to nhẹ (`scale(1.05)`) và đổ bóng tinh tế. Không cần bấm các nút xác nhận phụ.
- **Giữ phiên làm việc (F5 Session Persistence)**: Sử dụng URL Query Parameters (`?user_id=X&menu=Y`) để tự động duy trì người học hiện tại và tab menu khi tải lại trang (F5).
- **Bộ chọn Giao diện (Themes) dịu mắt**: Chuyển đổi trực tiếp 3 giao diện được thiết kế bảo vệ mắt:
  - **Dịu mắt**: Giao diện sáng với tone màu kem ấm `#F8F6F0` (giảm lóa) và màu nhấn xanh teal `#0D9488`.
  - **Hồng dịu**: Giao diện hồng phấn pastel `#FFF5F6` kết hợp chữ màu mận chín `#5F0F40` ấm áp, tương phản tốt và vô cùng dịu mắt.
  - **Tối giản**: Giao diện tối màu charcoal `#1A1A1E` và chữ trắng sữa `#E6E5E0` giúp giảm mỏi mắt khi học ban đêm.
- **Lưu cấu hình giao diện theo người học**: Tự động lưu cấu hình màu sắc yêu thích của từng tài khoản trực tiếp vào cơ sở dữ liệu SQLite (`users.theme`), tự động áp dụng ngay khi đăng nhập.
- **Nhập từ vựng thông minh**:
  - **Form Input**: Nhập từ, nghĩa, ví dụ, ghi chú thủ công.
  - **Nhập bằng AI (Gemini)**: Quét chữ viết tay từ hình ảnh hoặc phân tích ghi chú văn bản thô. Hỗ trợ xem trước và chỉnh sửa trực tiếp trước khi nhập.
- **Thuật toán ôn tập (Quiz)**: Phỏng theo cơ chế **Spaced Repetition** (Lặp lại ngắt quãng) tương tự Anki với 3 mức độ nhớ: "Chưa nhớ" (5 phút), "Nhớ sơ sơ" (2 giờ), và "Nhớ rồi" (tăng dần 7 ➜ 14 ➜ 30 ➜ 60 ➜ 90 ngày).
- **Tích hợp Tab HDSD (Hướng dẫn sử dụng)**: Hướng dẫn chi tiết cách thức hoạt động của các tính năng ngay trong ứng dụng.
- **Cơ sở dữ liệu SQLite**: Lưu trữ tại `data/database.db` có cơ chế tự động chạy di chuyển cột (migration) an toàn khi nâng cấp ứng dụng.

## Cài đặt

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Điền `.env` nếu muốn dùng tính năng nhập bằng AI:

```env
GEMINI_API_KEY_1=
GEMINI_API_KEY_2=
GEMINI_API_KEY_3=
GEMINI_API_KEY_4=
```

## Chạy ứng dụng

```powershell
streamlit run app.py
```

Có thể double-click [run-local.bat](run-local.bat) để chạy nhanh trên máy local.

Database sẽ được tạo tự động và tự cập nhật cấu trúc trong lần chạy đầu tiên.
