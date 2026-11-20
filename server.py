import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
PORT = 8090
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MODELS = [
    "gemini-flash-latest",
    "gemini-2.5-flash-lite",
    "gemini-flash-lite-latest",
]


def load_api_key():
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key:
        return env_key
    key_file = os.path.join(BASE_DIR, "key.txt")
    if os.path.exists(key_file):
        with open(key_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def ask_gemini(prompt_text):
    api_key = load_api_key()
    if not api_key:
        return "کلید API در فایل key.txt پیدا نشد."

    payload = {
        "systemInstruction": {
            "parts": [
                {
                    "text": (
                        "تو یک دستیار هوشمند و دقیق هستی. "
                        "همیشه به زبانِ پیامِ کاربر پاسخ بده. "
                        "مستقیم، طبیعی و کامل جواب بده و از جملات قالبی یا تکراری پرهیز کن."
                    )
                }
            ]
        },
        "contents": [{"role": "user", "parts": [{"text": prompt_text}]}],
        "generationConfig": {"temperature": 0.65, "maxOutputTokens": 8192},
    }
    raw_body = json.dumps(payload).encode("utf-8")

    for model in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        try:
            req = urllib.request.Request(
                url,
                data=raw_body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                candidates = data.get("candidates") or []
                if candidates:
                    parts = ((candidates[0].get("content") or {}).get("parts")) or []
                    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
                    if text:
                        return text
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403):
                return f"خطای کلید یا دسترسی ({e.code}). لطفاً کلید API را بررسی کن."
        except Exception:
            continue

    return "الان اتصال به هوش مصنوعی برقرار نشد. اینترنت یا کلید را چک کن و دوباره بپرس."


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def send_json(self, code, payload):
        try:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
            pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            html_file = os.path.join(BASE_DIR, "index.html")
            if not os.path.exists(html_file):
                self.send_json(404, {"reply": "index.html پیدا نشد."})
                return
            try:
                with open(html_file, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
                pass
            return
        self.send_json(404, {"reply": "مسیر پیدا نشد."})

    def do_POST(self):
        if self.path != "/api/chat":
            self.send_json(404, {"reply": "مسیر پیدا نشد."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length > 0 else b"{}"
            obj = json.loads(raw.decode("utf-8") or "{}")
            prompt = str(obj.get("message") or "").strip()
            if not prompt and isinstance(obj.get("messages"), list):
                for m in reversed(obj["messages"]):
                    if isinstance(m, dict) and m.get("role") == "user":
                        prompt = str(m.get("content") or "").strip()
                        break
            reply = ask_gemini(prompt or "سلام")
            self.send_json(200, {"reply": reply})
        except Exception:
            self.send_json(200, {"reply": "مشکلی در پردازش پیام پیش آمد."})


if __name__ == "__main__":
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"New AI running at http://{HOST}:{PORT}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()