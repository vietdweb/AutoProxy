# AutoProxy - Công cụ tự động lấy proxy từ Webshare qua OTPMail.vn
# Patch-1
Tool tự động hóa quy trình đăng ký tài khoản Webshare thông qua dịch vụ tạo email tạm thời `otpmail.vn` và lưu danh sách 10 proxy miễn phí vào file.

## 📋 Quy trình hoạt động
1. **Bước 1**: Mở `https://otpmail.vn/`, tạo email mới ngẫu nhiên và trích xuất địa chỉ email.
2. **Bước 2**: Mở `https://dashboard.webshare.io/register?source=login_signup_link`, tự động điền email vừa tạo, nhập mật khẩu cố định `Khiem@test`, tích chọn điều khoản (*I agree...*) và nhấn **Sign Up**.
3. **Bước 3**: Chuyển đến mục **Free -> Proxy List** (`https://dashboard.webshare.io/proxy/list`), trích xuất 10 proxy miễn phí và ghi vào file `proxies.txt`.

---

## 🛠️ Cài đặt môi trường

### 1. Yêu cầu hệ thống
- Đã cài đặt **Python 3.8+** trên máy tính.

### 2. Cài đặt thư viện siêu nhẹ
Mở terminal (PowerShell hoặc Command Prompt) tại thư mục dự án và chạy duy nhất:

```bash
pip install -r requirements.txt
```
*(Không cần chạy `playwright install`, tool sẽ sử dụng trực tiếp trình duyệt Google Chrome có sẵn trên máy để tiết kiệm ~250MB dung lượng).*


---

## 🚀 Hướng dẫn chạy Tool

### Cách 1: Chạy bằng 1 click (Khuyên dùng)
Chỉ cần **click đúp vào file `run.bat`**:
- Tự động kiểm tra Python trên máy.
- Tự động cài thư viện nếu chưa có.
- Tự động mở Google Chrome và thực hiện quy trình lấy proxy.

---

### Cách 2: Chạy bằng dòng lệnh (Nếu muốn)
```bash
python main.py
```

### ⚙️ Tùy chỉnh (trong file `config.py`)
- `WEBSHARE_PASSWORD`: Mật khẩu đăng ký tài khoản Webshare (mặc định: `Khiem@test`).
- `OUTPUT_PROXY_FILE`: Tên file lưu danh sách proxy (mặc định: `proxies.txt`).
- `HEADLESS_MODE`: 
  - `False` (mặc định): Mở giao diện cửa sổ trình duyệt để bạn dễ quan sát và vượt CAPTCHA / Cloudflare Turnstile nếu trang yêu cầu.
  - `True`: Chạy ẩn danh dưới nền không hiện giao diện.

---

## 📌 Lưu ý quan trọng
- **Cloudflare / CAPTCHA**: Webshare áp dụng hệ thống bảo vệ Cloudflare Turnstile. Khi trình duyệt tự động mở lên (`HEADLESS_MODE = False`), nếu xuất hiện ô xác thực bot của Cloudflare, bạn có thể click xác thực trực tiếp trên màn hình để tool tiếp tục chạy.
- **Xác nhận Email**: Mã nguồn đã tích hợp sẵn hàm `check_and_click_confirmation` trong `otpmail_helper.py` để tự động kiểm tra hòm thư và nhấn link kích hoạt nếu Webshare gửi thư xác minh.
