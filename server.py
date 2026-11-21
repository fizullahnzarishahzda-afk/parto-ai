import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8000"))
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")


def load_api_key() -> str:
    env_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if env_key:
        return env_key
    key_file = BASE_DIR / "key.txt"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    return ""


def ask_gemini(
    prompt: str,
    messages: list | None = None,
    mode_instruction: str = "",
    media_base64: str = "",
    media_mime_type: str = "",
) -> str:
    api_key = load_api_key()
    if not api_key:
        return "کلید API در key.txt یا متغیر محیطی پیدا نشد."

    system_parts = [
        "تو «پرتو هوش مصنوعی (نظری)» هستی؛ دستیار فارسی‌زبان، صمیمی، دقیق و مفید.",
        "اگر کاربر عکس یا ویدیو فرستاد، حتماً محتوای آن را با دقت بررسی کن و پاسخ بده.",
    ]
    if mode_instruction:
        system_parts.append(f"راهنمای حالت فعلی: {mode_instruction}")

    contents = []
    history = messages if isinstance(messages, list) else []

    for item in history[:-1]:
        if not isinstance(item, dict):
            continue
        role = "model" if item.get("role") == "assistant" else "user"
        txt = str(item.get("content") or "").strip()
        if txt:
            contents.append({"role": role, "parts": [{"text": txt}]})

    final_parts = []
    clean_b64 = (media_base64 or "").strip()
    clean_mime = (media_mime_type or "").strip()
    if clean_b64 and clean_mime:
        if "," in clean_b64:
            clean_b64 = clean_b64.split(",", 1)[1]
        final_parts.append({
            "inline_data": {
                "mime_type": clean_mime,
                "data": clean_b64,
            }
        })

    final_parts.append({"text": prompt or "سلام"})
    contents.append({"role": "user", "parts": final_parts})

    payload = {
        "system_instruction": {"parts": [{"text": "\n".join(system_parts)}]},
        "contents": contents,
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={api_key}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw)
            candidates = parsed.get("candidates") or []
            if not candidates:
                return "پاسخی از مدل دریافت نشد."
            parts = ((candidates[0].get("content") or {}).get("parts")) or []
            texts = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("text")]
            return "\n".join(texts).strip() or "پاسخی از مدل دریافت نشد."
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            pass
        return f"خطای سرویس جمنای ({e.code}): {err_body[:300]}"
    except Exception as e:
        return f"خطا در ارتباط با سرویس هوش مصنوعی: {str(e)[:250]}"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, status_code: int, obj: dict):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, filename: str, content_type: str):
        file_path = BASE_DIR / filename
        if not file_path.exists():
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
            return
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self.send_file("index.html", "text/html; charset=utf-8")
        elif path == "/manifest.json":
            self.send_file("manifest.json", "application/manifest+json; charset=utf-8")
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path != "/api/chat":
            self.send_json(404, {"reply": "مسیر پیدا نشد."})
            return

        try:
            content_len = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_len) if content_len > 0 else b"{}"
            data = json.loads(raw_body.decode("utf-8"))
        except Exception:
            self.send_json(400, {"reply": "فرمت درخواست نامعتبر است."})
            return

        messages = data.get("messages") if isinstance(data.get("messages"), list) else []
        mode_instruction = str(data.get("modeInstruction") or "").strip()
        media_base64 = str(data.get("mediaBase64") or "").strip()
        media_mime_type = str(data.get("mediaMimeType") or "").strip()
        prompt = str(data.get("message") or "").strip()

        if not prompt:
            for m in reversed(messages):
                if isinstance(m, dict) and m.get("role") == "user":
                    prompt = str(m.get("content") or "").strip()
                    break

        try:
            reply = ask_gemini(
                prompt or "سلام",
                messages=messages,
                mode_instruction=mode_instruction,
                media_base64=media_base64,
                media_mime_type=media_mime_type,
            )
            self.send_json(200, {"reply": reply})
        except Exception:
            self.send_json(200, {"reply": "أول پیش برش بدار در کلک میشه."})


if __name__ == "__main__":
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Parto AI running at http://{HOST}:{PORT}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
