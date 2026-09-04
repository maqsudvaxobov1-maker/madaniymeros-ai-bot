import os
import re
import json
import logging
import threading
import urllib.request
from urllib.error import HTTPError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

BASE = os.path.dirname(os.path.abspath(__file__))
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6").strip()
PORT = int(os.getenv("PORT", "10000"))
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
WEBHOOK_PATH = "/telegram/webhook"
WEBHOOK_URL = RENDER_URL + WEBHOOK_PATH

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY topilmadi")

KB_NAMES = [
    "knowledge_base_full_4.json",
    "knowledge_base_4.json",
    "knowledge_base.json",
    "knowledge_base_full.json",
    "knowledge_base_full_old.json",
]


def find_kb():
    for name in KB_NAMES:
        path = os.path.join(BASE, name)
        if os.path.isfile(path):
            return path

    for name in os.listdir(BASE):
        if name.lower().endswith(".json") and "knowledge" in name.lower():
            return os.path.join(BASE, name)

    raise RuntimeError("Bilim bazasi JSON fayli topilmadi")


KB_FILE = find_kb()


def norm(text):
    text = str(text or "").lower()

    table = str.maketrans({
        "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"yo",
        "ж":"j","з":"z","и":"i","й":"y","к":"k","қ":"q","л":"l",
        "м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t",
        "у":"u","ў":"o","ф":"f","х":"x","ҳ":"h","ц":"s","ч":"ch",
        "ш":"sh","ъ":"","ь":"","э":"e","ю":"yu","я":"ya"
    })

    text = text.translate(table)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load_kb():
    with open(KB_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        raw = data.get("documents", [])
    elif isinstance(data, list):
        raw = data
    else:
        raw = []

    docs = []

    for item in raw:
        if not isinstance(item, dict):
            continue

        title = str(item.get("title", ""))
        source = str(item.get("source_file", ""))
        text = str(item.get("text", item.get("content", "")))

        if text.strip():
            docs.append({
                "title": title,
                "source": source,
                "text": text,
                "ntitle": norm(title),
                "nsource": norm(source),
                "ntext": norm(text)
            })

    if not docs:
        raise RuntimeError("Bilim bazasida hujjatlar topilmadi")

    logging.info("KB: %s | hujjatlar: %s", KB_FILE, len(docs))
    return docs


DOCUMENTS = load_kb()


def detect_number(question):
    q = norm(question)

    if re.search(r"\b269\s*ii\b", q):
        return "269"

    m = re.search(r"\b(?:pq|pk)\s*(\d+)\b", q)
    if m:
        return m.group(1)

    m = re.search(r"\b(?:vmq|vm)\s*(\d+)\b", q)
    if m:
        return m.group(1)

    m = re.search(
        r"\b(\d{1,5})\s*(?:sonli|son|qaror|qonun)\b",
        q
    )

    if m:
        return m.group(1)

    m = re.search(r"\b(119|269)\b", q)

    if m:
        return m.group(1)

    return None


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
        w for w in q.split()
        if len(w) > 1 and w not in STOP
    ]

    found = []

    for doc in DOCUMENTS:
        score = 0

        if number:
            if number in doc["ntitle"]:
                score += 100

            if number in doc["nsource"]:
                score += 100

        if q and q in doc["ntext"]:
            score += 80

        for word in words:
            if word in doc["ntext"]:
                score += 3

            if word in doc["ntitle"]:
                score += 6

            if word in doc["nsource"]:
                score += 6

        if score:
            found.append((score, doc))

    found.sort(
        key=lambda x: x[0],
        reverse=True
    )

    return [
        item[1]
        for item in found[:limit]
    ]


