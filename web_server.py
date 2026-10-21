import os
import sys
import time
import json
import threading
from typing import Optional, List
from collections import deque
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from playwright.sync_api import sync_playwright

import config
from otpmail_helper import OtpMailHelper
from webshare_helper import WebshareHelper

# Cấu hình UTF-8 cho Windows và Linux
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

app = FastAPI(title="AutoProxy Cloud Collector Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# QUẢN LÝ LOG THỜI GIAN THỰC
# -----------------------------------------------------------------------------
class LogManager:
    def __init__(self, max_history=600):
        self.logs = deque(maxlen=max_history)
        self.lock = threading.Lock()

    def add(self, message: str, level: str = "info"):
        now_str = datetime.now().strftime("%H:%M:%S")
        entry = {
            "time": now_str,
            "message": message,
            "level": level
        }
        with self.lock:
            self.logs.append(entry)
        try:
            print(f"[{now_str}] {message}", flush=True)
        except Exception:
            pass

    def get_all(self):
        with self.lock:
            return list(self.logs)

log_manager = LogManager()

# -----------------------------------------------------------------------------
# TIẾN TRÌNH THU THẬP PROXY CHẠY NGẦM
# -----------------------------------------------------------------------------
class ProxyWorker:
    def __init__(self):
        self.is_running = False
        self.should_stop = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.current_loop = 0
        self.last_email = ""
        self.last_error = ""

    def start(self):
        if self.is_running:
            return False
        self.is_running = True
        self.should_stop.clear()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        log_manager.add("▶ Đã kích hoạt tiến trình thu thập proxy tự động!", "success")
        return True

    def stop(self):
        if not self.is_running:
            return False
        self.is_running = False
        self.should_stop.set()
        log_manager.add("⏹ Đã gửi lệnh tạm dừng. Tiến trình sẽ dừng sau khi kết thúc lượt hiện tại.", "warn")
        return True

    def _run_loop(self):
        log_manager.add("Khởi tạo hệ thống tự động đăng ký Webshare & OTPMail...", "info")
        otp_helper = OtpMailHelper()

        launch_kwargs = {
            "headless": config.HEADLESS_MODE,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
                "--disable-dev-shm-usage"
            ]
        }
        if getattr(config, "BROWSER_CHANNEL", None):
            launch_kwargs["channel"] = config.BROWSER_CHANNEL

        try:
            with sync_playwright() as p:
                browser = None
                for attempt in range(2):
                    try:
                        browser = p.chromium.launch(**launch_kwargs)
                        break
                    except Exception as launch_err:
                        err_str = str(launch_err)
                        launch_kwargs.pop("channel", None)
                        if "executable doesn't exist" in err_str.lower() or "playwright install" in err_str.lower() or attempt == 0:
                            log_manager.add("Đang tự động tải bộ cài Chromium vào máy chủ Render...", "warn")
                            import subprocess
                            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)
                        else:
                            raise launch_err

                if not browser:
                    browser = p.chromium.launch(**launch_kwargs)

                log_manager.add("Trình duyệt Chromium đã sẵn sàng hoạt động.", "success")

                while not self.should_stop.is_set():
                    self.current_loop += 1
                    log_manager.add(f"=== BẮT ĐẦU VÒNG LẶP THỨ {self.current_loop} ===", "info")

                    # BƯỚC 1: Lấy email từ OTPMail qua API
                    try:
                        temp_email = otp_helper.create_email()
                        self.last_email = temp_email
                        log_manager.add(f"[OTPMAIL] Tạo thành công email: {temp_email}", "success")
                    except Exception as e:
                        log_manager.add(f"[LỖI OTPMAIL] {e}. Thử lại sau 5s...", "error")
                        otp_helper.cleanup()
                        time.sleep(5)
                        continue

                    # Tạo Browser Context sạch cách ly 100%
                    context = browser.new_context(
                        no_viewport=True,
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    )
                    context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                    tab_webshare = context.new_page()
                    webshare_helper = WebshareHelper(tab_webshare)

                    try:
                        # BƯỚC 2: Đăng ký tài khoản Webshare
                        log_manager.add(f"[WEBSHARE] Đăng ký tài khoản mới với email {temp_email}...", "info")
                        webshare_helper.register(email=temp_email, password=config.WEBSHARE_PASSWORD)

                        # Chờ link xác nhận từ OTPMail
                        log_manager.add("[OTPMAIL] Đang lắng nghe thư xác thực từ Webshare...", "info")
                        activate_link = otp_helper.wait_for_activation_link(timeout_sec=15)
                        if activate_link:
                            log_manager.add(f"[XÁC THỰC] Kích hoạt tài khoản qua link...", "success")
                            try:
                                tab_webshare.goto(activate_link, wait_until="networkidle", timeout=config.DEFAULT_TIMEOUT)
                                tab_webshare.wait_for_timeout(3000)
                            except Exception as ex:
                                log_manager.add(f"[XÁC THỰC] {ex}", "warn")

                        # BƯỚC 3: Trích xuất 10 proxy và lưu vào file
                        log_manager.add("[WEBSHARE] Đang lấy danh sách 10 proxy...", "info")
                        new_proxies = webshare_helper.export_proxies(output_file=config.OUTPUT_PROXY_FILE)
                        if new_proxies:
                            log_manager.add(f"[THÀNH CÔNG] Thu thập được {len(new_proxies)} proxy mới ở vòng {self.current_loop}!", "success")
                        else:
                            log_manager.add("[CẢNH BÁO] Không lấy được proxy ở vòng lặp này.", "warn")

                    except Exception as e:
                        self.last_error = str(e)
                        log_manager.add(f"[LỖI QUY TRÌNH] {e}", "error")

                    finally:
                        # BƯỚC 4: Dọn dẹp context và giải phóng tab OTPMail
                        try:
                            webshare_helper.logout()
                        except Exception:
                            pass
                        try:
                            context.close()
                        except Exception:
                            pass
                        try:
                            otp_helper.cleanup()
                        except Exception:
                            pass

                    # Kiểm tra dừng
                    if self.should_stop.is_set():
                        break

                    delay = getattr(config, "DELAY_BETWEEN_LOOPS", 3)
                    time.sleep(delay)

                browser.close()
        except Exception as e:
            self.last_error = str(e)
            log_manager.add(f"[LỖI HỆ THỐNG] {e}", "error")
        finally:
            self.is_running = False
            log_manager.add("Tiến trình thu thập proxy đã dừng an toàn.", "info")

