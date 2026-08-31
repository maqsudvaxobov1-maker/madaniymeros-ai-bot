import os
import json
import time
import threading
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
PORT = int(os.getenv("PORT", "10000"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY topilmadi")


TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
OPENAI_URL = "https://api.openai.com/v1/responses"


def telegram(method, data=None):
    url = f"{TELEGRAM_URL}/{method}"

    body = None
    headers = {
        "Content-Type": "application/json"
    }

    if data is not None:
        body = json.dumps(data).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method="POST" if data is not None else "GET"
    )

    try:
        with urllib.request.urlopen(request, timeout=70) as response:
            return json.loads(response.read().decode("utf-8"))

    except Exception as e:
        print("Telegram xatosi:", e, flush=True)
        return None


def send_message(chat_id, text):
    if not text:
        text = "Kechirasiz, javob tayyorlashda xatolik yuz berdi."

    # Telegram 4096 belgigacha qabul qiladi
    for i in range(0, len(text), 4000):
        telegram(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text[i:i + 4000]
            }
        )


def ask_openai(question):
    data = {
        "model": "gpt-4o-mini",
        "input": [
            {
                "role": "system",
                "content": (
                    "Siz Madaniy Meros AI yordamchisisiz. "
                    "O'zbekiston madaniy merosi, tarixiy-me'moriy "
                    "obyektlar, restavratsiya, muhofaza va loyiha "
                    "hujjatlari bo'yicha aniq va foydali javob bering. "
                    "Foydalanuvchi qaysi tilda yozsa, shu tilda javob bering. "
                    "O'zbek tilida yozilganda sodda va tushunarli yozing."
                )
            },
            {
                "role": "user",
                "content": question
            }
        ],
        "max_output_tokens": 1200
    }

    request = urllib.request.Request(
        OPENAI_URL,
        data=json.dumps(data).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

        # Responses API javobidan matnni olish
        if "output_text" in result:
            return result["output_text"]

        # Zaxira usul
        output = result.get("output", [])

        for item in output:
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    return content.get("text", "")

        return "Javob olinmadi."

    except urllib.error.HTTPError as e:
        error_text = e.read().decode("utf-8", errors="ignore")
        print("OpenAI HTTP xatosi:", error_text, flush=True)
        return "AI xizmatida vaqtinchalik xatolik yuz berdi."

    except Exception as e:
        print("OpenAI xatosi:", e, flush=True)
        return "AI bilan bog'lanishda xatolik yuz berdi."


def bot_loop():
    print("Telegram bot ishga tushdi...", flush=True)

    offset = None

    # Webhook bo'lsa o'chiramiz
    telegram("deleteWebhook", {"drop_pending_updates": True})

    while True:
        try:
            data = {
                "timeout": 30
            }

            if offset is not None:
                data["offset"] = offset

            result = telegram("getUpdates", data)

            if not result:
                time.sleep(2)
                continue

            updates = result.get("result", [])

            for update in updates:
                offset = update["update_id"] + 1

                message = update.get("message")

                if not message:
                    continue

                chat = message.get("chat", {})
                chat_id = chat.get("id")

                text = message.get("text", "")

                if not chat_id:
                    continue

                print(
                    f"Xabar: {chat_id} -> {text}",
                    flush=True
                )

                if text == "/start":
                    send_message(
                        chat_id,
                        "Assalomu alaykum! 👋\n\n"
                        "Men Madaniy Meros AI yordamchisiman.\n\n"
                        "Savolingizni yozing, men javob beraman."
                    )
                    continue

                if text == "/help":
                    send_message(
                        chat_id,
                        "Savolingizni oddiy matn ko'rinishida yuboring.\n\n"
                        "Masalan:\n"
                        "• Madaniy meros obyekti nima?\n"
                        "• Restavratsiya loyihasiga nimalar kerak?\n"
                        "• Tarixiy binoni ta'mirlash tartibi qanday?"
                    )
                    continue

                if not text.strip():
                    continue

                # Foydalanuvchiga ishlayotganini bildiradi
                telegram(
                    "sendChatAction",
                    {
                        "chat_id": chat_id,
                        "action": "typing"
                    }
                )

                answer = ask_openai(text)

                send_message(chat_id, answer)

        except Exception as e:
            print("Bot loop xatosi:", e, flush=True)
            time.sleep(5)


class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        body = b"Madaniy Meros AI Bot ishlayapti!"

        self.send_response(200)
        self.send_header(
            "Content-Type",
            "text/plain; charset=utf-8"
        )
        self.send_header(
            "Content-Length",
            str(len(body))
        )
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        self.send_response(200)
        self.send_header(
            "Content-Type",
            "text/plain; charset=utf-8"
        )
        self.end_headers()

    def log_message(self, format, *args):
        print(format % args, flush=True)


def main():
    # Telegram botni alohida oqimda ishlatamiz
    thread = threading.Thread(
        target=bot_loop,
        daemon=True
    )

    thread.start()

    # Render uchun HTTP server
    server = ThreadingHTTPServer(
        ("0.0.0.0", PORT),
        Handler
    )

    print(
        f"Web server {PORT} portda ishga tushdi.",
        flush=True
    )

    server.serve_forever()


if __name__ == "__main__":
    main()