def direct_answer(question):
    q = norm(question)

    # 119-son qaror
    if (
        "119" in q
        and any(
            x in q
            for x in [
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
            "To'liq nomi:\n"
            "\"Moddiy madaniy meros obyektlari va "
            "YuNESKOning Umumjahon merosi ro'yxatiga "
            "kiritilgan hududlar muhofazasini kuchaytirish "
            "chora-tadbirlari to'g'risida\".\n\n"
            "Manba: O'zbekiston Respublikasi Vazirlar "
            "Mahkamasining 2021-yil 3-martdagi "
            "119-son qarori."
        )

    # 269-II-son Qonun
    if (
        "269" in q
        and any(
            x in q
            for x in [
                "qachon",
                "qabul",
                "sana"
            ]
        )
    ):
        return (
            "269-II-son Qonun 2001-yil 30-avgustda "
            "qabul qilingan.\n\n"
            "Qonun nomi:\n"
            "\"Madaniy meros obyektlarini muhofaza "
            "qilish va ulardan foydalanish "
            "to'g'risida\"gi Qonun.\n\n"
            "Manba: 269-II-son Qonun, 30.08.2001."
        )

    return None


def ask_openai(question, context):
    system = (
        "Siz Madaniy Meros AI yordamchisisiz. "
        "Faqat berilgan bilim bazasiga tayangan holda "
        "javob bering. Huquqiy norma, hujjat raqami, "
        "sana yoki bandni o'ylab topmang. "
        "Ma'lumot yetarli bo'lmasa, buni ochiq ayting. "
        "Javobni o'zbek tilida aniq va amaliy yozing."
    )

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": system
            },
            {
                "role": "user",
                "content": (
                    "Savol:\n"
                    + question
                    + "\n\nManbalar:\n"
                    + context[:18000]
                )
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
            "Authorization": "Bearer " + OPENAI_API_KEY
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=90
        ) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

        return (
            result["choices"][0]
            ["message"]["content"]
            .strip()
        )

    except HTTPError as error:
        logging.error(
            "OpenAI HTTP %s",
            error.code
        )
        return "OpenAI API xatosi: " + str(error.code)

    except Exception:
        logging.exception("OpenAI xatosi")
        return "Javobni shakllantirishda texnik xatolik yuz berdi."


def answer_question(question):
    direct = direct_answer(question)

    if direct:
        return direct

    results = search_kb(question)

    if not results:
        return (
            "Taqdim etilgan bilim bazasida bu savolga "
            "yetarli aniq ma'lumot topilmadi."
        )

    context = "\n\n---\n\n".join(
        (
            "HUJJAT: "
            + doc["title"]
            + "\nMANBA: "
            + doc["source"]
            + "\nMATN:\n"
            + doc["text"]
        )
        for doc in results
    )

    return ask_openai(
        question,
        context
    )


def telegram(method, payload):
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
            return json.loads(
                response.read().decode("utf-8")
            )

    except Exception:
        logging.exception(
            "Telegram API xatosi"
        )
        return {"ok": False}


def setup_webhook():
    if not RENDER_URL:
        logging.warning(
            "RENDER_EXTERNAL_URL topilmadi"
        )
        return

    result = telegram(
        "setWebhook",
        {
            "url": WEBHOOK_URL,
            "drop_pending_updates": False
        }
    )

    logging.info(
        "Webhook: %s",
        result
    )


def send_message(chat_id, text):
    limit = 3900

    while len(text) > limit:
        cut = text.rfind(
            "\n",
            0,
            limit
        )

        if cut < 500:
            cut = text.rfind(
                " ",
                0,
                limit
            )

        if cut < 500:
            cut = limit

        telegram(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text[:cut].strip()
            }
        )

        text = text[cut:].strip()

    if text:
        telegram(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text
            }
        )


def process_update(update):
    message = update.get("message")

    if not isinstance(
        message,
        dict
    ):
        return

    chat_id = message.get(
        "chat",
        {}
    ).get("id")

    text = str(
        message.get(
            "text",
            ""
        )
    ).strip()

    if not chat_id or not text:
        return

    logging.info(
        "Savol: %s",
        text[:500]
    )

    if text.lower().startswith("/start"):
        send_message(
            chat_id,
            "Assalomu alaykum!\n\n"
            "Men Madaniy Meros AI botiman.\n"
            "Savolingizni yozing."
        )
        return

    if text.lower().startswith("/help"):
        send_message(
            chat_id,
            "Masalan:\n"
            "269-II-son Qonun qachon qabul qilingan?\n"
            "119-sonli qarorning to'liq nomi nima?\n"
            "Tarixiy-madaniy ekspertiza tartibi qanday?"
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
            "Savol xatosi"
        )

        send_message(
            chat_id,
            "Kechirasiz, texnik xatolik yuz berdi."
        )


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

        if self.path in (
            "/",
            "/health"
        ):
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

            raw = self.rfile.read(
                length
            )

            update = json.loads(
                raw.decode("utf-8")
            )

            self.send_response(200)

            self.send_header(
                "Content-Type",
                "text/plain"
            )

            self.end_headers()

            self.wfile.write(
                b"OK"
            )

            threading.Thread(
                target=process_update,
                args=(update,),
                daemon=True
            ).start()

        except Exception:
            logging.exception(
                "Webhook xatosi"
            )

            try:
                self.send_response(200)
                self.end_headers()
            except Exception:
                pass


def main():
    logging.info(
        "MADANIY MEROS AI ISHLAYAPTI"
    )

    logging.info(
        "KB: %s",
        KB_FILE
    )

    logging.info(
        "Hujjatlar: %s",
        len(DOCUMENTS)
    )

    setup_webhook()

    server = ThreadingHTTPServer(
        (
            "0.0.0.0",
            PORT
        ),
        Handler
    )

    server.serve_forever()


if __name__ == "__main__":
    main()
