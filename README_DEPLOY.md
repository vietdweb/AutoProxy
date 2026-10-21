# HƯỚNG DẪN DEPLOY AUTOPROXY LÊN RENDER.COM 🚀

Hệ thống đã được thiết kế sẵn chuẩn theo mô hình Cloud Dashboard (tương tự như dự án SieuNhanToi):
- **Web Dashboard**: Xem thống kê thời gian thực, bật/tắt thu thập proxy bằng nút bấm.
- **Live Terminal Log**: Xem trực tiếp tiến trình đăng ký và cào proxy.
- **REST API tích hợp**: `/api/proxies?format=text` cho phép bất kỳ tool nào (kể cả SieuNhanToi) kéo proxy tự động về dùng 24/7.
- **Tự động nhận diện Render**: Tự chuyển sang headless mode và cài đặt Chromium của Linux.

---

## BƯỚC 1: Đẩy mã nguồn lên GitHub

Mở cửa sổ Command Prompt hoặc Git Bash tại thư mục `D:\JOB-Ngoai\AutoProxy`:

```bash
git init
git add .
git commit -m "Initial commit AutoProxy with Web Dashboard"
```

Tạo một repository mới trên [GitHub](https://github.com/new) (chọn Private hoặc Public), sau đó liên kết và đẩy code lên:

```bash
git branch -M main
git remote add origin https://github.com/<tai-khoan-cua-ban>/AutoProxy.git
git push -u origin main
```

---

## BƯỚC 2: Tạo Web Service trên Render.com

1. Truy cập [dashboard.render.com](https://dashboard.render.com/) và đăng nhập.
2. Bấm vào nút **New +** ở góc trên bên phải ➔ Chọn **Web Service** (hoặc chọn **Blueprint** để nhận diện trực tiếp file `render.yaml`).
3. Chọn Repository GitHub `AutoProxy` mà bạn vừa đẩy lên ➔ Bấm **Connect**.
4. Cấu hình dịch vụ (nếu không dùng Blueprint):
   - **Name**: `autoproxy-collector` (hoặc tên tùy thích)
   - **Region**: Singapore hoặc Oregon (US West)
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**:
     ```bash
     pip install -r requirements.txt && playwright install chromium --with-deps
     ```
   - **Start Command**:
     ```bash
     python web_server.py
     ```
   - **Plan Type**: Chọn **Free**
5. Bấm nút **Create Web Service** ở cuối trang.

---

## BƯỚC 3: Sử dụng Web Dashboard & API

Sau khoảng 2-3 phút, Render sẽ build xong và cấp cho bạn một đường link công khai (Ví dụ: `https://autoproxy-collector.onrender.com`):

- **Truy cập Dashboard**: Mở link trên trình duyệt máy tính hoặc điện thoại.
- **Bắt đầu thu thập**: Bấm nút xanh **▶ Bắt Đầu** trên giao diện để tự động chạy cào proxy ngầm.
- **Tải danh sách**: Bấm **📥 Tải proxies.txt** hoặc **📋 Sao Chép Hết**.
- **Tích hợp vào SieuNhanToi hoặc tool khác**:
  Sử dụng endpoint sau để lấy danh sách proxy dạng text thô:
  ```
  https://autoproxy-collector.onrender.com/api/proxies?format=text
  ```

---

## Test thử Web Dashboard tại máy tính (Local)

Nếu muốn xem trước giao diện Web Dashboard trên máy tính cá nhân trước khi deploy:
- Bấm đúp vào file **`run_web.bat`**.
- Trình duyệt sẽ tự động mở trang: `http://localhost:8000`!
