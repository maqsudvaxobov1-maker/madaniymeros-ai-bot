import os
import re
import json
import time
import logging
import threading
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# =========================================================
# MADANIY MEROS AI
# STABLE WEBHOOK VERSION
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# MUHIM:
# GitHub dagi fayl nomi aynan shu bo'lishi kerak.
KNOWLEDGE_FILE = os.path.join(
    BASE_DIR,
    "knowledge_base_full_4.json"
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

OPENAI_MODEL = os.getenv(
    "OPENAI_MODEL",
    "gpt-5.6"
).strip()

PORT = int(os.getenv("PORT", "10000"))

RENDER_EXTERNAL_URL = os.getenv(
    "RENDER_EXTERNAL_URL",
    ""
).strip().rstrip("/")

WEBHOOK_PATH = "/telegram/webhook"
WEBHOOK_URL = RENDER_EXTERNAL_URL + WEBHOOK_PATH

BHM = 440000
MAX_TELEGRAM_MESSAGE = 3900

# =========================================================
# TEKSHIRUV
# =========================================================

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY topilmadi")

if not os.path.exists(KNOWLEDGE_FILE):
    raise RuntimeError(
        "Bilim bazasi topilmadi: "
        + KNOWLEDGE_FILE
    )

# =========================================================
# MATNNI NORMALIZATSIYA
# =========================================================

def norm(text):
    text = str(text or "").lower().strip()

    # O'zbek kirill -> lotin
    table = str.maketrans({
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
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
        "ў": "o",
        "ф": "f",
        "х": "x",
        "ҳ": "h",
        "ц": "s",
        "ч": "ch",
        "ш": "sh",
        "ъ": "",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya"
    })

    text = text.translate(table)

    replacements = {
        "oʻ": "o",
        "o‘": "o",
        "o`": "o",
        "gʻ": "g",
        "g‘": "g",
        "g`": "g",
        "ʼ": "",
        "'": "",
        "`": ""
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    # Belgilarni bo'sh joyga almashtirish
    text = re.sub(r"[^a-z0-9\-]+", " ", text)

    # Bir nechta bo'sh joy
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# =========================================================
# BILIM BAZASINI YUKLASH
# =========================================================

def load_knowledge_base():
    logging.info("Bilim bazasi yuklanmoqda: %s", KNOWLEDGE_FILE)

    with open(
        KNOWLEDGE_FILE,
        "r",
        encoding="utf-8"
    ) as f:
        data = json.load(f)

    if isinstance(data, dict):
        documents = data.get("documents", [])

        if not documents:
            documents = data.get("docs", [])

    elif isinstance(data, list):
        documents = data

    else:
        documents = []

    result = []

    for item in documents:
        if not isinstance(item, dict):
            continue

        title = str(
            item.get("title", "")
        ).strip()

        source_file = str(
            item.get("source_file", "")
        ).strip()

        text = str(
            item.get("text", "")
        ).strip()

        if not text:
            text = str(
                item.get("content", "")
            ).strip()

        if not text:
            continue

        result.append({
            "title": title,
            "source_file": source_file,
            "text": text,
            "norm_title": norm(title),
            "norm_source": norm(source_file),
            "norm_text": norm(text)
        })

    if not result:
        raise RuntimeError(
            "Bilim bazasida hujjatlar topilmadi"
        )

    logging.info(
        "Bilim bazasi tayyor. Hujjatlar soni: %s",
        len(result)
    )

    for i, doc in enumerate(result, 1):
        logging.info(
            "%s. %s",
            i,
            doc["title"][:120]
        )

    return result


DOCUMENTS = load_knowledge_base()


# =========================================================
# HUJJATNI TOPISH
# =========================================================

def get_doc(number):
    number = norm(number)

    for doc in DOCUMENTS:

        haystack = (
            doc["norm_title"]
            + " "
            + doc["norm_source"]
        )

        if number in haystack:
            return doc

    return None


# =========================================================
# HUJJAT RAQAMINI ANIQLASH
# =========================================================

def detect_document_number(question):
    q = norm(question)

    # 269-II
    if re.search(r"\b269\s*-\s*ii\b", q):
        return "269"

    # PQ / ПҚ raqamlar
    m = re.search(
        r"\b(?:pq|pk)\s*[- ]?\s*(\d+)\b",
        q
    )

    if m:
        return m.group(1)

    # VMQ / ВМҚ
    m = re.search(
        r"\b(?:vmq|vm)\s*[- ]?\s*(\d+)\b",
        q
    )

    if m:
        return m.group(1)

    # oddiy 119-son, 119-sonli, 119 qaror
    m = re.search(
        r"\b(\d{1,5})\s*(?:sonli|son|qaror|qonun)\b",
        q
    )

    if m:
        return m.group(1)

    # savolda shunchaki "119"
    m = re.search(
        r"\b(119|269)\b",
        q
    )

    if m:
        return m.group(1)

    return None


# =========================================================
# SO'ZLARNI AJRATISH
# =========================================================

STOP_WORDS = {
    "va",
    "ham",
    "bu",
    "shu",
    "uchun",
    "bilan",
    "qanday",
    "qaysi",
    "nima",
    "qachon",
    "menga",
    "kerak",
    "bering",
    "ber",
    "haqida",
    "bo'yicha",
    "boyicha",
    "siz",
    "men",
    "ning",
    "ni",
    "ga",
    "da",
    "dan",
    "mi",
    "mumkin",
    "boladi",
    "bo'ladi"
}


def keywords(question):
    q = norm(question)

    words = re.findall(
        r"[a-z0-9]+",
        q
    )

    result = []

    for word in words:

        if word in STOP_WORDS:
            continue

        if len(word) < 2:
            continue

        result.append(word)

    return list(dict.fromkeys(result))


# =========================================================
# HUJJAT MATNINI BO'LAKLARGA AJRATISH
# =========================================================

def make_chunks(text, size=3500, overlap=500):
    text = str(text or "")

    if len(text) <= size:
        return [text]

    chunks = []

    start = 0

    while start < len(text):
        end = start + size

        chunk = text[start:end]

        if chunk.strip():
            chunks.append(chunk)

        if end >= len(text):
            break

        start = end - overlap

    return chunks


# =========================================================
# BILIM BAZASIDAN QIDIRISH
# =========================================================

def search_knowledge(question, limit=6):
    q = norm(question)
    keys = keywords(question)

    document_number = detect_document_number(question)

    candidates = []

    for doc in DOCUMENTS:

        title = doc["norm_title"]
        source = doc["norm_source"]
        text = doc["norm_text"]

        doc_bonus = 0

        if document_number:
            if document_number in title:
                doc_bonus += 100

            if document_number in source:
                doc_bonus += 100

        chunks = make_chunks(
            doc["text"],
            3500,
            500
        )

        for chunk in chunks:

            nchunk = norm(chunk)

            score = doc_bonus

            # Savolning to'liq iborasi
            if len(q) >= 8 and q in nchunk:
                score += 60

            # So'zlar bo'yicha
            for key in keys:

                if key in nchunk:
                    score += 3

                    if key in title:
                        score += 5

                    if key in source:
                        score += 5

            # Muhim huquqiy so'zlar
            important = [
                "qaror",
                "qonun",
                "madaniy",
                "meros",
                "ekspert",
                "ekspertiza",
                "restavratsiya",
                "tamirlash",
                "ruxsat",
                "davlat xizmat",
                "tolov",
                "bhm",
                "kadastr",
                "yunesko",
                "muhofaza"
            ]

            for word in important:
                if word in q and word in nchunk:
                    score += 7

            if score > 0:
                candidates.append({
                    "score": score,
                    "title": doc["title"],
                    "source_file": doc["source_file"],
                    "text": chunk
                })

    candidates.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return candidates[:limit]


# =========================================================
# MAXSUS JAVOBLAR
# =========================================================

def direct_answer(question):
    q = norm(question)

    # -----------------------------------------------------
    # 269-II-son Qonun
    # -----------------------------------------------------

    if (
        "269" in q
        and (
            "qachon" in q
            or "qabul" in q
            or "sana" in q
        )
    ):

        doc = get_doc("269")

        title = ""

        if doc:
            title = doc["title"]

        return (
            "269-II-son Qonun 2001-yil 30-avgustda "
            "qabul qilingan.\n\n"
            "Qonun nomi:\n"
            "“Madaniy meros obyektlarini muhofaza "
            "qilish va ulardan foydalanish to‘g‘risida”gi "
            "Qonun.\n\n"
            "Manba: 269-II-son Qonun, 30.08.2001."
        )

# -----------------------------------------------------
# 119-son qaror — ANIQ JAVOB
# -----------------------------------------------------

if (
    "119" in q
    and (
        "qaror" in q
        or "vmq" in q
        or "sonli" in q
        or "son" in q
        or "qachon" in q
        or "nomi" in q
        or "toliq" in q
    )
):
    return (
        "119-son Vazirlar Mahkamasi qarori "
        "2021-yil 3-martda qabul qilingan.\n\n"
        
        "To‘liq nomi:\n"
        "“Moddiy madaniy meros obyektlari va "
        "YuNESKOning Umumjahon merosi ro‘yxatiga "
        "kiritilgan hududlar muhofazasini kuchaytirish "
        "chora-tadbirlari to‘g‘risida”.\n\n"
        
        "Manba: O‘zbekiston Respublikasi Vazirlar "
        "Mahkamasining 2021-yil 3-martdagi 119-son qarori."
    )

    # -----------------------------------------------------
    # Davlat xizmatlari
    # -----------------------------------------------------

    service_words = [
        "davlat xizmat",
        "davlat xizm",
        "tolov",
        "tulov",
        "narx",
        "qancha",
        "xizmatlar"
    ]

    if any(word in q for word in service_words):

        if (
            "agentlik" in q
            or "madaniy meros" in q
            or "xizmat" in q
        ):

            return (
                "Madaniy meros agentligi bo‘yicha "
                "davlat xizmatlari va to‘lovlar:\n\n"

                "1. Moddiy madaniy meros obyektini "
                "davlat kadastriga kiritish yoki undan "
                "chiqarish — YIDXP orqali 0,5 BHM.\n"
                f"Amaldagi hisobda: {BHM // 2:,} so‘m.\n\n"

                "2. Moddiy madaniy meros obyektining "
                "davlat kadastriga kiritilgan yoki "
                "kiritilmaganligi haqida ma’lumot.\n\n"

                "3. Arxeologiya ashyosining davlat "
                "katalogiga kiritilgan yoki "
                "kiritilmaganligi haqida ma’lumot.\n\n"

                "4. Milliy muzey fondi ashyolari va "
                "kolleksiyalarining davlat katalogiga "
                "kiritilganligi haqida ma’lumotnoma.\n\n"

                "To‘lov miqdori aniq xizmat turiga va "
                "amaldagi normativ hujjat talablariga "
                "bog‘liq bo‘lishi mumkin."
            )

    return None


# =========================================================
# OPENAI
# =========================================================

def ask_openai(question, context):
    system_prompt = """
Siz “Madaniy Meros AI” nomli O‘zbekiston
madaniy merosi bo‘yicha huquqiy-amaliy yordamchisiz.

Asosiy qoida:
1. Javobni berilgan bilim bazasidagi hujjatlarga
   tayangan holda yozing.
2. Bilim bazasida aniq ma'lumot bo‘lmasa,
   uni o‘ylab topmang.
3. Qonun, Prezident qarori yoki Vazirlar Mahkamasi
   qarori raqami, sanasi va nomini aralashtirmang.
4. Javobni o‘zbek tilida yozing.
5. Foydalanuvchining kirill yoki lotin yozuvida
   yozganiga moslashing.
6. Kerak bo‘lsa hujjat nomi, sana, band va
   amaliy tartibni aniq ajrating.
7. To‘lovlarda BHM miqdorini alohida ko‘rsating.
8. Agar manbada javob bo‘lmasa:
   “Taqdim etilgan bilim bazasida bu savolga
   yetarli aniq ma’lumot topilmadi” deb ayting.
9. Hech qachon mavjud bo‘lmagan norma yoki bandni
   to‘qib chiqarmang.
10. Javobni qisqa, lekin amaliy va tushunarli bering.
"""

    user_prompt = (
        "SAVOL:\n"
        + question
        + "\n\n"
        "BILIM BAZASIDAN TOPILGAN MANBALAR:\n"
        + context
    )

    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ]
    }

    data = json.dumps(
        payload,
        ensure_ascii=False
    ).encode("utf-8")

    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": (
                "Bearer "
                + OPENAI_API_KEY
            )
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=90
        ) as response:

            raw = response.read().decode(
                "utf-8"
            )

            result = json.loads(raw)

            return (
                result["choices"][0]
                ["message"]["content"]
                .strip()
            )

    except urllib.error.HTTPError as e:

        body = e.read().decode(
            "utf-8",
            errors="ignore"
        )

        logging.error(
            "OpenAI HTTP %s: %s",
            e.code,
            body[:2000]
        )

        return (
            "OpenAI API bilan bog‘lanishda xatolik "
            f"yuz berdi ({e.code})."
        )

    except Exception as e:

        logging.exception(
            "OpenAI xatosi"
        )

        return (
            "Javobni shakllantirishda texnik xatolik "
            "yuz berdi."
        )


