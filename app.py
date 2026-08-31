import os
import json
import time
import threading
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


# =========================================================
# SOZLAMALAR
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

PORT = int(os.getenv("PORT", "10000"))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6")

TELEGRAM_TIMEOUT = 40
OPENAI_TIMEOUT = 90


# =========================================================
# TEKSHIRISH
# =========================================================

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY topilmadi")


# =========================================================
# UMUMIY HTTP FUNKSIYA
# =========================================================

def http_json(url, data=None, headers=None, timeout=60):

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
            raw = response.read().decode("utf-8")
            return json.loads(raw)

    except urllib.error.HTTPError as e:

        error_body = e.read().decode("utf-8", errors="ignore")

        print(
            f"HTTP ERROR {e.code}: {error_body}",
            flush=True
        )

        raise

    except Exception as e:

        print(
            f"HTTP ERROR: {e}",
            flush=True
        )

        raise


# =========================================================
# TELEGRAM
# =========================================================

TELEGRAM_API = (
    "https://api.telegram.org/bot"
    + BOT_TOKEN
    + "/"
)


def telegram(method, data=None):

    url = TELEGRAM_API + method

    return http_json(
        url,
        data=data,
        timeout=TELEGRAM_TIMEOUT
    )


# =========================================================
# TELEGRAM TOKENNI TEKSHIRISH
# =========================================================

def check_telegram():

    print("Telegram token tekshirilmoqda...", flush=True)

    result = telegram("getMe")

    if not result.get("ok"):
        raise RuntimeError(
            "Telegram token ishlamayapti: "
            + str(result)
        )

    bot = result.get("result", {})

    print(
        "Telegram bot OK: @"
        + str(bot.get("username")),
        flush=True
    )


# =========================================================
# WEBHOOKNI O'CHIRISH
# =========================================================

def remove_webhook():

    try:

        result = telegram(
            "deleteWebhook",
            {
                "drop_pending_updates": False
            }
        )

        print(
            "Webhook o'chirildi:",
            result,
            flush=True
        )

    except Exception as e:

        print(
            "Webhook o'chirishda xato:",
            e,
            flush=True
        )


# =========================================================
# XABAR YUBORISH
# =========================================================

def send_message(chat_id, text):

    if not text:
        text = "Javob tayyorlashda xatolik yuz berdi."

    # Telegram maksimal xabar uzunligini cheklaydi.
    # Shu sababli katta javobni bo'lib yuboramiz.

    text = str(text)

    max_length = 4000

    for i in range(0, len(text), max_length):

        part = text[i:i + max_length]

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


# =========================================================
# OPENAI
# =========================================================

def openai_answer(question):

    url = "https://api.openai.com/v1/chat/completions"

    system_text = """
Siz "Madaniy Meros AI" nomli yordamchisiz.

Siz O'zbekiston madaniy merosi,
tarixiy-me'moriy obidalari,
madaniy meros obyektlarini muhofaza qilish,
restavratsiya,
ta'mirlash,
moslashtirish,
me'moriy yechimlar,
loyiha hujjatlari va ilmiy-ekspert kengashi
bilan bog'liq savollarga yordam berasiz.

Javoblarni o'zbek tilida bering.

Javob:
- aniq;
- tushunarli;
- amaliy;
- imkon qadar qisqa;
- kerak bo'lsa punktlar bilan bo'lsin.

Huquqiy masalalarda qonun yoki qaror raqamini
aniq bilmasangiz, o'ylab topmang.
Noaniq ma'lumotni fakt sifatida bermang.
"""

    data = {
        "model": OPENAI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": system_text
            },
            {
                "role": "user",
                "content": question
            }
        ],
        "temperature": 0.3
    }

    headers = {
        "Authorization": "Bearer " + OPENAI_API_KEY,
        "Content-Type": "application/json"
    }

    result = http_json(
        url,
        data=data,
        headers=headers,
        timeout=OPENAI_TIMEOUT
    )

    choices = result.get("choices", [])

    if not choices:
        return "OpenAI javob qaytarmadi."

    message = choices[0].get("message", {})

    answer = message.get("content", "")

    if not answer:
        return "Javob bo'sh qaytdi."

    return answer.strip()


# =========================================================
# START
# =========================================================

def start_message():

    return (
        "🏛 Assalomu alaykum!\n\n"
        "Men — Madaniy Meros AI yordamchisiman.\n\n"
        "O'zbekiston madaniy merosi, "
        "tarixiy-me'moriy obyektlar, "
        "restavratsiya va loyiha hujjatlari "
        "bo'yicha savolingizni yozishingiz mumkin.\n\n"
        "Savolingizni yuboring."
    )


# =========================================================
# UPDATE ISHLASH
# =========================================================

def process_update(update):

    try:

        message = update.get("message")

        if not message:
            return

        chat = message.get("chat", {})
        chat_id = chat.get("id")

        text = message.get("text", "")

        if not chat_id:
            return

        if not text:
            return

        text = text.strip()

        print(
            f"Xabar: {chat_id}: {text}",
            flush=True
        )

        # START

        if text.startswith("/start"):

            send_message(
                chat_id,
                start_message()
            )

            return

        # HELP

        if text.startswith("/help"):

            send_message(
                chat_id,
                "Savolingizni oddiy matn ko'rinishida yuboring.\n\n"
                "Masalan:\n"
                "• Madaniy meros obyekti nima?\n"
                "• Restavratsiya loyihasida nimalar bo'lishi kerak?\n"
                "• Tarixiy binoning tashqi ko'rinishini o'zgartirish mumkinmi?"
            )

            return

        # AI JAVOB

        send_message(
            chat_id,
            "⏳ Savolingiz ko'rib chiqilmoqda..."
        )

        try:

            answer = openai_answer(text)

            send_message(
                chat_id,
                answer
            )

        except Exception as e:

            print(
                "OpenAI xatosi:",
                e,
                flush=True
            )

            send_message(
                chat_id,
                "⚠️ Hozircha javob tayyorlashda texnik xatolik yuz berdi.\n"
                "Birozdan keyin yana urinib ko'ring."
            )

    except Exception as e:

        print(
            "UPDATE XATOSI:",
            e,
            flush=True
        )


# =========================================================
# TELEGRAM POLLING
# =========================================================

def telegram_polling():

    print(
        "Telegram polling boshlandi...",
        flush=True
    )

    offset = None

    while True:

        try:

            data = {
                "timeout": 30,
                "limit": 100,
                "allowed_updates": [
                    "message"
                ]
            }

            if offset is not None:
                data["offset"] = offset

            result = telegram(
                "getUpdates",
                data
            )

            if not result.get("ok"):

                print(
                    "getUpdates xatosi:",
                    result,
                    flush=True
                )

                time.sleep(5)

                continue

            updates = result.get(
                "result",
                []
            )

            for update in updates:

                update_id = update.get(
                    "update_id"
                )

                if update_id is not None:

                    offset = update_id + 1

                process_update(update)

        except Exception as e:

            print(
                "Telegram polling xatosi:",
                e,
                flush=True
            )

            time.sleep(5)


# =========================================================
# RENDER WEB SERVER
# =========================================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        body = (
            "Madaniy Meros AI Bot ishlayapti!"
        ).encode("utf-8")

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


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "====================================",
        flush=True
    )

    print(
        "MADANIY MEROS AI BOT",
        flush=True
    )

    print(
        "====================================",
        flush=True
    )

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
