import os
import json
import time
import threading
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


# ==============================
# SOZLAMALAR
# ==============================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

PORT = int(os.getenv("PORT", "10000"))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6")

TELEGRAM_TIMEOUT = 40
OPENAI_TIMEOUT = 90

KNOWLEDGE_FILE = "knowledge_base.json"


# ==============================
# TEKSHIRISH
# ==============================

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY topilmadi")


# ==============================
# HTTP
# ==============================

def http_json(url, data=None, headers=None, timeout=60):

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


# ==============================
# TELEGRAM
# ==============================

TELEGRAM_API = (
    "https://api.telegram.org/bot"
    + BOT_TOKEN
    + "/"
)


def telegram(method, data=None):

    return http_json(
        TELEGRAM_API + method,
        data=data,
        timeout=TELEGRAM_TIMEOUT
    )


def check_telegram():

    print(
        "Telegram token tekshirilmoqda...",
        flush=True
    )

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


# ==============================
# XABAR YUBORISH
# ==============================

def send_message(chat_id, text):

    if not text:

        text = (
            "Javob tayyorlashda "
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
                "Xabar yuborishda xato:",
                e,
                flush=True
            )


# ==============================
# BILIM BAZASINI YUKLASH
# ==============================

def load_knowledge_base():

    try:

        if not os.path.exists(
            KNOWLEDGE_FILE
        ):

            print(
                "knowledge_base.json topilmadi.",
                flush=True
            )

            return []

        with open(
            KNOWLEDGE_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        print(
            "Bilim bazasi yuklandi: "
            + str(len(data))
            + " ta hujjat",
            flush=True
        )

        return data

    except Exception as e:

        print(
            "Bilim bazasini yuklashda xato:",
            e,
            flush=True
        )

        return []


KNOWLEDGE_BASE = load_knowledge_base()


# ==============================
# BILIM BAZASIDAN MATN OLISH
# ==============================

def get_knowledge_text(question):

    if not KNOWLEDGE_BASE:

        return ""

    question_words = set(
        question.lower().split()
    )

    documents = []

    for document in KNOWLEDGE_BASE:

        title = str(
            document.get("title", "")
        )

        meta = str(
            document.get("meta", "")
        )

        blocks = document.get(
            "blocks",
            []
        )

        full_text = (
            title
            + " "
            + meta
            + " "
            + " ".join(
                str(x)
                for x in blocks
            )
        )

        lower_text = full_text.lower()

        score = 0

        for word in question_words:

            clean_word = (
                word
                .strip(".,!?;:()[]{}\"'")
            )

            if len(clean_word) >= 3:

                if clean_word in lower_text:

                    score += 1

        documents.append(
            (
                score,
                full_text
            )
        )

    documents.sort(
        key=lambda x: x[0],
        reverse=True
    )

    selected = []

    for score, text in documents[:3]:

        if score > 0:

            selected.append(text)

    if not selected:

        return ""

    result = "\n\n".join(
        selected
    )

    # Juda katta prompt bo'lib ketmasligi uchun
    return result[:18000]


# ==============================
# OPENAI
# ==============================

def openai_answer(question):

    knowledge = get_knowledge_text(
        question
    )

    system_text = """
Siz "Madaniy Meros AI" nomli
O'zbekiston madaniy merosi bo'yicha
ixtisoslashgan yordamchisiz.

Siz quyidagi mavzularda yordam berasiz:

- madaniy meros obyektlari;
- tarixiy-me'moriy obyektlar;
- ularni muhofaza qilish;
- restavratsiya;
- konservatsiya;
- ta'mirlash;
- moslashtirish;
- loyiha hujjatlari;
- ilmiy-ekspert kengashi;
- madaniy meros hududlarida qurilish;
- muhofaza zonalari;
- amaldagi qonunchilik.

Javoblarni o'zbek tilida bering.

Javob:
- aniq;
- tushunarli;
- amaliy;
- imkon qadar qisqa;
- kerak bo'lsa punktlar bilan bo'lsin.

Agar bilim bazasida tegishli ma'lumot mavjud bo'lsa,
avvalo shu ma'lumotga tayaning.

Huquqiy masalalarda qonun yoki qaror raqamini
o'ylab topmang.

Agar ma'lumot yetarli bo'lmasa,
buni ochiq ayting.

Bilim bazasidagi hujjatni amaldagi qonunchilik
sifatida ko'rsatishda ehtiyot bo'ling.
"""


    if knowledge:

        system_text += """

QUYIDA MADANIY MEROS BO'YICHA
BILIM BAZASIDAN TOPILGAN MA'LUMOT:

------------------------------

""" + knowledge + """

------------------------------

Javobni yuq