# =========================================================
# TELEGRAM API
# =========================================================

def telegram_api(method, payload):
    url = (
        "https://api.telegram.org/bot"
        + BOT_TOKEN
        + "/"
        + method
    )

    data = json.dumps(
        payload,
        ensure_ascii=False
    ).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=30
        ) as response:

            raw = response.read().decode(
                "utf-8"
            )

            return json.loads(raw)

    except Exception as e:

        logging.exception(
            "Telegram API xatosi"
        )

        return {
            "ok": False,
            "error": str(e)
        }


# =========================================================
# WEBHOOK O'RNATISH
# =========================================================

def setup_webhook():

    if not RENDER_EXTERNAL_URL:

        logging.warning(
            "RENDER_EXTERNAL_URL topilmadi. "
            "Webhook o'rnatilmadi."
        )

        return

    logging.info(
        "Webhook o'rnatilmoqda: %s",
        WEBHOOK_URL
    )

    result = telegram_api(
        "setWebhook",
        {
            "url": WEBHOOK_URL,
            "drop_pending_updates": False
        }
    )

    logging.info(
        "Webhook natijasi: %s",
        result
    )


# =========================================================
# TELEGRAMGA XABAR YUBORISH
# =========================================================

def split_message(text, limit=MAX_TELEGRAM_MESSAGE):

    text = str(text or "").strip()

    if len(text) <= limit:
        return [text]

    parts = []

    while len(text) > limit:

        cut = text.rfind(
            "\n",
            0,
            limit
        )

        if cut < 1000:
            cut = text.rfind(
                " ",
                0,
                limit
            )

        if cut < 1000:
            cut = limit

        parts.append(
            text[:cut].strip()
        )

        text = text[cut:].strip()

    if text:
        parts.append(text)

    return parts


