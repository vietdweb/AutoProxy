import sys
import os
import time
from playwright.sync_api import sync_playwright

import config
from otpmail_helper import OtpMailHelper
from webshare_helper import WebshareHelper

def run():
    print("=" * 70)
    print("   HỆ THỐNG TỰ ĐỘNG ĐĂNG KÝ VÀ LẤY PROXY TỪ WEBSHARE (VÒNG LẶP B1 -> B4)")
    print("   - OTPMail chạy 100% qua REST API (không mở tab, tự xóa dọn dẹp)")
    print("   - Tự động đăng xuất & làm sạch session trước mỗi vòng lặp mới")
    print("=" * 70)

    loop_target = getattr(config, "LOOP_COUNT", 0)
    delay_between = getattr(config, "DELAY_BETWEEN_LOOPS", 3)

    loop_idx = 0

    with sync_playwright() as p:
        launch_kwargs = {
            "headless": config.HEADLESS_MODE,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
                "--start-maximized"
            ]
        }
        if getattr(config, "BROWSER_CHANNEL", None):
            launch_kwargs["channel"] = config.BROWSER_CHANNEL

        try:
            browser = p.chromium.launch(**launch_kwargs)
        except Exception:
            launch_kwargs.pop("channel", None)
            browser = p.chromium.launch(**launch_kwargs)

        otp_helper = OtpMailHelper()

        try:
            while True:
                loop_idx += 1
                loop_info = f"VÒNG LẶP THỨ {loop_idx}" + (f" / {loop_target}" if loop_target > 0 else " (Nhấn Ctrl+C để dừng)")
                print("\n" + "=" * 70)
                print(f">>> [BẮT ĐẦU {loop_info}]")
                print("=" * 70)

                # BƯỚC 1: Lấy email từ otpmail.vn thuần qua requests (không cần Chrome)
                print(f"\n>>> [BƯỚC 1]: Khởi tạo email mới tại https://otpmail.vn/ qua REST API...")
                try:
                    temp_email = otp_helper.create_email()
                except Exception as e:
                    print(f"[LỖI] Không thể tạo email từ OTPMail: {e}. Thử lại sau 5 giây...")
                    otp_helper.cleanup()
                    time.sleep(5)
                    continue

                # Tạo browser context mới hoàn toàn sạch cookies & session Webshare
                context = browser.new_context(
                    no_viewport=True,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                )
                context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

                tab_webshare = context.new_page()
                webshare_helper = WebshareHelper(tab_webshare)

                try:
                    # BƯỚC 2: Mở Webshare đăng ký tài khoản
                    print(f"\n>>> [BƯỚC 2]: Mở Webshare đăng ký tài khoản mới với email: {temp_email}")
                    webshare_helper.register(email=temp_email, password=config.WEBSHARE_PASSWORD)

                    # Kiểm tra hộp thư OTPMail xem có thư xác thực từ Webshare
                    print("\n>>> Kiểm tra hộp thư OTPMail xem có thư xác thực từ Webshare...")
                    activate_link = otp_helper.wait_for_activation_link(timeout_sec=15)
                    if activate_link:
                        print(f"[XÁC THỰC] Tự động kích hoạt tài khoản qua link: {activate_link}")
                        try:
                            tab_webshare.goto(activate_link, wait_until="networkidle", timeout=config.DEFAULT_TIMEOUT)
                            tab_webshare.wait_for_timeout(3000)
                        except Exception as e:
                            print(f"[XÁC THỰC] Lưu ý khi mở link xác thực: {e}")

                    # BƯỚC 3: Lấy danh sách 10 proxy và lưu tích lũy vào file
                    print(f"\n>>> [BƯỚC 3]: Lấy danh sách 10 proxy và ghi tiếp vào {config.OUTPUT_PROXY_FILE}")
                    webshare_helper.export_proxies(output_file=config.OUTPUT_PROXY_FILE)

                except Exception as ex:
                    print(f"[LỖI TRONG VÒNG LẶP {loop_idx}]: {ex}")

                finally:
                    # BƯỚC 4: Đăng xuất tài khoản Webshare và xóa tab OTPMail cũ trước khi lặp lại
                    print(f"\n>>> [BƯỚC 4]: Chuẩn bị cho lần chạy tiếp theo:")
                    print("  1. Đăng xuất tài khoản Webshare vừa tạo...")
                    try:
                        webshare_helper.logout()
                    except Exception:
                        pass

                    print("  2. Đóng context trình duyệt (xóa sạch 100% cookie, cache, local storage)...")
                    try:
                        context.close()
                    except Exception:
                        pass

                    print("  3. Giải phóng tab OTPMail cũ và xóa hòm thư (tránh bị lỗi đợi 10 phút)...")
                    try:
                        otp_helper.cleanup()
                    except Exception:
                        pass

                if loop_target > 0 and loop_idx >= loop_target:
                    print(f"\n[HOÀN TẤT] Đã đạt giới hạn {loop_target} vòng lặp đã cấu hình!")
                    break

                print(f"\n[NGHỈ] Tạm nghỉ {delay_between} giây trước khi bắt đầu vòng lặp tiếp theo...")
                time.sleep(delay_between)

        except KeyboardInterrupt:
            print("\n[DỪNG] Người dùng đã dừng chương trình bằng Ctrl+C.")
        finally:
            try:
                browser.close()
            except Exception:
                pass

    print(f"\n[THÀNH CÔNG] Toàn bộ quy trình đã kết thúc an toàn. File lưu proxy: {os.path.abspath(config.OUTPUT_PROXY_FILE)}")

if __name__ == "__main__":
    run()