worker = ProxyWorker()

# -----------------------------------------------------------------------------
# CÁC API ENDPOINTS
# -----------------------------------------------------------------------------
@app.get("/healthz")
async def healthz():
    return {"status": "ok", "app": "AutoProxy Cloud Collector", "running": worker.is_running}

@app.get("/api/status")
async def get_status():
    total_proxies = 0
    if os.path.exists(config.OUTPUT_PROXY_FILE):
        try:
            with open(config.OUTPUT_PROXY_FILE, "r", encoding="utf-8") as f:
                total_proxies = sum(1 for line in f if line.strip())
        except Exception:
            pass

    return {
        "is_running": worker.is_running,
        "current_loop": worker.current_loop,
        "total_proxies": total_proxies,
        "last_email": worker.last_email,
        "last_error": worker.last_error
    }

@app.post("/api/start")
async def start_worker():
    success = worker.start()
    return {"success": success, "is_running": worker.is_running}

@app.post("/api/stop")
async def stop_worker():
    success = worker.stop()
    return {"success": success, "is_running": worker.is_running}

@app.get("/api/logs")
async def get_logs():
    return {"logs": log_manager.get_all()}

@app.get("/api/proxies")
async def get_proxies(format: str = "text"):
    """
    Endpoint linh hoạt:
    - ?format=text : Trả về raw text (IP:PORT:USER:PASS) mỗi dòng một proxy. Dùng trực tiếp cho bot/tool khác!
    - ?format=json : Trả về mảng JSON.
    """
    lines = []
    if os.path.exists(config.OUTPUT_PROXY_FILE):
        with open(config.OUTPUT_PROXY_FILE, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]

    if format.lower() == "text":
        return Response(content="\n".join(lines), media_type="text/plain")

    # JSON format
    parsed = []
    for line in lines:
        parts = line.split(":")
        if len(parts) >= 4:
            parsed.append({
                "ip": parts[0],
                "port": parts[1],
                "user": parts[2],
                "password": parts[3],
                "proxy": line
            })
        elif len(parts) >= 2:
            parsed.append({
                "ip": parts[0],
                "port": parts[1],
                "user": "",
                "password": "",
                "proxy": line
            })
    return {"count": len(parsed), "proxies": parsed}

