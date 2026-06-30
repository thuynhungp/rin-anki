# Hướng Dẫn Triển Khai Rin Anki Lên Streamlit Cloud & Cấu Hình Secrets

Tài liệu này hướng dẫn chi tiết cách đưa ứng dụng **Rin Anki** lên **Streamlit Community Cloud** miễn phí, đồng thời quản lý các khóa API bảo mật (thay thế cho file `.env` cục bộ) thông qua GitHub và Streamlit Secrets.

---

## Bước 1: Chuẩn bị mã nguồn trên GitHub

Streamlit Cloud sẽ kết nối trực tiếp với tài khoản GitHub của bạn để lấy mã nguồn và tự động deploy.

### 1. Kiểm tra file `.gitignore`
Trước khi đưa lên GitHub, hãy đảm bảo các tệp thông tin nhạy cảm và cơ sở dữ liệu cục bộ **KHÔNG** bị đẩy lên mạng.
Mở hoặc tạo file `.gitignore` ở thư mục gốc của dự án và kiểm tra xem đã có các dòng sau chưa:
```text
# Không đẩy file cấu hình chứa API Key nhạy cảm
.env

# Không đẩy cơ sở dữ liệu SQLite cá nhân
data/database.db

# Thư mục môi trường ảo Python
.venv/
__pycache__/
*.pyc
```

### 2. Tạo Repository trên GitHub và đẩy mã nguồn lên
1. Truy cập [GitHub](https://github.com/) và tạo một Repository mới (đặt ở chế độ **Private** hoặc **Public** tùy ý).
2. Chạy các lệnh Git sau tại thư mục dự án trên máy tính của bạn:
   ```bash
   git init
   git add .
   git commit -m "Initial commit - Rin Anki theme update and persistent session"
   git branch -M main
   git remote add origin <đường-dẫn-repo-github-của-bạn>
   git push -u origin main
   ```

---

## Bước 2: Triển khai lên Streamlit Community Cloud

1. Truy cập trang web [Streamlit Community Cloud](https://share.streamlit.io/).
2. Chọn **Continue with GitHub** để đăng nhập bằng tài khoản GitHub chứa repository của bạn.
3. Sau khi đăng nhập thành công, nhấn vào nút **Create app** (hoặc **New app**) ở góc trên bên phải.
4. Điền các thông tin sau:
   * **Repository**: Chọn repository `rin-anki` vừa đẩy lên.
   * **Branch**: `main` (hoặc nhánh chứa code của bạn).
   * **Main file path**: `app.py`.
   * **App URL**: Bạn có thể tùy chỉnh tên miền phụ của ứng dụng (Ví dụ: `rin-anki-learning.streamlit.app`).

---

## Bước 3: Cấu hình Secrets trên Streamlit Cloud (Thay thế cho `.env`)

Vì chúng ta không đẩy file `.env` lên GitHub để bảo mật, chúng ta cần cấu hình các khóa API và kết nối cơ sở dữ liệu trong phần **Secrets** của Streamlit Cloud. 

1. Trước khi bấm nút Deploy, hoặc tại trang quản trị ứng dụng sau khi deploy, nhấn vào mục **Advanced settings...** (nằm ở dưới cùng form tạo app) hoặc chọn **Settings ➜ Secrets** của ứng dụng.
2. Tại ô nhập liệu **Secrets**, dán cấu hình API Key và thông tin kết nối **Turso** của bạn theo định dạng **TOML** (như dưới đây):
   ```toml
   GEMINI_API_KEY_1 = "khóa-api-gemini-của-bạn-ở-đây"
   GEMINI_API_KEY_2 = "khóa-api-gemini-phụ-nếu-có"

   # Cấu hình Turso Cloud Database (Giúp chạy vĩnh viễn không sợ mất dữ liệu khi app khởi động lại)
   TURSO_DATABASE_URL = "libsql://ten-database-cua-ban.turso.io"
   TURSO_AUTH_TOKEN = "token-xac-thuc-lay-tu-bang-dieu-khien-turso"
   ```
3. Nhấn **Save**.
4. Nhấn **Deploy!** để bắt đầu quá trình cài đặt môi trường và khởi chạy ứng dụng.

---

## 💡 Giải pháp lưu trữ cơ sở dữ liệu (SQLite cục bộ vs Turso Cloud)

*   **SQLite Cục bộ (Local Run)**:
    *   Mặc định khi không điền thông tin Turso, ứng dụng tự động fallback về dùng tệp SQLite cục bộ tại `data/database.db`.
    *   Thích hợp để học cá nhân offline trên máy tính (bằng cách click chạy file `run-local.bat`).
    *   *Hạn chế trên Cloud*: Tệp SQLite cục bộ trên Streamlit Cloud nằm trong vùng nhớ tạm (ephemeral). Nếu container bị reboot hoặc tự động ngủ (khi không có người học), cơ sở dữ liệu sẽ **bị khởi tạo lại và mất toàn bộ lịch sử học**.
*   **Turso Cloud Database (Khuyên dùng khi chạy Online)**:
    *   Turso là dịch vụ cơ sở dữ liệu đám mây xây dựng trên **libSQL** (một nhánh tương thích 100% với SQLite).
    *   Khi bạn điền `TURSO_DATABASE_URL` và `TURSO_AUTH_TOKEN` vào mục Secrets của Streamlit Cloud, ứng dụng sẽ tự động chuyển sang lưu trữ đám mây của Turso.
    *   Dữ liệu của bạn được đồng bộ và lưu trữ vĩnh viễn trực tuyến mà không bao giờ lo bị mất khi container khởi động lại hay chuyển đổi phiên làm việc.