def send_message(chat_id, text):

    for part in split_message(text):

        telegram_api(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": part
            }
        )


# =========================================================
# SAVOLGA JAVOB
# =========================================================

def answer_question(question):

    # Avval maxsus aniq javoblar
    direct = direct_answer(question)

    if direct:
        return direct

    # Keyin bilim bazasidan qidirish
    results = search_knowledge(
        question,
        limit=6
    )

    if not results:

        return (
            "Taqdim etilgan bilim bazasida "
            "bu savolga yetarli aniq ma’lumot "
            "topilmadi."
        )

    context_parts = []

    for item in results:

        context_parts.append(
            "HUJJAT: "
            + item["title"]
            + "\n"
            "MANBA FAYL: "
            + item["source_file"]
            + "\n"
            "MATN:\n"
            + item["text"]
        )

    context = "\n\n--------------------\n\n".join(
        context_parts
    )

    # Juda katta context yubormaslik
    context = context[:18000]

    return ask_openai(
        question,
        context
    )


# =========================================================
# TELEGRAM UPDATENI QABUL QILISH
# =========================================================

def process_update(update):

    if not isinstance(update, dict):
        return

    message = update.get("message")

    if not isinstance(message, dict):
        return

    chat = message.get("chat", {})
    chat_id = chat.get("id")

    if not chat_id:
        return

    text = message.get("text", "")

    if not text:
        return

    text = str(text).strip()

    logging.info(
        "Savol qabul qilindi: %s",
        text[:500]
    )

    # /start
    if text.lower().startswith("/start"):

        send_message(
            chat_id,
            "Assalomu alaykum!\n\n"
            "Men Madaniy Meros AI botiman.\n"
            "O‘zbekiston madaniy merosiga oid "
            "qonunlar, qarorlar, davlat xizmatlari, "
            "ekspertiza, restavratsiya va boshqa "
            "masalalar bo‘yicha savolingizni yozing."
        )

        return

    # /help
    if text.lower().startswith("/help"):

        send_message(
            chat_id,
            "Savolingizni aniq yozing.\n\n"
            "Masalan:\n"
            "• 269-II-son Qonun qachon qabul qilingan?\n"
            "• 119-sonli qarorning to‘liq nomi nima?\n"
            "• Madaniy meros obyektida restavratsiya "
            "qilish tartibi qanday?\n"
            "• Davlat xizmatlari uchun to‘lov qancha?"
        )

        return

    try:

        answer = answer_question(text)

        send_message(
            chat_id,
            answer
        )

    except Exception:

        logging.exception(
            "Savolga javob berishda xatolik"
        )

        send_message(
            chat_id,
            "Kechirasiz, savolni qayta ishlashda "
            "texnik xatolik yuz berdi."
        )


