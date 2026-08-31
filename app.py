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

TELEGRAM_TIMEOUT = 35
OPENAI_TIMEOUT = 90

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
        body = json.dumps(data).encode("utf-8")
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

def telegram(method, data=None):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

    return http_json(
        url,
        data=data,
        timeout=TELEGRAM_TIMEOUT
    )


def send_message(chat_id, text):

    if not text:
        text = "Kechirasiz, javob olinmadi."

    # Telegram bitta xabar uchun taxminan 4096 belgilik limitga ega.
    chunks = [
        text[i:i + 3900]
        for i in range(0, len(text), 3900)
    ]

    for chunk in chunks:

        try:

            result = telegram(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": chunk
                }
            )

            if not result.get("ok"):
                print(
                    "Telegram sendMessage xatosi:",
                    result,
                    flush=True
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

    payload = {
        "model": "gpt-4o-mini",

        "messages": [
            {
                "role": "system",
                "content": (
                    "Siz Madaniy Meros AI yordamchisisiz. "
                    "O'zbekiston madaniy merosi, "
                    "tarixiy-me'moriy obyektlar, "
                    "restavratsiya, ta'mirlash, "
                    "ilmiy-ekspertiza va loyiha hujjatlari "
                    "bo'yicha yordam bering. "
                    "Javoblarni o'zbek tilida, "
                    "aniq, tushunarli va foydali yozing. "
                    "Agar savol rasmiy hujjatga oid bo'lsa, "
                    "rasmiy uslubdan foydalaning."
                )
            },

            {
                "role": "user",
                "content": question
            }
        ],

        "temperature": 0.2,

        "max_tokens": 1500
    }

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    result = http_json(
        url,
        data=payload,
        headers=headers,
        timeout=OPENAI_TIMEOUT
    )

    try:

        answer = result["choices"][0]["message"]["content"]

        if not answer:
            raise RuntimeError("OpenAI bo'sh javob qaytardi")

        return answer.strip()

    except Exception:

        print(
            "OpenAI javobi noto'g'ri:",
            result,
            flush=True
        )

        raise RuntimeError("OpenAI javobini o'qib bo'lmadi")


# =========================================================
# TELEGRAM BOT
# =========================================================

def telegram_bot():

    print("====================================", flush=True)
    print("Madaniy Meros AI BOT ISHLADI", flush=True)
    print("====================================", flush=True)

    # Botning webhookini o'chirish.
    # Polling bilan ishlash uchun kerak.
    try:

        result = telegram(
            "deleteWebhook",
            {
                "drop_pending_updates": False
            }
        )

        print(
            "deleteWebhook:",
            result,
            flush=True
        )

    except Exception as e:

        print(
            "deleteWebhook xatosi:",
            e,
            flush=True
        )

    # Eski update'larni tashlab yuboramiz.
    offset = None

    try:

        result = telegram(
            "getUpdates",
            {
                "offset": -1,
                "timeout": 1
            }
        )

        if result.get("ok") and result.get("result"):

            offset = (
                result["result"][-1]["update_id"] + 1
            )

    except Exception as e:

        print(
            "Boshlang'ich getUpdates xatosi:",
            e,
            flush=True
        )

    print(
        "Telegram polling tayyor.",
        flush=True
    )

    # Asosiy sikl
    while True:

        try:

            params = {
                "timeout": 30,
                "allowed_updates": [
                    "message"
                ]
            }

            if offset is not None:
                params["offset"] = offset

            result = telegram(
                "getUpdates",
                params
            )

            if not result.get("ok"):

                print(
                    "getUpdates xatosi:",
                    result,
                    flush=True
                )

                time.sleep(3)
                continue

            updates = result.get("result", [])

            for update in updates:

                offset = (
                    update["update_id"] + 1
                )

                process_update(update)

        except Exception as e:

            print(
                "BOT SIKL XATOSI:",
                repr(e),
                flush=True
            )

            time.sleep(5)


# =========================================================
# UPDATE QAYTA ISHLASH
# =========================================================

def process_update(update):

    try:

        message = update.get("message")

        if not message:
            return

        chat = message.get("chat")

        if not chat:
            return

        chat_id = chat.get("id")

        text = message.get("text", "").strip()

        if not text:
            return

        username = (
            message.get("from", {})
            .get("username", "")
        )

        print(
            f"USER @{username}: {text}",
            flush=True
        )

        # -----------------------------
        # START
        # -----------------------------

        if text == "/start":

            send_message(
                chat_id,
                "Assalomu alaykum! 👋\n\n"
                "Men Madaniy Meros AI yordamchisiman.\n\n"
                "O'zbekiston madaniy merosi, "
                "tarixiy-me'moriy obyektlar, "
                "restavratsiya va loyiha hujjatlari "
                "bo'yicha savolingizni yozing."
            )

            return

        # -----------------------------
        # HELP
        # -----------------------------

        if text == "/help":

            send_message(
                chat_id,
                "Yordam:\n\n"
                "Savolingizni oddiy tilda yozing.\n"
                "Masalan:\n\n"
                "• Madaniy meros obyekti nima?\n"
                "• Restavratsiya loyihasida nimalar bo'ladi?\n"
                "• Loyiha xatini rasmiy qilib bering.\n"
                "• Tarixiy bino fasadini qanday saqlash kerak?"
            )

            return

        # -----------------------------
        # BO'SH SAVOL
        # -----------------------------

        if len(text) < 2:

            send_message(
                chat_id,
                "Iltimos, savolingizni yozing."
            )

            return

        # -----------------------------
        # ISHLAYAPTI
        # -----------------------------

        send_message(
            chat_id,
            "⏳ Саволингизни кўриб чиқяпман..."
        )

        # -----------------------------
        # OPENAI
        # -----------------------------

        try:

            answer = openai_answer(text)

            send_message(
                chat_id,
                answer
            )

        except urllib.error.HTTPError as e:

            print(
                "OpenAI HTTP xatosi:",
                e,
                flush=True
            )

            send_message(
                chat_id,
                "⚠️ AI xizmatida vaqtinchalik xatolik yuz berdi.\n"
                "Birozdan keyin yana urinib ko'ring."
            )

        except Exception as e:

            print(
                "AI XATOSI:",
                repr(e),
                flush=True
            )

            send_message(
                chat_id,
                "⚠️ Javob tayyorlashda xatolik yuz berdi.\n"
                "