@app.get("/api/download")
async def download_file():
    if os.path.exists(config.OUTPUT_PROXY_FILE):
        return FileResponse(
            path=config.OUTPUT_PROXY_FILE,
            filename="proxies.txt",
            media_type="text/plain"
        )
    return Response(content="", media_type="text/plain")

@app.post("/api/clear")
async def clear_proxies():
    if os.path.exists(config.OUTPUT_PROXY_FILE):
        with open(config.OUTPUT_PROXY_FILE, "w", encoding="utf-8") as f:
            f.write("")
    log_manager.add("Đã xóa sạch danh sách proxies.txt.", "warn")
    return {"success": True}

# -----------------------------------------------------------------------------
# GIAO DIỆN WEB DASHBOARD HIỆN ĐẠI (DARK / CYBERPUNK THEME)
# -----------------------------------------------------------------------------
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoProxy Cloud - Quản Lý & Thu Thập Proxy Tự Động</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-body: #0a0d14;
            --bg-card: #121824;
            --bg-card-alt: #1a2234;
            --border: #232d42;
            --text-main: #f1f5f9;
            --text-muted: #8492a6;
            --accent-green: #10b981;
            --accent-green-glow: rgba(16, 185, 129, 0.25);
            --accent-cyan: #06b6d4;
            --accent-purple: #8b5cf6;
            --accent-red: #ef4444;
            --accent-orange: #f59e0b;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Plus Jakarta Sans', sans-serif;
            background: var(--bg-body);
            color: var(--text-main);
            min-height: 100vh;
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 24px;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            width: 100%;
            display: flex;
            flex-direction: column;
            gap: 24px;
        }

        /* HEADER */
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--bg-card);
            border: 1px solid var(--border);
            padding: 20px 28px;
            border-radius: 16px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.4);
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 14px;
        }

        .brand-icon {
            width: 44px;
            height: 44px;
            background: linear-gradient(135deg, var(--accent-green), var(--accent-cyan));
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 22px;
            box-shadow: 0 0 20px var(--accent-green-glow);
        }

        .brand-text h1 {
            font-size: 20px;
            font-weight: 800;
            letter-spacing: -0.5px;
            background: linear-gradient(90deg, #fff, var(--text-muted));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .brand-text p {
            font-size: 13px;
            color: var(--text-muted);
        }

        .controls {
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }

        .btn {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 10px 18px;
            border-radius: 10px;
            font-weight: 600;
            font-size: 14px;
            cursor: pointer;
            border: none;
            transition: all 0.2s ease;
            text-decoration: none;
        }

        .btn:hover {
            transform: translateY(-1px);
        }

        .btn-start {
            background: var(--accent-green);
            color: #042416;
            box-shadow: 0 4px 15px var(--accent-green-glow);
        }

        .btn-start:hover { background: #059669; }

        .btn-stop {
            background: rgba(239, 68, 68, 0.15);
            color: var(--accent-red);
            border: 1px solid rgba(239, 68, 68, 0.3);
        }

        .btn-stop:hover { background: rgba(239, 68, 68, 0.25); }

        .btn-download {
            background: rgba(6, 182, 212, 0.15);
            color: var(--accent-cyan);
            border: 1px solid rgba(6, 182, 212, 0.3);
        }

        .btn-download:hover { background: rgba(6, 182, 212, 0.25); }

        .btn-copy {
            background: rgba(139, 92, 246, 0.15);
            color: var(--accent-purple);
            border: 1px solid rgba(139, 92, 246, 0.3);
        }

        .btn-clear {
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-muted);
            border: 1px solid var(--border);
        }

        /* STATS GRID */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
        }

        .stat-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            padding: 20px;
            border-radius: 14px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .stat-label {
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-muted);
        }

        .stat-value {
            font-size: 28px;
            font-weight: 800;
            color: #fff;
        }

        .badge-running {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 13px;
            color: var(--accent-green);
        }

        .pulse-dot {
            width: 8px;
            height: 8px;
            background: var(--accent-green);
            border-radius: 50%;
            box-shadow: 0 0 10px var(--accent-green);
            animation: pulse 1.5s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.4; transform: scale(1.2); }
        }

        /* MAIN CONTENT SPLIT */
        .main-grid {
            display: grid;
            grid-template-columns: 1.1fr 1fr;
            gap: 20px;
        }

        @media (max-width: 1024px) {
            .main-grid { grid-template-columns: 1fr; }
        }

        .panel {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }

        .panel-header {
            padding: 16px 20px;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--bg-card-alt);
        }

        .panel-title {
            font-size: 14px;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        /* TERMINAL LOG */
        .terminal {
            background: #080b11;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12.5px;
            padding: 16px;
            height: 480px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        .log-entry {
            display: flex;
            gap: 10px;
            line-height: 1.5;
            word-break: break-all;
        }

        .log-time {
            color: #4b5563;
            flex-shrink: 0;
        }

        .log-msg-info { color: #94a3b8; }
        .log-msg-success { color: #34d399; font-weight: 600; }
        .log-msg-warn { color: #fbbf24; }
        .log-msg-error { color: #f87171; font-weight: 600; }

        /* PROXY TABLE */
        .table-wrap {
            height: 480px;
            overflow-y: auto;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }

        th {
            position: sticky;
            top: 0;
            background: var(--bg-card-alt);
            padding: 12px 16px;
            text-align: left;
            font-size: 12px;
            color: var(--text-muted);
            border-bottom: 1px solid var(--border);
            font-weight: 600;
            text-transform: uppercase;
        }

        td {
            padding: 10px 16px;
            border-bottom: 1px solid rgba(255,255,255,0.03);
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
        }

        tr:hover {
            background: rgba(255,255,255,0.02);
        }

        .copy-chip {
            padding: 2px 6px;
            border-radius: 4px;
            background: rgba(255,255,255,0.06);
            color: var(--accent-cyan);
            cursor: pointer;
            font-size: 11px;
            border: 1px solid rgba(255,255,255,0.1);
        }

        .copy-chip:hover {
            background: var(--accent-cyan);
            color: #042416;
        }

        /* API BOX */
        .api-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            padding: 16px 20px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
        }

        .api-info {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .api-code {
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            background: #080b11;
            padding: 6px 12px;
            border-radius: 6px;
            color: var(--accent-green);
            border: 1px solid var(--border);
        }

        /* TOAST */
        .toast {
            position: fixed;
            bottom: 24px;
            right: 24px;
            padding: 12px 20px;
            background: var(--bg-card-alt);
            border: 1px solid var(--accent-green);
            color: #fff;
            border-radius: 10px;
            font-size: 13px;
            display: none;
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
            z-index: 1000;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- HEADER -->
        <header class="header">
            <div class="brand">
                <div class="brand-icon">🌐</div>
                <div class="brand-text">
                    <h1>AutoProxy Cloud Collector</h1>
                    <p>Hệ thống tự động hóa thu thập Webshare Proxy trên Cloud</p>
                </div>
            </div>
            <div class="controls">
                <button id="btn-start" class="btn btn-start" onclick="startWorker()">▶ Bắt Đầu</button>
                <button id="btn-stop" class="btn btn-stop" onclick="stopWorker()">⏹ Tạm Dừng</button>
                <a href="/api/download" class="btn btn-download">📥 Tải proxies.txt</a>
                <button class="btn btn-copy" onclick="copyAllProxies()">📋 Sao Chép Hết</button>
                <button class="btn btn-clear" onclick="clearProxies()">🗑 Xóa Hết</button>
            </div>
        </header>

        <!-- STATS -->
        <section class="stats-grid">
            <div class="stat-card">
                <span class="stat-label">Tổng Proxy Thu Được</span>
                <span id="stat-total" class="stat-value">0</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Trạng Thái Hệ Thống</span>
                <div id="stat-status" class="stat-value" style="font-size: 18px; margin-top: 6px;">
                    <span style="color: var(--text-muted);">Đang dừng</span>
                </div>
            </div>
            <div class="stat-card">
                <span class="stat-label">Vòng Lặp Hiện Tại</span>
                <span id="stat-loop" class="stat-value">0</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Email Gần Nhất</span>
                <span id="stat-email" class="stat-value" style="font-size: 14px; word-break: break-all; margin-top: 6px; color: var(--accent-cyan);">-</span>
            </div>
        </section>

        <!-- API BOX -->
        <div class="api-card">
            <div class="api-info">
                <strong style="font-size: 13px;">🔗 Link API Lấy Danh Sách Proxy Tự Động (Raw Text):</strong>
                <span style="font-size: 12px; color: var(--text-muted);">Gắn URL này vào bất kỳ bot/tool nào để tự động kéo danh sách proxy về sử dụng:</span>
            </div>
            <div style="display: flex; gap: 8px; align-items: center;">
                <code id="api-url-text" class="api-code">/api/proxies?format=text</code>
                <button class="btn btn-copy" style="padding: 6px 12px;" onclick="copyApiUrl()">Copy Link</button>
            </div>
        </div>

        <!-- MAIN GRID: TERMINAL + TABLE -->
        <div class="main-grid">
            <!-- TERMINAL LOG -->
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title">🖥️ Live Terminal Log</span>
                    <span style="font-size: 11px; color: var(--text-muted);">Tự động cập nhật mỗi giây</span>
                </div>
                <div id="terminal-box" class="terminal">
                    <!-- Logs dynamically appended here -->
                </div>
            </div>

            <!-- TABLE PROXIES -->
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title">📋 Danh Sách Proxy Chi Tiết (<span id="table-count">0</span>)</span>
                    <input type="text" id="search-input" placeholder="Tìm kiếm IP..." oninput="filterTable()" style="background: var(--bg-card); border: 1px solid var(--border); padding: 4px 10px; border-radius: 6px; color: #fff; font-size: 12px;">
                </div>
                <div class="table-wrap">
                    <table>
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Địa Chỉ IP:Port</th>
                                <th>Username:Password</th>
                                <th>Copy</th>
                            </tr>
                        </thead>
                        <tbody id="proxy-tbody">
                            <!-- Table rows -->
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <div id="toast" class="toast"></div>

    <script>
        let allProxies = [];

        function showToast(msg) {
            const t = document.getElementById("toast");
            t.innerText = msg;
            t.style.display = "block";
            setTimeout(() => { t.style.display = "none"; }, 2500);
        }

        async function fetchStatus() {
            try {
                const res = await fetch("/api/status");
                const data = await res.json();
                document.getElementById("stat-total").innerText = data.total_proxies;
                document.getElementById("stat-loop").innerText = data.current_loop;
                document.getElementById("stat-email").innerText = data.last_email || "-";

                const sEl = document.getElementById("stat-status");
                if (data.is_running) {
                    sEl.innerHTML = '<span class="badge-running"><span class="pulse-dot"></span> ĐANG CHẠY</span>';
                    document.getElementById("btn-start").style.display = "none";
                    document.getElementById("btn-stop").style.display = "inline-flex";
                } else {
                    sEl.innerHTML = '<span style="color: var(--text-muted);">Tạm dừng</span>';
                    document.getElementById("btn-start").style.display = "inline-flex";
                    document.getElementById("btn-stop").style.display = "none";
                }
            } catch(e) {}
        }

        async function fetchLogs() {
            try {
                const res = await fetch("/api/logs");
                const data = await res.json();
                const box = document.getElementById("terminal-box");
                const isScrolledToBottom = box.scrollHeight - box.clientHeight <= box.scrollTop + 30;

                box.innerHTML = data.logs.map(l => {
                    return `<div class="log-entry">
                        <span class="log-time">[${l.time}]</span>
                        <span class="log-msg-${l.level}">${escapeHtml(l.message)}</span>
                    </div>`;
                }).join("");

                if (isScrolledToBottom) {
                    box.scrollTop = box.scrollHeight;
                }
            } catch(e) {}
        }

        async function fetchProxies() {
            try {
                const res = await fetch("/api/proxies?format=json");
                const data = await res.json();
                allProxies = data.proxies || [];
                renderTable(allProxies);
            } catch(e) {}
        }

        function renderTable(list) {
            document.getElementById("table-count").innerText = list.length;
            const tbody = document.getElementById("proxy-tbody");
            tbody.innerHTML = list.map((p, idx) => {
                return `<tr>
                    <td style="color: var(--text-muted);">${idx + 1}</td>
                    <td style="font-weight: 600; color: #fff;">${p.ip}:${p.port}</td>
                    <td style="color: var(--accent-cyan);">${p.user ? p.user + ':' + p.password : '-'}</td>
                    <td><button class="copy-chip" onclick="copyText('${p.proxy}')">Copy</button></td>
                </tr>`;
            }).join("");
        }

        function filterTable() {
            const q = document.getElementById("search-input").value.trim().toLowerCase();
            const filtered = allProxies.filter(p => p.proxy.toLowerCase().includes(q));
            renderTable(filtered);
        }

        async function startWorker() {
            await fetch("/api/start", { method: "POST" });
            showToast("Đã gửi lệnh bắt đầu thu thập!");
            fetchStatus();
        }

        async function stopWorker() {
            await fetch("/api/stop", { method: "POST" });
            showToast("Đang dừng tiến trình...");
            fetchStatus();
        }

        async function clearProxies() {
            if (!confirm("Bạn có chắc chắn muốn xóa toàn bộ danh sách proxy trong file không?")) return;
            await fetch("/api/clear", { method: "POST" });
            showToast("Đã xóa sạch danh sách proxy!");
            fetchProxies();
            fetchStatus();
        }

        function copyText(text) {
            navigator.clipboard.writeText(text);
            showToast("Đã sao chép: " + text);
        }

        async function copyAllProxies() {
            const res = await fetch("/api/proxies?format=text");
            const text = await res.text();
            if (!text.trim()) {
                showToast("Danh sách proxy đang trống!");
                return;
            }
            navigator.clipboard.writeText(text);
            showToast("Đã sao chép toàn bộ " + allProxies.length + " proxy vào clipboard!");
        }

        function copyApiUrl() {
            const fullUrl = window.location.origin + "/api/proxies?format=text";
            navigator.clipboard.writeText(fullUrl);
            showToast("Đã sao chép link API: " + fullUrl);
        }

        function escapeHtml(str) {
            return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        }

        // Khởi động cập nhật chu kỳ
        window.onload = () => {
            fetchStatus();
            fetchLogs();
            fetchProxies();

            document.getElementById("api-url-text").innerText = window.location.origin + "/api/proxies?format=text";

            setInterval(fetchStatus, 2000);
            setInterval(fetchLogs, 1500);
            setInterval(fetchProxies, 4000);
        };
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def dashboard_index():
    return HTMLResponse(content=DASHBOARD_HTML)

# -----------------------------------------------------------------------------
# CHẠY SERVER
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"[*] Đang khởi động AutoProxy Cloud Dashboard tại: http://localhost:{port}")
    # Tự động bật worker nếu chạy trên Cloud (Render)
    if config.IS_RENDER:
        print("[*] Phát hiện môi trường Render Cloud: Tự động khởi chạy worker!")
        worker.start()
    uvicorn.run(app, host="0.0.0.0", port=port)
