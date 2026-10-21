import requests
import random
import string
import time
import re
import uuid
from typing import Optional, List
import config

class OtpMailHelper:
    """
    Cơ chế tương tác OTPMAIL.VN thuần túy qua HTTP API (requests)
    Tham khảo từ dự án SieuNhanToi (D:\\JOB-Ngoai\\SieuNhanToi\\core\\account_creator.py):
    - KHÔNG cần mở bất kỳ tab Chrome nào.
    - Gọi API /api/domains và /api/generate trực tiếp.
    - Tự động xóa hộp thư (/api/inbox/{email}) và giải phóng tab (/api/release-device)
      để không bao giờ bị dính lỗi chờ 10 phút!
    - Tự động kiểm tra chống trùng email cũ giữa các vòng lặp.
    """
    def __init__(self, base_url: str = config.OTPMAIL_URL):
        self.base_url = base_url.rstrip("/")
        self.current_email: Optional[str] = None
        self.current_tab_id: Optional[str] = None
        self.used_emails = set()
        self._init_session()

    def _init_session(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/",
            "Content-Type": "application/json"
        })

    def get_domains(self) -> List[str]:
        """Lấy danh sách domain đang hoạt động từ OTPMAIL.VN"""
        fallback_domains = ["taphoammo.fit", "zovnct.fit", "jpmfetv.biz", "otpmail.one"]
        try:
            resp = self.session.get(f"{self.base_url}/api/domains", timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    domains = [
                        str(d.get("domain", "")).strip().lower() 
                        for d in data.get("data", []) 
                        if d.get("is_active", True)
                    ]
                    if domains:
                        return domains
        except Exception as e:
            print(f"[OTPMAIL] Lưu ý khi lấy danh sách domain: {e}")
        return fallback_domains

    def create_email(self, prefix: str = "") -> str:
        """
        B1: Tạo email mới qua REST API không cần mở tab Chrome.
        Tự động phát hiện và chặn tái sử dụng email cũ của vòng lặp trước.
        """
        domains = self.get_domains()

        for attempt in range(4):
            # Dùng UUID chuẩn khớp với crypto.randomUUID() trên trình duyệt thật
            tab_id = str(uuid.uuid4())
            self.current_tab_id = tab_id

            clean_prefix = re.sub(r'[^a-zA-Z0-9]', '', prefix.lower()) if prefix else ""
            if not clean_prefix or attempt > 0:
                clean_prefix = f"user{uuid.uuid4().hex[:7]}"

            domain = random.choice(domains)

            print(f"[OTPMAIL] Đang gọi API tạo email với prefix '{clean_prefix}' @ '{domain}'...")
            payload = {
                "prefix": clean_prefix,
                "domain": domain,
                "tab_id": tab_id
            }

            try:
                resp = self.session.post(f"{self.base_url}/api/generate", json=payload, timeout=12)
            except Exception as e:
                print(f"[OTPMAIL] Lỗi kết nối API: {e}. Thử lại...")
                time.sleep(2)
                continue

            if resp.status_code == 200:
                data = resp.json()
                if data.get("success") and "data" in data and "email" in data["data"]:
                    email = data["data"]["email"]
                    is_reused = data.get("reused") or data.get("data", {}).get("reused") or False

                    # Nếu OTPMail vẫn giữ email của tài khoản vòng trước
                    if (is_reused or email in self.used_emails) and self.used_emails:
                        print(f"[OTPMAIL ⚠️ CẢNH BÁO] Máy chủ đang giữ email cũ [{email}] đã dùng ở vòng trước (reused={is_reused})!")
                        print("[OTPMAIL] Gửi lệnh giải phóng thiết bị/tab cũ và chờ 3s lấy email mới toanh...")
                        try:
                            self.session.post(f"{self.base_url}/api/release-device", json={"tab_id": tab_id}, timeout=5)
                            self.session.delete(f"{self.base_url}/api/inbox/{email}", timeout=5)
                        except Exception:
                            pass
                        time.sleep(3)
                        continue

                    self.current_email = email
                    self.used_emails.add(email)
                    print(f"[OTPMAIL - REQUESTS] Tạo email MỚI thành công 100% qua API: {email}")
                    return email
                else:
                    print(f"[OTPMAIL] Phản hồi bất thường: {data}")
            else:
                print(f"[OTPMAIL] HTTP Lỗi: {resp.status_code}")

            time.sleep(2)

        raise Exception("Không thể tạo email mới từ OTPMail sau nhiều lần thử.")

    def cleanup(self):
        """
        Giải phóng tab và xóa hộp thư để không bị khóa 10 phút.
        Đồng thời reset session HTTP cho lần chạy tiếp theo.
        """
        if self.current_email:
            try:
                del_resp = self.session.delete(f"{self.base_url}/api/inbox/{self.current_email}", timeout=5)
                print(f"[OTPMAIL] Đã xóa hòm thư cũ [{self.current_email}]: HTTP {del_resp.status_code}")
            except Exception as e:
                print(f"[OTPMAIL] Lưu ý xóa hòm thư: {e}")
            self.current_email = None

        if self.current_tab_id:
            try:
                rel_resp = self.session.post(f"{self.base_url}/api/release-device", json={"tab_id": self.current_tab_id}, timeout=5)
                print(f"[OTPMAIL] Đã giải phóng tab thiết bị [{self.current_tab_id}]: HTTP {rel_resp.status_code}")
            except Exception as e:
                print(f"[OTPMAIL] Lưu ý giải phóng tab: {e}")
            self.current_tab_id = None

        try:
            self.session.close()
        except Exception:
            pass

        self._init_session()
        print("[OTPMAIL] Đã dọn dẹp hòm thư, giải phóng tab cũ và tạo session mới (chống chờ 10 phút).")

    def wait_for_activation_link(self, timeout_sec: int = 30) -> Optional[str]:
        """Lắng nghe hộp thư qua API /api/inbox/{email} để lấy link xác nhận nếu Webshare yêu cầu"""
        if not self.current_email:
            return None

        print(f"[OTPMAIL] Lắng nghe hộp thư API cho [{self.current_email}] trong tối đa {timeout_sec}s...")
        start_time = time.time()
        while time.time() - start_time < timeout_sec:
            time.sleep(2.0)
            try:
                inbox_url = f"{self.base_url}/api/inbox/{self.current_email}"
                resp = self.session.get(inbox_url, timeout=8)
                if resp.status_code == 200:
                    data = resp.json()
                    messages = data.get("data", [])
                    if messages:
                        for msg in messages:
                            msg_id = msg.get("id")
                            detail_resp = self.session.get(f"{self.base_url}/api/message/{msg_id}", timeout=8)
                            if detail_resp.status_code == 200:
                                detail_data = detail_resp.json().get("data", {})
                                full_text = f"{detail_data.get('body_html', '')} {detail_data.get('body_text', '')}"
                                links = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', full_text)
                                for link in links:
                                    if "webshare" in link.lower() and ("verify" in link.lower() or "confirm" in link.lower() or "activate" in link.lower()):
                                        print(f"[OTPMAIL] Tìm thấy link xác thực: {link}")
                                        return link
            except Exception:
                pass
        return None
