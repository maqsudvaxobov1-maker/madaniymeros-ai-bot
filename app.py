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
OPENAI_MODEL = "gpt-5.6"

TELEGRAM_TIMEOUT = 40
OPENAI_TIMEOUT = 90


# =========================================================
# HTTP
# =========================================================

def http_request(url, data=None, headers=None, timeout=60):

    if headers is None:
        headers = {}

    body = None

    if data is not None:
        body = json.dumps(
            data,
            ensure_ascii=False
        ).encode("utf-8")

        headers = dict(headers)
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method="POST" if data is not None else "GET"
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=timeout
        ) as response:

            raw = response.read().decode("utf-8")

            return json.loads(raw)

    except urllib.error.HTTPError as e:

        error_body = e.read().decode(
            "utf-8",
            errors="ignore"
        )

        print(
            "HTTP ERROR",
            e.code,
            error_body,
            flush=True
        )

        raise

    except Exception as e:

        print(
            "HTTP REQUEST ERROR:",
            repr(e),
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

    return http_request(
        TELEGRAM_API + method,
        data=data,
        timeout=TELEGRAM_TIMEOUT
    )


# =========================================================
# TELEGRAMNI TEKSHIRISH
# =========================================================

def check_telegram():

    if not BOT_TOKEN:

        print(
            "XATO: BOT_TOKEN mavjud emas!",
            flush=True
        )

        return False

    try:

        result = telegram("getMe")

        if result.get("ok"):

            bot = result.get(
                "result",
                {}
            )

            print(
                "Telegram OK: @"
                + str(bot.get("username")),
                flush=True
            )

            return True

        print(
            "Telegram token xatosi:",
            result,
            flush=True
        )

        return False

    except Exception as e:

        print(
            "Telegram tekshirish xatosi:",
            repr(e),
            flush=True
        )

        return False


# =========================================================
# WEBHOOK
# =========================================================

def remove_webhook():

    if not BOT_TOKEN:
        return

    try:

        result = telegram(
            "deleteWebhook",
            {
                "drop_pending_updates": False
            }
        )

        print(
            "Webhook:",
            result,
            flush=True
        )

    except Exception as e:

        print(
            "Webhook xatosi:",
            repr(e),
            flush=True
        )


# =========================================================
# TELEGRAMGA XABAR
# =========================================================

def send_message(chat_id, text):

    if not text:

        text = (
            "⚠️ Javob tayyorlashda "
            "xatolik yuz berdi."
        )

    text = str(text)

    max_length = 4000

    for i in range(
        0,
        len(text),
        max_length
    ):

        part = text[
            i:i + max_length
        ]

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
                "Telegram sendMessage xatosi:",
                repr(e),
                flush=True
            )


# =========================================================
# OPENAI
# =========================================================

def openai_answer(question):

    if not OPENAI_API_KEY:

        return (
            "⚠️ OPENAI_API_KEY topilmadi.\n\n"
            "Render → Environment Variables "
            "bo‘limida OPENAI_API_KEY bo‘lishi kerak."
        )

    url = (
        "https://api.openai.com/v1/responses"
    )

    instructions = """
Siz "Madaniy Meros AI" nomli
professional yordamchisiz.

Siz O‘zbekiston madaniy merosi,
tarixiy-me’moriy obyektlar,
madaniy meros obyektlarini muhofaza qilish,
restavratsiya,
ta’mirlash,
moslashtirish,
me’moriy yechimlar,
loyiha hujjatlari,
ilmiy-ekspert kengashi
va shu sohaga oid masalalarda yordam berasiz.

Javoblarni o‘zbek tilida bering.

Javoblar:
- aniq;
- tushunarli;
- amaliy;
- qisqa va mazmunli bo‘lsin.

Kerak bo‘lsa punktlardan foydalaning.

Huquqiy masalalarda qonun,
qaror yoki boshqa hujjat raqamini
aniq bilmasangiz, o‘ylab topmang.

Noto‘g‘ri ma’lumotni fakt sifatida bermang.
"""

    data = {
        "model": OPENAI_MODEL,

        "instructions": instructions,

        "input": question,

        "max_output_tokens": 1500
    }

    headers = {
        "Authorization":
            "Bearer " + OPENAI_API_KEY,

        "Content-Type":
            "application/json"
    }

    try:

        result = http_request(
            url,
            data=data,
            headers=headers,
            timeout=OPENAI_TIMEOUT
        )

        # Responses API javobidan matnni olish

        output_text = result.get(
            "output_text"
        )

        if output_text:

            return output_text.strip()

        # Zaxira usul

        output = result.get(
            "output",
            []
        )

        texts = []

        for item in output:

            content = item.get(
                "content",
                []
            )

            for part in content:

                if part.get(
                    "type"
                ) == "output_text":

                    text = part.get(
                        "text",
                        ""
                    )

                    if text:
                        texts.append(text)

        if texts:

            return "\n".join(
                texts
            ).strip()

        return (
            "OpenAI javob qaytarmadi."
        )

    except urllib.error.HTTPError as e:

        error_body = e.read().decode(
            "utf-8",
            errors="ignore"
        )

        print(
            "OPENAI HTTP ERROR:",
            e.code,
            error_body,
            flush=True
        )

        if e.code == 401:

            return (
                "⚠️ OPENAI_API_KEY noto‘g‘ri.\n\n"
                "Render'dagi OPENAI_API_KEY "
                "qiymatini tekshiring."
            )

        if e.code == 429:

            return (
                "⚠️ OpenAI API limiti yoki "
                "billing bilan bog‘liq muammo."
            )

        return (
            "⚠️ OpenAI xatosi: HTTP "
            + str(e.code)
        )

    except Exception as e:

        print(
            "OPENAI XATOSI:",
            repr(e),
            flush=True
        )

        return (
            "⚠️ OpenAI bilan bog‘lanishda "
            "texnik xatolik yuz berdi."
        )


