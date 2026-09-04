import os
import re
import json
import logging
import threading
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# =========================================================
# MADANIY MEROS AI
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

BASE = os.path.dirname(os.path.abspath(__file__))

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6").strip()

PORT = int(os.getenv("PORT", "10000"))

RENDER_URL = os.getenv(
    "RENDER_EXTERNAL_URL",
    ""
).strip().rstrip("/")

WEBHOOK_PATH = "/telegram/webhook"
WEBHOOK_URL = RENDER_URL + WEBHOOK_PATH

MAX_LEN = 3900


# =========================================================
# KALITLAR
# =========================================================

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY topilmadi")


# =========================================================
# BILIM BAZASINI TOPISH
# =========================================================

KB_NAMES = [
    "knowledge_base_full_4.json",
    "knowledge_base_4.json",
    "knowledge_base.json",
    "knowledge_base_full.json",
    "knowledge_base_full_old.json"
]


def find_kb():
    for name in KB_NAMES:
        path = os.path.join(BASE, name)

        if os.path.isfile(path):
            logging.info("Bilim bazasi: %s", name)
            return path

    for name in os.listdir(BASE):
        if (
            name.lower().endswith(".json")
            and "knowledge" in name.lower()
        ):
            path = os.path.join(BASE, name)
            logging.info("Bilim bazasi: %s", name)
            return path

    raise RuntimeError(
        "Bilim bazasi JSON fayli topilmadi"
    )


KB_FILE = find_kb()


# =========================================================
# MATNNI NORMALIZATSIYA
# =========================================================

def norm(text):
    text = str(text or "").lower()

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

    for ch in ["ʻ", "ʼ", "’", "‘", "`", "'"]:
        text = text.replace(ch, "")

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text
    )

    return re.sub(
        r"\s+",
        " ",
        text
    ).strip()


# =========================================================
# BILIM BAZASI
# =========================================================

def load_kb():
    with open(
        KB_FILE,
        "r",
        encoding="utf-8"
    ) as f:
        data = json.load(f)

    if isinstance(data, dict):
        docs = data.get("documents", [])

        if not docs:
            docs = data.get("docs", [])

    elif isinstance(data, list):
        docs = data

    else:
        docs = []

    result = []

    for item in docs:

        if not isinstance(item, dict):
            continue

        title = str(
            item.get("title", "")
        ).strip()

        source = str(
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
            "source": source,
            "text": text,
            "ntitle": norm(title),
            "nsource": norm(source),
            "ntext": norm(text)
        })

    if not result:
        raise RuntimeError(
            "Bilim bazasida hujjatlar topilmadi"
        )

    logging.info(
        "Hujjatlar soni: %s",
        len(result)
    )

    return result


DOCUMENTS = load_kb()


# =========================================================
# HUJJAT RAQAMINI ANIQLASH
# =========================================================

def detect_number(question):
    q = norm(question)

    if re.search(r"\b269\s*ii\b", q):
        return "269"

    m = re.search(
        r"\b(?:pq|pk)\s*(\d+)\b",
        q
    )

    if m:
        return m.group(1)

    m = re.search(
        r"\b(?:vmq|vm)\s*(\d+)\b",
        q
    )

    if m:
        return m.group(1)

    m = re.search(
        r"\b(\d{1,5})\s*(?:sonli|son|qaror|qonun)\b",
        q
    )

    if m:
        return m.group(1)

    m = re.search(
        r"\b(119|269)\b",
        q
    )

    if m:
        return m.group(1)

    return None


# =========================================================
# BILIM BAZASIDAN QIDIRISH
# =========================================================

STOP = {
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
    "haqida",
    "boyicha",
    "bo",
    "mi"
}


def search_kb(question, limit=6):
    q = norm(question)
    number = detect_number(question)

    words = [
        x for x in q.split()
        if len(x) >= 2 and x not in STOP
    ]

    results = []

    for doc in DOCUMENTS:

        score = 0

        if number:
            if number in doc["ntitle"]:
                score += 100

            if number in doc["nsource"]:
                score += 100

        for word in words:

            if word in doc["ntext"]:
                score += 3

            if word in doc["ntitle"]:
                score += 8

            if word in doc["nsource"]:
                score += 8

        if q in doc["ntext"]:
            score += 80

        if score > 0:
            results.append({
                "score": score,
                "title": doc["title"],
                "source": doc["source"],
                "text": doc["text"]
            })

    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return results[:limit]


# =========================================================
# ANIQ HUQUQIY JAVOBLAR
# =========================================================

def direct_answer(question):
    q = norm(question)

    # -----------------------------------------------------
    # 119-SON QAROR
    # -----------------------------------------------------

    if (
        "119" in q
        and any(
            word in q
            for word in [
                "qaror",
                "vmq",
                "sonli",
                "son",
                "qachon",
                "nomi",
                "toliq",
                "qabul"
            ]
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
            "Mahkamasining 2021-yil 3-martdagi "
            "119-son qarori."
        )

    # -----------------------------------------------------
    # 269-II-SON QONUN
    # -----------------------------------------------------

    if (
        "269" in q
        and any(
            word in q
            for word in [
                "qachon",
                "qabul",
                "sana"
            ]
        )
    ):
        return (
            "269-II-son Qonun