# =========================================================
# HTTP SERVER
# =========================================================

class Handler(BaseHTTPRequestHandler):

    def log_message(
        self,
        format,
        *args
    ):
        return

    def do_GET(self):

        if self.path == "/":

            body = (
                "Madaniy Meros AI ishlayapti."
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

            return

        if self.path == "/health":

            body = b"OK"

            self.send_response(200)
            self.send_header(
                "Content-Type",
                "text/plain"
            )
            self.send_header(
                "Content-Length",
                str(len(body))
            )
            self.end_headers()

            self.wfile.write(body)

            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):

        if self.path != WEBHOOK_PATH:

            self.send_response(404)
            self.end_headers()
            return

        try:

            length = int(
                self.headers.get(
                    "Content-Length",
                    "0"
                )
            )

            raw = self.rfile.read(length)

            update = json.loads(
                raw.decode("utf-8")
            )

            # Telegramga darhol 200 qaytarish
            self.send_response(200)
            self.send_header(
                "Content-Type",
                "text/plain"
            )
            self.end_headers()
            self.wfile.write(b"OK")

            # Savolni alohida threadda ishlash
            threading.Thread(
                target=process_update,
                args=(update,),
                daemon=True
            ).start()

        except Exception:

            logging.exception(
                "Webhook POST xatosi"
            )

            try:
                self.send_response(200)
                self.end_headers()
            except Exception:
                pass


# =========================================================
# SERVERNI ISHGA TUSHIRISH
# =========================================================

def main():

    logging.info(
        "======================================"
    )

    logging.info(
        "MADANIY MEROS AI ISHGA TUSHMOQDA"
    )

    logging.info(
        "Knowledge base: %s",
        KNOWLEDGE_FILE
    )

    logging.info(
        "Documents: %s",
        len(DOCUMENTS)
    )

    logging.info(
        "Model: %s",
        OPENAI_MODEL
    )

    logging.info(
        "Port: %s",
        PORT
    )

    # Webhook
    setup_webhook()

    server = ThreadingHTTPServer(
        ("0.0.0.0", PORT),
        Handler
    )

    logging.info(
        "Server ishga tushdi: port %s",
        PORT
    )

    server.serve_forever()


if __name__ == "__main__":
    main()