# =========================================================
# START
# =========================================================

def start_message():

    return (
        "🏛 Assalomu alaykum!\n\n"
        "Men — Madaniy Meros AI "
        "yordamchisiman.\n\n"
        "O‘zbekiston madaniy merosi, "
        "tarixiy-me’moriy obyektlar, "
        "restavratsiya va loyiha "
        "hujjatlari bo‘yicha savollaringizga "
        "javob beraman.\n\n"
        "Savolingizni yuboring."
    )


# =========================================================
# UPDATE
# =========================================================

def process_update(update):

    try:

        message = update.get(
            "message"
        )

        if not message:
            return

        chat = message.get(
            "chat",
            {}
        )

        chat_id = chat.get(
            "id"
        )

        text = message.get(
            "text",
            ""
        )

        if not chat_id:
            return

        if not text:
            return

        text = text.strip()

        print(
            "Xabar:",
            chat_id,
            ":",
            text,
            flush=True
        )

        # START

        if text.startswith(
            "/start"
        ):

            send_message(
                chat_id,
                start_message()
            )

            return

        # HELP

        if text.startswith(
            "/help"
        ):

            send_message(
                chat_id,
                "Savolingizni oddiy matn "
                "ko‘rinishida yuboring."
            )

            return

        # AI

        send_message(
            chat_id,
            "⏳ Savolingiz ko‘rib chiqilmoqda..."
        )

        answer = openai_answer(
            text
        )

        send_message(
            chat_id,
            answer
        )

    except Exception as e:

        print(
            "UPDATE XATOSI:",
            repr(e),
            flush=True
        )


# =========================================================
# POLLING
# =========================================================

def telegram_polling():

    print(
        "Telegram polling boshlandi...",
        flush=True
    )

    offset = None

    while True:

        try:

            if not BOT_TOKEN:

                print(
                    "BOT_TOKEN yo‘q.",
                    flush=True
                )

                time.sleep(10)

                continue

            data = {
                "timeout": 30,
                "limit": 100,
                "allowed_updates": [
                    "message"
                ]
            }

            if offset is not None:

                data[
                    "offset"
                ] = offset

            result = telegram(
                "getUpdates",
                data
            )

            if not result.get(
                "ok"
            ):

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

                    offset = (
                        update_id + 1
                    )

                process_update(
                    update
                )

        except Exception as e:

            print(
                "POLLING XATOSI:",
                repr(e),
                flush=True
            )

            time.sleep(5)


# =========================================================
# RENDER SERVER
# =========================================================

class HealthHandler(
    BaseHTTPRequestHandler
):

    def do_GET(self):

        body = (
            "Madaniy Meros AI Bot ishlayapti!"
        ).encode("utf-8")

        self.send_response(
            200
        )

        self.send_header(
            "Content-Type",
            "text/plain; charset=utf-8"
        )

        self.send_header(
            "Content-Length",
            str(len(body))
        )

        self.end_headers()

        self.wfile.write(
            body
        )

    def do_HEAD(self):

        self.send_response(
            200
        )

        self.send_header(
            "Content-Type",
            "text/plain"
        )

        self.end_headers()

    def log_message(
        self,
        format,
        *args
    ):

        return


def run_web_server():

    server = ThreadingHTTPServer(
        (
            "0.0.0.0",
            PORT
        ),
        HealthHandler
    )

    print(
        "WEB SERVER PORT =",
        PORT,
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
        "BOT_TOKEN:",
        bool(BOT_TOKEN),
        flush=True
    )

    print(
        "OPENAI_API_KEY:",
        bool(OPENAI_API_KEY),
        flush=True
    )

    print(
        "MODEL:",
        OPENAI_MODEL,
        flush=True
    )

    print(
        "PORT:",
        PORT,
        flush=True
    )

    print(
        "====================================",
        flush=True
    )

    # Web server

    web_thread = threading.Thread(
        target=run_web_server,
        daemon=True
    )

    web_thread.start()

    # Telegram

    check_telegram()

    remove_webhook()

    # Polling

    telegram_polling()


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    main()
