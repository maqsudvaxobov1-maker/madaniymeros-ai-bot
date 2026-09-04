import os
import re
import json
import threading
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


# =========================
# SOZLAMALAR
# =========================

BASE = os.path.dirname(os.path.abspath(__file__))

KB_FILE = os.path.join(
    BASE,
    "knowledge_base_4.json"
)

BOT_TOKEN = os.getenv(
    "BOT_TOKEN",
    ""
).strip()

OPENAI_API_KEY = os.getenv(
    "OPENAI_API_KEY",
    ""
).strip()

MODEL = os.getenv(
    "OPENAI_MODEL",
    "gpt-5.6"
).strip()

PORT = int(
    os.getenv(
        "PORT",
        "10000"
    )
)

RENDER_URL = os.getenv(
    "RENDER_EXTERNAL_URL",
    ""
).strip().rstrip("/")

WEBHOOK_PATH = "/telegram/webhook"

BHM = 440000

MAX_MSG = 3900


# =========================
# TEKSHIRUV
# =========================

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN topilmadi"
    )

if not OPENAI_API_KEY:
    raise RuntimeError(
        "OPENAI_API_KEY topilmadi"
    )


# =========================
# MATNNI NORMALIZATSIYA
# =========================

def norm(text):
    s = str(text or "").lower().strip()

    table = str.maketrans({
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "ғ": "g",
        "д": "d",
        "е": "e",
        "ё": "yo",
        "ж": "j",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "қ": "q",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ў": "u",
        "ф": "f",
        "х": "x",
        "ҳ": "h",
        "ц": "s",
        "ч": "ch",
        "ш": "sh",
        "ъ": "",
        "ы": "i",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya"
    })

    s = s.translate(table)

    replacements = {
        "ʼ": "'",
        "’": "'",
        "ʻ": "'",
        "`": "'",
        "–": "-",
        "—": "-"
    }

    for a, b in replacements.items():
        s = s.replace(a, b)

    s = re.sub(
        r"[^a-z0-9\-]+",
        " ",
        s
    )

    s = re.sub(
        r"\s+",
        " ",
        s
    )

    return s.strip()


# =========================
# BILIM BAZASINI YUKLASH
# =========================

def load_kb():

    if not os.path.exists(KB_FILE):
        raise RuntimeError(
            "knowledge_base_4.json topilmadi"
        )

    with open(
        KB_FILE,
        "r",
        encoding="utf-8"
    ) as f:
        data = json.load(f)

    if isinstance(data, dict):
        docs = data.get(
            "documents",
            []
        )
    elif isinstance(data, list):
        docs = data
    else:
        docs = []

    result = []

    for d in docs:

        if not isinstance(d, dict):
            continue

        result.append({
            "title": str(
                d.get("title", "")
            ),
            "source_file": str(
                d.get("source_file", "")
            ),
            "text": str(
                d.get("text", "")
            )
        })

    return result


DOCS = load_kb()


# =========================
# HUJJAT TOPISH
# =========================

def get_doc(number):

    number = str(number)

    for d in DOCS:

        title = norm(
            d["title"]
        )

        source = norm(
            d["source_file"]
        )

        if number in title or number in source:
            return d

    return None


# =========================
# BILIM BAZASIDAN QIDIRISH
# =========================

def search_kb(question):

    q = norm(question)

    words = [
        x
        for x in q.split()
        if len(x) >= 3
    ]

    if not words:
        return []

    scored = []

    for d in DOCS:

        title = norm(
            d["title"]
        )

        source = norm(
            d["source_file"]
        )

        text = norm(
            d["text"]
        )

        score = 0

        for word in words:

            if word in title:
                score += 10

            if word in source:
                score += 8

            score += min(
                text.count(word),
                10
            )

        numbers = re.findall(
            r"\b\d{2,4}\b",
            q
        )

        for number in numbers:

            if number in title:
                score += 30

        if score > 0:
            scored.append(
                (score, d)
            )

    scored.sort(
        key=lambda x: x[0],
        reverse=True
    )

    result = []

    for score, d in scored[:6]:

        result.append(
            "HUJJAT: "
            + d["title"]
            + "\nMANBA: "
            + d["source_file"]
            + "\nMATN:\n"
            + d["text"][:5000]
        )

    return result


# =========================
# ANIQ JAVOBLAR
# =========================

