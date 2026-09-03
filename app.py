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

        if text.startswith("/help
