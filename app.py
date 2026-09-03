import os
import json
import time
import threading
import urllib.request
import urllib.error
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
PORT = int(os.getenv("PORT", "10000"))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6")

TELEGRAM_TIMEOUT = 40
OPENAI_TIMEOUT = 90
KNOWLEDGE_FILE = os.path.join(os.path.dirname(__file__), "knowledge_base.json")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY topilmadi")


def load_knowledge():
    try:
        with open(KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        docs = data.get("documents", [])

        print(
            "Bilim bazasi yuklandi:",
            len(docs),
            "ta hujjat",
            flush=True
        )

        return docs

    except Exception as e:
        print(
            "Bilim bazasini yuklashda xato:",
            e,
            flush=True
        )

        return []


DOCUMENTS = load_knowledge()


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
            {
                "drop_pending_updates": False
            }
        )

        print(
            "Webhook holati:",
            result,
            flush=True
        )

    except Exception as e:

        print(
            "Webhook o'chirishda xato:",
            e,
            flush=True
        )


def clean_answer(text):

    if not text:

        return (
            "Javob tayyorlashda "
            "xatolik yuz berdi."
        )

    text = str(text)

    text = text.replace("**", "")
    text = text.replace("__", "")
    text = text.replace("```", "")
    text = text.replace("`", "")

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text
    )

    return text.strip()


def send_message(chat_id, text):

    text = clean_answer(text)

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


def normalize(text):

    text = str(text).lower()

    text = re.sub(
        r"[^a-zа-яёўқғҳқʼʻ'0-9\s-]",
        " ",
        text
    )

    return re.sub(
        r"\s+",
        " ",
        text
    ).strip()


def document_number(doc):

    title = str(
        doc.get("title", "")
    )

    source = str(
        doc.get("source_file", "")
    )

    match = re.search(
        r"(?<!\d)(\d{2,5})-?(?:ii|son|с[oо]н)",
        title.lower()
    )

    if match:

        return match.group(1)

    match = re.search(
        r"(\d{2,5})",
        source
    )

    if match:

        return match.group(1)

    match = re.search(
        r"(?<!\d)(\d{2,5})(?!\d)",
        title
    )

    if match:

        return match.group(1)

    return ""


def get_document_by_number(number):

    number = str(number).strip()

    for doc in DOCUMENTS:

        if document_number(doc) == number:

            return doc

    return None


def requested_document_number(question):

    q = normalize(question)

    patterns = [

        r"\b(?:vmq|vazirlar mahkamasi)\s*[- ]?\s*(\d{2,5})\b",

        r"\b(\d{2,5})\s*-\s*son\b",

        r"\b(\d{2,5})\s*sonli\b",

        r"\b(\d{2,5})\s*son\b",

        r"\b(?:pq|pf)\s*[- ]?\s*(\d{2,5})\b",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            q
        )

        if match:

            return match.group(1)

    return None


def split_chunks(text):

    paragraphs = [
        p.strip()
        for p in re.split(
            r"\n{2,}|\n",
            str(text)
        )
        if len(p.strip()) >= 50
    ]

    chunks = []

    for paragraph in paragraphs:

        if len(paragraph) <= 1800:

            chunks.append(paragraph)

        else:

           
