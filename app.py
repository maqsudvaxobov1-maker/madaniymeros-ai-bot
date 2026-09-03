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
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6")

TELEGRAM_API = "https://api.telegram.org/bot" + BOT_TOKEN + "/"
KNOWLEDGE_FILE = "knowledge_base.json"


def http_json(url, data=None, headers=None, timeout=90):
    if headers is None:
        headers = {}

    body = None

    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers = dict(headers)
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method="POST" if data is not None else "GET"
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        print("HTTP ERROR", e.code, error_body, flush=True)
        raise

    except Exception as e:
        print("HTTP ERROR:", e, flush=True)
        raise


def telegram(method, data=None):
    return http_json(
        TELEGRAM_API + method,
        data=data,
        timeout=60
    )


def load_knowledge_base():
    try:
        with open(
            KNOWLEDGE_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            data = json.load(f)

        text = json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        )

        print(
            "Knowledge base yuklandi:",
            len(text),
            "belgi",
            flush=True
        )

        return text[:50000]

    except FileNotFoundError:
        print(
            "knowledge_base.json topilmadi",
            flush=True
        )
        return ""

    except Exception as e:
        print(
            "Knowledge base xatosi:",
            e,
            flush=True
        )
        return ""


KNOWLEDGE_BASE = load_knowledge_base()


def check_telegram():
    result = telegram("getMe")

    if not result.get("ok"):
        raise RuntimeError(
            "Telegram token ishlamayapti"
        )

    bot = result.get("result", {})

    print(
        "Telegram bot OK: @"
        + str(bot.get("username")),
        flush=True
    )


def remove_webhook():
    try:
        result = telegram(
            "deleteWebhook",
            {"drop_pending_updates": False}
        )

        print(
            "Webhook holati:",
            result,
            flush=True
        )

    except Exception as e:
        print(
            "Webhook xatosi:",
            e,
            flush=True
        )


def send_message(chat_id, text):
    if not text:
        text = "Javob tayyorlashda xatolik yuz berdi."

    text = str(text)

    for i in range(0, len(text), 4000):
        part = text[i:i + 4000]

        try:
            telegram(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": part
                }
            )

        except Exception as e:
            print(
                "Xabar yuborishda xato:",
                e,
                flush=True
            )


def openai_answer(question):

    system_text = """
Siz "Madaniy Meros AI" nomli
O'zbekiston madaniy merosi bo'yicha
ixtisoslashgan AI yordamchisiz.

Siz quyidagi mavzularda yordam berasiz:

- madaniy meros obyektlari;
- tarixiy-me'moriy obyektlar;
- arxeologiya;
- restavratsiya;
- ta'mirlash;
- moslashtirish;
- muhofaza qilish;
- loyiha hujjatlari;
- ilmiy-ekspert kengashi;
- madaniy meros obyektlaridan foydalanish.

Javoblarni o'zbek tilida bering.

Eng muhim qoida:
Quyida berilgan KNOWLEDGE BASE ma'lumotlaridan
birinchi navbatda foydalaning.

Agar savolga aniq javob KNOWLEDGE BASEda bo'lmasa,
buni ochiq ayting.

Qonun, qaror yoki boshqa normativ hujjat
raqamini o'ylab topmang.

Aniq bo'lmagan ma'lumotni fakt sifatida bermang.

Javob:
- aniq;
- tushunarli;
- amaliy;
- qisqa;
- kerak bo'lsa punktlar bilan bo'lsin.
"""

    prompt = (
        "KNOWLEDGE BASE:\n"
        + KNOWLEDGE_BASE
        + "\n\nFOYDALANUVCHI SAVOLI:\n"
        + question
    )

    data = {
        "model": OPENAI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": system_text
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    }

    headers = {
        "Authorization":
            "Bearer " + OPENAI_API_KEY,
        "Content-Type":
            "application/json"
    }

    result = http_json(
        "https://api.openai.com/v1/chat/completions",
        data=data,
        headers=headers,
        timeout=120
    )

    choices = result.get("choices", [])

    if not choices:
        return "OpenAI javob qaytarmadi."

    message = choices[0].get(
        "message",
        {}
    )

    answer = message.get(
        "content",
        ""
    )

    if not answer:
        return "Javob bo'sh qaytdi."

    return answer.strip()


def start_message():
    return (
        "🏛 Assalomu alaykum!\n\n"
        "Men — Madaniy Meros AI yordamchisiman.\n\n"
        "O'zbekiston madaniy merosi, "
        "tarixiy-me'moriy obyektlar, "
        "restavratsiya va loyiha hujjatlari "
        "bo'yicha savollaringizga javob beraman.\n\n"
        "Savolingizni yuboring."
    )


def process_update(update):

    try:
        message = update.get("message")

        if not message:
            return

        chat = message.get("chat", {})
        chat_id = chat.get("id")
        text = message.get("text", "")

        if not chat_id or not text:
            return

        text = text.strip()

        print(
            "Savol:",
            text,
            flush=True
        )

        if text.startswith("/start"):
            send_message(
                chat_id,
                start_message()
            )
            return

        if text.startswith("/help"):    send_message(
        chat_id,
        "Savolingizni oddiy matn ko'rinishida yuboring.\n\n"
        "Masalan:\n"
        "• Madaniy meros obyekti nima?\n"
        "• Restavratsiya loyihasida nimalar bo'lishi kerak?\n"
        "• Tarixiy binoning tashqi ko'rinishini o'zgartirish mumkinmi?"
    )
    return

send_message(chat_id, "⏳ Savolingiz ko'rib chiqilmoqda...")

try:
    answer = openai_answer(text)
    send_message(chat_id, answer)
except Exception as e:
    print("OpenAI xatosi:", e, flush=True)
    send_message(
        chat_id,
        "⚠️ Hozircha javob tayyorlashda texnik xatolik yuz berdi.\n"
        "Birozdan keyin yana urinib ko'ring."
    )


def telegram_polling():
    print("Telegram polling boshlandi...", flush=True)
    offset = None

    while True:
        try:
            data = {
                "timeout": 30,
                "limit": 100,
                "allowed_updates": ["message"]
            }

            if offset is not None:
                data["offset"] = offset

            result = telegram("getUpdates", data)

            if not result.get("ok"):
                print("getUpdates xatosi:", result, flush=True)
                time.sleep(5)
                continue

            updates = result.get("result", [])

            for update in updates:
                update_id = update.get("update_id")

                if update_id is not None:
                    offset = update_id + 1

                process_update(update)

        except Exception as e:
            print("Telegram polling xatosi:", e, flush=True)
            time.sleep(5)


class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        body = "Madaniy Meros AI Bot ishlayapti!".encode("utf-8")

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
            "text/plain"
        )
        self.end_headers()

    def log_message(self, format, *args):
        return


def run_web_server():
    server = ThreadingHTTPServer(
        ("0.0.0.0", PORT),
        HealthHandler
    )

    print(
        f"Web server PORT={PORT}",
        flush=True
    )

    server.serve_forever()


def main():
    print("====================================", flush=True)
    print("MADANIY MEROS AI BOT", flush=True)
    print("====================================", flush=True)

    check_telegram()
    remove_webhook()

    web_thread = threading.Thread(
        target=run_web_server,
        daemon=True
    )

    web_thread.start()

    telegram_polling()


if __name__ == "__main__":
    main()
