import os
import re
import json
import logging
import threading
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini").strip()
PORT = int(os.getenv("PORT", "10000"))

RENDER_EXTERNAL_URL = os.getenv(
    "RENDER_EXTERNAL_URL", ""
).strip().rstrip("/")

WEBHOOK_PATH = "/telegram/webhook"
WEBHOOK_URL = RENDER_EXTERNAL_URL + WEBHOOK_PATH

MAX_MESSAGE_LENGTH = 3900


if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY topilmadi")


# ============================================================
# BILIM BAZASI
# ============================================================

KB_NAMES = [
    "knowledge_base_full_4.json",
    "knowledge_base_4.json",
    "knowledge_base.json",
    "knowledge_base_full.json",
    "knowledge_base_full_old.json",
]


def find_kb():
    for name in KB_NAMES:
        path = os.path.join(BASE_DIR, name)

        if os.path.isfile(path):
            logging.info("Bilim bazasi: %s", name)
            return path

    json_files = sorted(
        f for f in os.listdir(BASE_DIR)
        if f.lower().endswith(".json")
        and "knowledge" in f.lower()
    )

    if json_files:
        path = os.path.join(
            BASE_DIR,
            json_files[0]
        )

        logging.info(
            "Bilim bazasi avtomatik topildi: %s",
            json_files[0]
        )

        return path

    raise RuntimeError(
        "Bilim bazasi JSON fayli topilmadi"
    )


KB_FILE = find_kb()


# ============================================================
# NORMALIZATSIYA
# ============================================================

def norm(text):
    text = str(text or "").lower().strip()

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

    text = (
        text
        .replace("ʻ", "")
        .replace("ʼ", "")
        .replace("’", "")
        .replace("‘", "")
        .replace("`", "")
        .replace("'", "")
    )

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


# ============================================================
# BILIM BAZASINI YUKLASH
# ============================================================

def load_kb():

    with open(
        KB_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        data = json.load(f)

    if isinstance(data, dict):

        raw_docs = data.get(
            "documents",
            data.get("docs", [])
        )

    elif isinstance(data, list):

        raw_docs = data

    else:

        raw_docs = []

    docs = []

    for item in raw_docs:

        if not isinstance(item, dict):
            continue

        title = str(
            item.get("title", "")
        ).strip()

        source = str(
            item.get("source_file", "")
        ).strip()

        text = str(
            item.get(
                "text",
                item.get("content", "")
            )
        ).strip()

        if not text:
            continue

        docs.append({
            "title": title,
            "source_file": source,
            "text": text,
            "ntitle": norm(title),
            "nsource": norm(source),
            "ntext": norm(text),
        })

    if not docs:
        raise RuntimeError(
            "Bilim bazasida hujjatlar topilmadi"
        )

    logging.info(
        "Bilim bazasi yuklandi: %s ta hujjat",
        len(docs)
    )

    return docs


DOCUMENTS = load_kb()


# ============================================================
# QIDIRUV
# ============================================================

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
    "boyicha",
    "bo‘yicha",
    "siz",
    "men",
    "ning",
    "ni",
    "ga",
    "da",
    "dan",
    "mi",
    "mumkin"
}


def detect_number(question):

    q = norm(question)

    if re.search(
        r"\b269\s*ii\b",
        q
    ):
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

    return m.group(1) if m else None


def keywords(question):

    words = re.findall(
        r"[a-z0-9]+",
        norm(question)
    )

    return list(
        dict.fromkeys(
            w for w in words
            if len(w) >= 2
            and w not in STOP_WORDS
        )
    )


def chunks(
    text,
    size=4000,
    overlap=500
):

    if len(text) <= size:
        return [text]

    result = []

    start = 0

    while start < len(text):

        end = start + size

        result.append(
            text[start:end]
        )

        if end >= len(text):
            break

        start = end - overlap

    return result


def is_expertise_question(q):

    if "ekspertiza" not in q:
        return False

    words = [
        "tarixiy",
        "madaniy",
        "muddat",
        "xulosa",
        "tartib",
        "kengash"
    ]

    return any(
       