def direct_answer(question):

    q = norm(question)

    # =====================
    # 269-II-SON QONUN
    # =====================

    if (
        "269" in q
        and any(
            x in q
            for x in [
                "qachon",
                "qabul",
                "sana",
                "nomi"
            ]
        )
    ):

        doc = get_doc("269")

        answer = (
            "269-II-son Qonun "
            "2001-yil 30-avgustda "
            "qabul qilingan.\n\n"
            "Nomi: “Madaniy meros "
            "obyektlarini muhofaza "
            "qilish va ulardan "
            "foydalanish to‘g‘risida”gi "
            "Qonun."
        )

        if doc:
            answer += (
                "\n\nManba: "
                + doc["title"]
            )

        return answer


    # =====================
    # 119-SON QAROR
    # =====================

    if (
        "119" in q
        and any(
            x in q
            for x in [
                "qaror",
                "vmq",
                "sonli",
                "qachon",
                "qabul",
                "sana",
                "nomi",
                "toliq"
            ]
        )
    ):

        doc = get_doc("119")

        if doc:

            return (
                "119-son qaror "
                "2021-yil 3-martda "
                "qabul qilingan.\n\n"
                "To‘liq nomi:\n"
                + doc["title"]
                + "\n\n"
                "Manba: O‘zbekiston Respublikasi "
                "Vazirlar Mahkamasining "
                "2021-yil 3-martdagi "
                "119-son qarori."
            )

        return (
            "119-son qaror "
            "2021-yil 3-martda "
            "qabul qilingan."
        )


    # =====================
    # DAVLAT XIZMATLARI
    # =====================

    service = any(
        x in q
        for x in [
            "davlat xizm",
            "davlat xizmat",
            "tolov",
            "tulov",
            "bhm",
            "narx",
            "qancha",
            "agentlik"
        ]
    )

    if service:

        return (
            "Madaniy meros agentligi "
            "bo‘yicha asosiy davlat "
            "xizmatlari:\n\n"

            "1. Moddiy madaniy meros "
            "obyektini davlat kadastriga "
            "kiritish yoki undan chiqarish "
            "— 0,5 BHM.\n"
            "1 BHM 440 000 so‘m bo‘lsa, "
            "to‘lov 220 000 so‘m.\n\n"

            "2. Moddiy madaniy meros "
            "obyektining davlat kadastriga "
            "kiritilgan yoki kiritilmaganligi "
            "haqida ma’lumot.\n\n"

            "3. Arxeologiya ashyosining "
            "davlat katalogiga kiritilgan "
            "yoki kiritilmaganligi haqida "
            "ma’lumot.\n\n"

            "4. Milliy muzey fondi "
            "ashyolari va kolleksiyalarining "
            "davlat katalogiga kiritilganligi "
            "haqida ma’lumotnoma.\n\n"

            "Ayrim to‘lovlar:\n"
            "• 10 BHM — 4 400 000 so‘m;\n"
            "• 5 BHM — 2 200 000 so‘m;\n"
            "• 20 BHM — 8 800 000 so‘m;\n"
            "• 1 BHM — 440 000 so‘m;\n"
            "• 0,5 BHM — 220 000 so‘m;\n"
            "• 7 BHM — 3 080 000 so‘m;\n"
            "• 4 BHM — 1 760 000 so‘m."
        )

    return None


# =========================
# OPENAI
# =========================

def ask_openai(
    question,
    context
):

    system = """
Siz “Madaniy Meros AI”
nomli huquqiy-amaliy
yordamchisiz.

Faqat berilgan bilim
bazasidagi ma’lumotlarga
tayangan holda javob bering.

Bilim bazasida ma’lumot
bo‘lmasa, buni ochiq ayting.

Qonun, qaror, band, muddat,
to‘lov yoki talabni
o‘ylab topmang.

Javobni o‘zbek tilida
aniq va tushunarli bering.

Imkon qadar hujjat nomi,
raqami va manbasini ko‘rsating.
"""

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": system
            },
            {
                "role": "user",
                "content":
                    "SAVOL:\n"
                    + question
                    + "\n\nBILIM BAZASI:\n"
                    + context
            }
        ]
    }

    data = json.dumps(
        payload
    ).encode("utf-8")

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=data,
        headers={
            "Content-Type":
                "application/json",
            "Authorization":
                "Bearer "
                + OPENAI_API_KEY
        },
        method="POST"
    )

    try:

        with urllib.request.urlopen(
            req,
            timeout=90
        ) as response:

            result = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

        return (
            result["choices"][0]
            ["message"]["content"]
            .strip()
        )

    except Exception as e:

        print(
            "OpenAI xatosi:",
            e
        )

        return (
            "Javob tayyorlashda "
            "texnik xatolik yuz berdi. "
            "Savolni yana yuboring."
        )


# =========================
# SAVOLGA JAVOB
# =========================

