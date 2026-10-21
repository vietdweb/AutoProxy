# Cấu hình hệ thống AutoProxy

# Thông tin đăng ký cố định theo yêu cầu
WEBSHARE_PASSWORD = "Khiem@test"

# Các URL dịch vụ
OTPMAIL_URL = "https://otpmail.vn/"
WEBSHARE_REGISTER_URL = "https://dashboard.webshare.io/register?source=login_signup_link"
WEBSHARE_PROXYLIST_URL = "https://dashboard.webshare.io/proxy/list"

# Tên file xuất danh sách proxy
OUTPUT_PROXY_FILE = "proxies.txt"

import os

# Cấu hình trình duyệt
# Mặc định False trên máy cá nhân để hiển thị Chrome
HEADLESS_MODE = False
BROWSER_CHANNEL = "chrome"

# Tự động chuyển chế độ khi deploy lên Render / Linux Server
IS_RENDER = os.environ.get("RENDER") is not None or os.environ.get("PORT") is not None
if IS_RENDER:
    HEADLESS_MODE = True
    BROWSER_CHANNEL = None  # Dùng Chromium chuẩn cài đặt trong môi trường Linux


# Thời gian chờ (giây)
DEFAULT_TIMEOUT = 30000

# Cấu hình lặp lại Bước 1 đến Bước 4 (B4)
# LOOP_COUNT: 0 nghĩa là lặp lại liên tục vô tận (dừng bằng cách đóng cửa sổ cmd hoặc nhấn Ctrl+C)
# Hoặc điền số lần cụ thể (ví dụ: 5 để tạo 5 tài khoản = 50 proxies)
LOOP_COUNT = 0

# Thời gian nghỉ giữa các lần lặp (giây)
DELAY_BETWEEN_LOOPS = 3
