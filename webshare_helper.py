import time
import os
import re
from playwright.sync_api import Page
import config

class WebshareHelper:
    def __init__(self, page: Page):
        self.page = page
        self.captured_proxies = []
        self.auth_token = None
        self._setup_network_interception()

    def _setup_network_interception(self):
        """
        Lắng nghe toàn bộ network traffic giữa trình duyệt và máy chủ Webshare.
        Khi trang Proxy List tải, Webshare tự động gọi API /api/v2/proxy/list/.
        Network interception bắt trực tiếp dữ liệu JSON gốc trả về 10 proxy đầy đủ thông tin (IP, Port, User, Pass).
        """
        def on_request(request):
            try:
                auth = request.headers.get("authorization", "")
                if auth and ("token" in auth.lower() or "bearer" in auth.lower()):
                    self.auth_token = auth
            except Exception:
                pass

        def on_response(response):
            try:
                url = response.url.lower()
                if ("proxy/list" in url or "api/v2/proxy" in url) and response.status == 200:
                    ct = response.headers.get("content-type", "")
                    if "json" in ct:
                        data = response.json()
                        if isinstance(data, dict) and "results" in data and isinstance(data["results"], list):
                            new_proxies = []
                            for p in data["results"]:
                                ip = p.get("proxy_address") or p.get("ip")
                                port = p.get("port")
                                u = p.get("username")
                                pwd = p.get("password")
                                if ip and port:
                                    if u and pwd:
                                        new_proxies.append(f"{ip}:{port}:{u}:{pwd}")
                                    else:
                                        new_proxies.append(f"{ip}:{port}")
                            if len(new_proxies) > len(self.captured_proxies):
                                self.captured_proxies = new_proxies
                                print(f"[WEBSHARE - NETWORK] ✅ Đã tóm được {len(new_proxies)} proxy trực tiếp từ API Webshare!")
            except Exception:
                pass

        self.page.on("request", on_request)
        self.page.on("response", on_response)

    def register(self, email: str, password: str = config.WEBSHARE_PASSWORD) -> bool:
        """
        B2: Vào webshare đăng ký với email vừa tạo và password cố định, tích chọn I agree rồi Sign Up.
        """
        print(f"[WEBSHARE] Đang truy cập trang đăng ký: {config.WEBSHARE_REGISTER_URL}")
        self.page.goto(config.WEBSHARE_REGISTER_URL, wait_until="networkidle", timeout=config.DEFAULT_TIMEOUT)
        self.page.wait_for_timeout(2000)

        # 1. Nhập Email
        print(f"[WEBSHARE] Nhập email: {email}")
        email_selector = "input[data-testid='email-input'], #email-input, input[type='email']"
        self.page.wait_for_selector(email_selector, timeout=config.DEFAULT_TIMEOUT)
        self.page.fill(email_selector, email)
        self.page.wait_for_timeout(500)

        # 2. Nhập Mật khẩu
        print("[WEBSHARE] Nhập mật khẩu...")
        pass_selector = "input[data-testid='password-input'], input[type='password']"
        self.page.wait_for_selector(pass_selector, timeout=config.DEFAULT_TIMEOUT)
        self.page.fill(pass_selector, password)
        self.page.wait_for_timeout(500)

        # 3. Tích ô I agree (data-testid='tos-checkbox')
        print("[WEBSHARE] Tích vào ô 'I agree'...")
        tos_input = self.page.locator("[data-testid='tos-checkbox'] input, input[type='checkbox']").first
        tos_box = self.page.locator("[data-testid='tos-checkbox']").first

        tos_box.scroll_into_view_if_needed()
        self.page.wait_for_timeout(500)

        for attempt in range(5):
            try:
                tos_input.check(force=True)
            except Exception:
                pass
            if not tos_input.is_checked():
                try:
                    self.page.evaluate("() => { const el = document.querySelector('[data-testid=\"tos-checkbox\"] input') || document.querySelector('input[type=\"checkbox\"]'); if (el) { el.checked = true; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); } }")
                except Exception:
                    pass
            self.page.wait_for_timeout(300)
            if tos_input.is_checked():
                break

        is_checked = tos_input.is_checked()
        print(f"[WEBSHARE] Trạng thái ô 'I agree': {'ĐÃ TÍCH THÀNH CÔNG (True)' if is_checked else 'CHƯA TÍCH (False)'}")
        self.page.wait_for_timeout(500)

        # 4. Bấm nút Sign Up With Email
        print("[WEBSHARE] Click nút 'Sign Up With Email'...")
        signup_btn = self.page.locator("button[data-testid='signup-button']")
        if signup_btn.count() > 0:
            signup_btn.first.click()
        else:
            self.page.locator("button:has-text('Sign Up With Email')").first.click()

        print("[WEBSHARE] Đã click nút đăng ký. Chờ phản hồi từ máy chủ...")
        
        captcha_notified = False
        for sec in range(90):
            curr_url = self.page.url
            if "dashboard.webshare.io" in curr_url and "register" not in curr_url and "accounts.google.com" not in curr_url:
                print(f"[WEBSHARE] Đăng ký thành công! URL hiện tại: {curr_url}")
                self.page.wait_for_timeout(3000)
                return True

            if not captcha_notified:
                captcha_frames = self.page.locator("iframe[title*='recaptcha challenge' i], iframe[src*='recaptcha/api2/bframe' i]")
                if captcha_frames.count() > 0:
                    print("\n" + "=" * 60)
                    print("[WEBSHARE] ⚠️ PHÁT HIỆN BẢNG GOOGLE CAPTCHA (CHỌN HÌNH ẢNH)!")
                    print(">>> Vui lòng click chọn hình ảnh trên cửa sổ Chrome để tiếp tục...")
                    print("=" * 60 + "\n")
                    captcha_notified = True

            error_elements = self.page.locator(".Mui-error, [role='alert'], .MuiFormHelperText-root, .MuiAlert-message, p.Mui-error").all_inner_texts()
            clean_errors = [e.strip() for e in error_elements if e.strip() and e.strip() not in ("Email", "Password")]
            if clean_errors and sec > 5 and not captcha_notified:
                print(f"[WEBSHARE PHẢN HỒI LỖI TRÊN MÀN HÌNH]: {' | '.join(clean_errors)}")
                self.page.screenshot(path="debug_register.png")
                break

            self.page.wait_for_timeout(1000)

        print(f"[WEBSHARE] Kết thúc chờ. URL hiện tại: {self.page.url}")
        self.page.screenshot(path="debug_register.png")
        return True

    def _dismiss_onboarding_and_go_to_proxylist(self):
        """
        Xử lý popup hướng dẫn ban đầu ('Send your first proxy request').
        Bấm nút 'Go To Proxy List' để chuyển trang và mở khóa danh sách 10 proxy.
        """
        print("[WEBSHARE] Đang kiểm tra popup hướng dẫn ('Send your first proxy request')...")
        
        # Bấm nút 'Go To Proxy List' bằng Javascript để không bị subtree intercepts pointer events
        for _ in range(8):
            clicked = self.page.evaluate("""() => {
                const buttons = Array.from(document.querySelectorAll('button, a'));
                const btn = buttons.find(b => b.innerText && b.innerText.toLowerCase().includes('go to proxy list'));
                if (btn) {
                    btn.click();
                    return true;
                }
                return false;
            }""")
            if clicked:
                print("[WEBSHARE] ✅ Đã click nút 'Go To Proxy List' trên popup!")
                self.page.wait_for_timeout(3000)
                break
            
            # Thử bấm Escape
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(800)

        # Xóa dialog/backdrop nếu vẫn còn cản trở DOM
        try:
            self.page.evaluate("""() => {
                const dialogs = document.querySelectorAll('.MuiDialog-root, .MuiBackdrop-root, .MuiModal-root');
                dialogs.forEach(d => {
                    if (d.innerText && d.innerText.includes('Send your first proxy request')) {
                        d.remove();
                    }
                });
            }""")
        except Exception:
            pass

    def export_proxies(self, output_file: str = config.OUTPUT_PROXY_FILE) -> list:
        """
        B3: Vào Free -> Proxy List để lấy đầy đủ 10 proxy và ghi vào file.
        """
        print("\n[WEBSHARE] Bắt đầu quá trình lấy đầy đủ 10 proxy...")
        self.page.wait_for_timeout(2000)

        # 1. Xử lý popup và bấm Go To Proxy List
        self._dismiss_onboarding_and_go_to_proxylist()

        # 2. Đảm bảo điều hướng chính xác vào trang /proxy/list
        if "proxy/list" not in self.page.url:
            print("[WEBSHARE] Đang điều hướng đến trang Proxy List...")
            # Click trên giao diện sidebar / menu nếu có
            clicked_nav = self.page.evaluate("""() => {
                const links = Array.from(document.querySelectorAll('a, button'));
                const link = links.find(l => (l.getAttribute('href') && l.getAttribute('href').includes('proxy/list')) || (l.innerText && l.innerText.trim() === 'Proxy List'));
                if (link) { link.click(); return true; }
                return false;
            }""")
            if not clicked_nav:
                self.page.goto(config.WEBSHARE_PROXYLIST_URL, wait_until="networkidle", timeout=20000)
            self.page.wait_for_timeout(4000)

        print(f"[WEBSHARE] Đang ở trang: {self.page.url}")

        # Lấy thông tin xác thực mặc định (username, password) nếu có trên trang
        default_user = None
        default_pass = None
        try:
            auth_info = self.page.evaluate("""() => {
                let user = '';
                let pass = '';
                const inputs = Array.from(document.querySelectorAll('input'));
                // Tìm input username / password proxy
                inputs.forEach(inp => {
                    const label = (inp.getAttribute('aria-label') || inp.getAttribute('name') || inp.id || '').toLowerCase();
                    if (label.includes('user')) user = inp.value;
                    if (label.includes('pass')) pass = inp.value;
                });
                return { user, pass };
            }""")
            if auth_info:
                default_user = auth_info.get("user")
                default_pass = auth_info.get("pass")
        except Exception:
            pass

        # CHỜ NETWORK INTERCEPTION (CÁCH 1)
        print("[WEBSHARE] [Cách 1] Kiểm tra dữ liệu 10 proxy từ Network API...")
        for _ in range(8):
            if len(self.captured_proxies) >= 10:
                break
            self.page.wait_for_timeout(1000)

        proxies = list(self.captured_proxies)

        # CÁCH 2: Gọi trực tiếp API nội bộ Webshare bằng token từ phiên
        if len(proxies) < 10:
            print("[WEBSHARE] [Cách 2] Gọi API nội bộ bằng session token...")
            try:
                token_to_use = self.auth_token or ''
                api_res = self.page.evaluate(r"""
                    async (tokenArg) => {
                        let token = tokenArg;
                        if (!token) {
                            try {
                                for (let i = 0; i < localStorage.length; i++) {
                                    const k = localStorage.key(i);
                                    const v = localStorage.getItem(k);
                                    const m = v.match(/[a-f0-9]{40}/i) || v.match(/"token":\s*"([^"]+)"/i);
                                    if (m) {
                                        token = `Token ${m[1] || m[0]}`;
                                        break;
                                    }
                                }
                            } catch(e) {}
                        }

                        const endpoints = [
                            'https://proxy.webshare.io/api/v2/proxy/list/?mode=direct&page=1&page_size=25',
                            '/api/v2/proxy/list/?mode=direct&page=1&page_size=25',
                            'https://proxy.webshare.io/api/v2/proxy/list/',
                            '/api/v2/proxy/list/'
                        ];
                        
                        const headers = token ? { 'Authorization': token } : {};

                        for (const ep of endpoints) {
                            try {
                                const res = await fetch(ep, { headers, credentials: 'include' });
                                if (res.ok) {
                                    const data = await res.json();
                                    if (data.results && data.results.length > 0) {
                                        return data.results.map(p => {
                                            if (p.username && p.password) {
                                                return `${p.proxy_address}:${p.port}:${p.username}:${p.password}`;
                                            }
                                            return `${p.proxy_address}:${p.port}`;
                                        });
                                    }
                                }
                            } catch(e) {}
                        }
                        return [];
                    }
                """, token_to_use)
                if api_res and len(api_res) >= 10:
                    print(f"[WEBSHARE] Lấy thành công {len(api_res)} proxy qua API trực tiếp!")
                    proxies = api_res
            except Exception as e:
                print(f"[WEBSHARE] Lưu ý gọi API: {e}")

        # CÁCH 3: Tải file danh sách qua nút Download
        if len(proxies) < 10:
            print("[WEBSHARE] [Cách 3] Thử tải file TXT danh sách proxy qua nút Download...")
            try:
                with self.page.expect_download(timeout=8000) as download_info:
                    # Click Download bằng JS
                    self.page.evaluate("""() => {
                        const btns = Array.from(document.querySelectorAll('button, a'));
                        const b = btns.find(x => x.innerText && x.innerText.trim().toLowerCase() === 'download');
                        if (b) b.click();
                    }""")
                    self.page.wait_for_timeout(1000)
                    # Click TXT / Download format
                    self.page.evaluate("""() => {
                        const items = Array.from(document.querySelectorAll('li, button, a, [role="menuitem"], span'));
                        const it = items.find(x => x.innerText && (x.innerText.toLowerCase().includes('text') || x.innerText.toLowerCase().includes('txt')));
                        if (it) it.click();
                    }""")
                download = download_info.value
                download_path = download.path()
                if download_path and os.path.exists(download_path):
                    with open(download_path, "r", encoding="utf-8") as f:
                        lines = [line.strip() for line in f if line.strip() and ":" in line]
                    if len(lines) >= 10:
                        print(f"[WEBSHARE] Đã tải file TXT thành công với {len(lines)} proxies!")
                        proxies = lines
            except Exception as ex:
                print(f"[WEBSHARE] Tải file download: {ex}")

        # CÁCH 4: Quét toàn bộ bảng HTML table trên trang
        if len(proxies) < 10:
            print("[WEBSHARE] [Cách 4] Quét các hàng trong bảng danh sách proxy...")
            self.page.wait_for_timeout(2000)
            rows = self.page.locator("table tbody tr, [role='row']").all()
            table_proxies = []
            for row in rows:
                try:
                    cells = [c.strip() for c in row.locator("td").all_inner_texts() if c.strip()]
                    ip = None
                    port = None
                    for c in cells:
                        if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", c):
                            ip = c
                        elif c.isdigit() and len(c) in (2, 4, 5):
                            port = c
                    if ip and port:
                        if default_user and default_pass:
                            table_proxies.append(f"{ip}:{port}:{default_user}:{default_pass}")
                        else:
                            table_proxies.append(f"{ip}:{port}")
                except Exception:
                    pass
            if len(table_proxies) >= 10:
                print(f"[WEBSHARE] Quét bảng thành công: {len(table_proxies)} proxies!")
                proxies = table_proxies

        # CÁCH 5: Quét toàn bộ nội dung văn bản trang
        if len(proxies) < 10:
            print("[WEBSHARE] [Cách 5] Quét toàn bộ nội dung trang...")
            page_text = self.page.inner_text("body")
            
            # Tìm curl proxy nếu có: curl --proxy "http://user:pass@ip:port/"
            curl_matches = re.findall(r"http://([^:]+):([^@]+)@([\d\.]+):(\d+)", page_text)
            for cm in curl_matches:
                p_str = f"{cm[2]}:{cm[3]}:{cm[0]}:{cm[1]}"
                if p_str not in proxies:
                    proxies.append(p_str)

            # Tìm ip:port thông thường
            raw_ips = re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}:\d{2,5}\b", page_text)
            for rip in raw_ips:
                if not rip.startswith("0.0.0.0") and not rip.startswith("127.0.0.1"):
                    # Kiểm tra xem IP này đã có trong proxies với dạng user:pass chưa
                    already_has = any(p.startswith(rip) for p in proxies)
                    if not already_has:
                        if default_user and default_pass:
                            proxies.append(f"{rip}:{default_user}:{default_pass}")
                        else:
                            proxies.append(rip)

        # Lọc lấy đúng 10 proxy chuẩn (loại bỏ trùng lặp)
        final_proxies = []
        seen_ip_ports = set()
        for p in proxies:
            # Loại bỏ lệnh curl nếu bị lẫn
            if "curl " in p:
                match = re.search(r"http://([^:]+):([^@]+)@([\d\.]+):(\d+)", p)
                if match:
                    p = f"{match.group(3)}:{match.group(4)}:{match.group(1)}:{match.group(2)}"
                else:
                    ip_match = re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}:\d{2,5}\b", p)
                    if ip_match:
                        p = ip_match.group(0)

            # Tách ip:port để tránh ghi đúp 1 proxy (1 cái có pass, 1 cái không pass)
            parts = p.split(":")
            if len(parts) >= 2:
                ip_port = f"{parts[0]}:{parts[1]}"
                if ip_port not in seen_ip_ports:
                    seen_ip_ports.add(ip_port)
                    final_proxies.append(p)
            
            if len(final_proxies) == 10:
                break

        print("\n" + "=" * 60)
        print(f"[KẾT QUẢ] Số lượng proxy thu thập được: {len(final_proxies)}/10")
        for idx, p in enumerate(final_proxies, 1):
            print(f"  {idx}. {p}")
        print("=" * 60)

        # Ghi danh sách vào file (tích lũy và chống trùng lặp qua các vòng lặp)
        if final_proxies:
            existing_proxies = []
            if os.path.exists(output_file):
                with open(output_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            existing_proxies.append(line)

            # Gộp và loại bỏ trùng lặp (chỉ bỏ qua nếu trùng cả IP:PORT:USER:PASS)
            all_saved = list(existing_proxies)
            new_added = 0
            for p in final_proxies:
                if p not in all_saved:
                    all_saved.append(p)
                    new_added += 1

            with open(output_file, "w", encoding="utf-8") as f:
                for p in all_saved:
                    f.write(p + "\n")

            print(f"[SUCCESS] Đã lưu thành công! (+{new_added} proxy mới). Tổng cộng đang có {len(all_saved)} proxy trong file: {os.path.abspath(output_file)}")
        else:
            print("[CANH BAO] Chưa lấy được proxy. Đang lưu ảnh kiểm tra tại debug_proxylist.png...")
            self.page.screenshot(path="debug_proxylist.png")

        return final_proxies

    def logout(self):
        """
        B4: Đăng xuất tài khoản Webshare và xóa sạch cookies/session trước khi tạo tài khoản mới.
        """
        print("[WEBSHARE] Đang đăng xuất tài khoản cũ trên Webshare...")
        try:
            self.page.goto("https://dashboard.webshare.io/logout", timeout=8000)
            self.page.wait_for_timeout(1000)
        except Exception:
            pass

        try:
            self.page.evaluate("() => { try { localStorage.clear(); sessionStorage.clear(); } catch(e){} }")
        except Exception:
            pass

        try:
            self.page.context.clear_cookies()
        except Exception:
            pass
        print("[WEBSHARE] Đã đăng xuất và xóa sạch session/cookie tài khoản cũ thành công!")