def answer_question(question):

    direct = direct_answer(
        question
    )

    if direct:
        return direct

    chunks = search_kb(
        question
    )

    if not chunks:

        return (
            "Savol bo‘yicha bilim "
            "bazasida yetarli aniq "
            "ma’lumot topilmadi.\n\n"
            "Iltimos, hujjat raqami, "
            "obyekt nomi yoki masalani "
            "aniqroq yozing."
        )

    context = (
        "\n\n----------------\n\n"
        .join(chunks)
    )

    return ask_openai(
        question,
        context
    )


# =========================
# TELEGRAM API
# =========================

def telegram(
    method,
    payload=None
):

    url = (
        "https://api.telegram.org/"
        "bot"
        + BOT_TOKEN
        + "/"
        + method
    )

    data = None

    if payload is not None:

        data = urllib.parse.urlencode(
            payload
        ).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        method=(
            "POST"
            if data
            else "GET"
        )
    )

    try:

        with urllib.request.urlopen(
            req,
            timeout=30
        ) as response:

            return json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

    except Exception as e:

        print(
            "Telegram API xatosi:",
            e
        )

        return {
            "ok": False,
            "error": str(e)
        }


# =========================
# XABAR YUBORISH
# =========================

def send_message(
    chat_id,
    text
):

    text = text or (
        "Javob tayyorlanmadi."
    )

    parts = [
        text[i:i + MAX_MSG]
        for i in range(
            0,
            len(text),
            MAX_MSG
        )
    ]

    for part in parts:

        telegram(
            "sendMessage",
            {
                "chat_id":
                    str(chat_id),
                "text":
                    part
            }
        )


# =========================
# TELEGRAM UPDATE
# =========================

def process_update(update):

    try:

        message = (
            update.get("message")
            or {}
        )

        chat = (
            message.get("chat")
            or {}
        )

        chat_id = chat.get(
            "id"
        )

        if not chat_id:
            return

        text = (
            message.get(
                "text",
                ""
            )
            .strip()
        )

        if not text:
            return

        if text == "/start":

            send_message(
                chat_id,
                "Assalomu alaykum!\n\n"
                "Men Madaniy Meros AI "
                "yordamchisiman.\n\n"
                "Madaniy meros obyektlari, "
                "qonunlar, qarorlar, "
                "davlat xizmatlari, "
                "ekspertiza, restavratsiya "
                "va boshqa masalalar "
                "bo‘yicha savolingizni "
                "yuboring."
            )

            return

        answer = answer_question(
            text
        )

        send_message(
            chat_id,
            answer
        )

    except Exception as e:

        print(
            "Update xatosi:",
            e
        )


# =========================
# WEB SERVER
# =========================

class Handler(
    BaseHTTPRequestHandler
):

    def log_message(
        self,
        format,
        *args
    ):
        return

    def do_GET(self):

        if (
            self.path == "/"
            or self.path == "/health"
        ):

            body = (
                b"Madaniy Meros AI is running"
            )

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

            return

        self.send_response(
            404
        )

        self.end_headers()

    def do_POST(self):

        if (
            self.path
            != WEBHOOK_PATH
        ):

            self.send_response(
                404
            )

            self.end_headers()

            return

        try:

            length = int(
                self.headers.get(
                    "Content-Length",
                    "0"
                )
            )

            raw = self.rfile.read(
                length
            )

            update = json.loads(
                raw.decode(
                    "utf-8"
                )
            )

            threading.Thread(
                target=process_update,
                args=(update,),
                daemon=True
            ).start()

            self.send_response(
                200
            )

            self.send_header(
                "Content-Type",
                "text/plain"
            )

            self.end_headers()

            self.wfile.write(
                b"OK"
            )

        except Exception as e:

            print(
                "Webhook xatosi:",
                e
            )

            self.send_response(
                200
            )

            self.end_headers()

            self.wfile.write(
                b"OK"
            )


# =========================
# WEBHOOKNI O‘RNATISH
# =========================

def set_webhook():

    if not RENDER_URL:

        print(
            "RENDER_EXTERNAL_URL topilmadi"
        )

        return

    webhook_url = (
        RENDER_URL
        + WEBHOOK_PATH
    )

    result = telegram(
        "setWebhook",
        {
            "url":
                webhook_url,
            "drop_pending_updates":
                "true"
        }
    )

    print(
        "Webhook:",
        webhook_url
    )

    print(
        "Webhook natijasi:",
        result
    )


# =========================
# ISHGA TUSHIRISH
# =========================

if __name__ == "__main__":

    print(
        "Madaniy Meros AI ishga tushmoqda..."
    )

    print(
        "Bilim bazasi:",
        KB_FILE
    )

    print(
        "Hujjatlar soni:",
        len(DOCS)
    )

    set_webhook()

    server = ThreadingHTTPServer(
        (
            "0.0.0.0",
            PORT
        ),
        Handler
    )

    print(
        "Server port:",
        PORT
    )

    server.serve_forever()
