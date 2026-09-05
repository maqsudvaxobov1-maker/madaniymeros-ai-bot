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
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
WEBHOOK_PATH = "/telegram/webhook"
WEBHOOK_URL = RENDER_EXTERNAL_URL + WEBHOOK_PATH
MAX_MESSAGE_LENGTH = 3900

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY topilmadi")


# ------------------------------------------------------------
# BILIM BAZASI: fayl nomini avtomatik topish
# ------------------------------------------------------------

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
        f
        for f in os.listdir(BASE_DIR)
        if f.lower().endswith(".json")
        and "knowledge" in f.lower()
    )

    if json_files:
        path = os.path.join(BASE_DIR, json_files[0])

        logging.info(
            "Bilim bazasi avtomatik topildi: %s",
            json_files[0]
        )

        return path

    raise RuntimeError(
        "Bilim bazasi JSON fayli topilmadi"
    )


KB_FILE = find_kb()


# ------------------------------------------------------------
# NORMALIZATSIYA
# ------------------------------------------------------------

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

    text = text.replace("ʻ", "")
    text = text.replace("ʼ", "")
    text = text.replace("’", "")
    text = text.replace("‘", "")
    text = text.replace("`", "")
    text = text.replace("'", "")

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text
    )

    return re.sub(
        r"\s+",
       
