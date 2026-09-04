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
        word in q
        for word in words
    )


def search_kb(
    question,
    limit=6
):

    q = norm(question)

    keys = keywords(question)

    number = detect_number(question)

    found = []

    expertise = is_expertise_question(q)

    for doc in DOCUMENTS:

        doc_bonus = 0

        title = doc["ntitle"]
        source = doc["nsource"]

        if number:

            if number in title:
                doc_bonus += 100

            if number in source:
                doc_bonus += 100

        # 269-son Nizomni ustuvor qilish
        if expertise:

            if "269" in title:
                doc_bonus += 300

            if "269" in source:
                doc_bonus += 300

            if "ekspertiza" in doc["ntext"]:
                doc_bonus += 100

        for chunk in chunks(
            doc["text"]
        ):

            nchunk = norm(chunk)

            score = doc_bonus

            if (
                len(q) >= 8
                and q in nchunk
            ):
                score += 80

            for key in keys:

                if key in nchunk:
                    score += 3

                if key in title:
                    score += 6

                if key in source:
                    score += 6

            important = [
                "ekspert",
                "ekspertiza",
                "restavratsiya",
                "qurilish",
                "buzish",
                "ruxsat",
                "muhofaza",
                "madaniy",
                "meros",
                "yunesko",
                "xizmat",
                "tolov",
                "kadastr"
            ]

            for word in important:

                if (
                    word in q
                    and word in nchunk
                ):
                    score += 8

            if score > 0:

                found.append({
                    "score": score,
                    "title": doc["title"],
                    "source": doc["source_file"],
                    "text": chunk
                })

    found.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return found[:limit]


# ============================================================
# ANIQ JAVOBLAR
# ============================================================

def direct_answer(question):

    q = norm(question)

    # --------------------------------------------------------
    # TARIXIY-MADANIY EKSPERTIZA
    # --------------------------------------------------------

    if (
        "ekspertiza" in q
        and (
            "tarixiy" in q
            or "madaniy" in q
            or "muddat" in q
            or "xulosa" in q
        )
    ):

        if (
            "muddat" in q
            and (
                "xulosa" in q
                or "tasdiq" in q
            )
        ):

            return (
                "Tarixiy-madaniy ekspertiza o'tkazish "
                "muddati 30 kundan oshmasligi kerak. "
                "Muddati ekspertiza yo'nalishi, ishning "
                "murakkabligi va hajmiga qarab belgilanadi.\n\n"

                "Ekspertiza xulosasi loyihasi "
                "Ilmiy-ekspert kengashi majlisida "
                "ko'rib chiqiladi. Kengash tomonidan "
                "ma'qullangan xulosa belgilangan "
                "tartibda rasmiylashtiriladi. "
                "Bayonnoma va xulosa Agentlikka yuboriladi.\n\n"

                "Manba: Vazirlar Mahkamasining "
                "2002-yil 29-iyuldagi 269-son qarori "
                "bilan tasdiqlangan Nizom, 15–19-bandlar."
            )

        if "muddat" in q:

            return (
                "Tarixiy-madaniy ekspertiza o'tkazish "
                "muddati 30 kundan oshmasligi kerak. "
                "Muddati ekspertiza yo'nalishi, ishning "
                "murakkabligi va hajmiga qarab belgilanadi.\n\n"

                "Manba: Vazirlar Mahkamasining "
                "2002-yil 29-iyuldagi 269-son qarori "
                "bilan tasdiqlangan Nizom, 18-band."
            )

        if (
            "xulosa" in q
            or "tasdiq" in q
        ):

            return (
                "Tarixiy-madaniy ekspertiza xulosasi "
                "loyihasi Ilmiy-ekspert kengashi "
                "majlisida ko'rib chiqiladi. "
                "Kengash tomonidan ma'qullangan xulosa "
                "belgilangan tartibda rasmiylashtiriladi. "
                "Bayonnoma va xulosa Agentlikka yuboriladi.\n\n"

                "Manba: Vazirlar Mahkamasining "
                "2002-yil 29-iyuldagi 269-son qarori "
                "bilan tasdiqlangan Nizom, 15–17-bandlar."
            )

        if "tartib" in q:

            return (
                "Tarixiy-madaniy ekspertiza materiallari "
                "Ilmiy-ekspert kengashi kotibiga kiritiladi. "
                "Ekspertiza tegishli yo'nalish bo'yicha "
                "o'tkaziladi. Ekspertiza muddati 30 kundan "
                "oshmasligi kerak.\n\n"

                "Natijasi bo'yicha xulosa loyihasi "
                "Kengash majlisida ko'rib chiqiladi va "
                "ma'qullangan xulosa belgilangan "
                "tartibda rasmiylashtiriladi.\n\n"

                "Manba: Vazirlar Mahkamasining "
                "2002-yil 29-iyuldagi 269-son qarori "
                "bilan tasdiqlangan Nizom."
            )

    # --------------------------------------------------------
    # 269-II QONUN
    # --------------------------------------------------------

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
            "269-II-son Qonun "
            "2001-yil 30-avgustda qabul qilingan.\n\n"

            "Qonun nomi:\n"
            "“Madaniy meros obyektlarini muhofaza "
            "qilish va ulardan foydalanish "
            "to‘g‘risida”gi Qonun.\n\n"

            "Manba: 269-II-son Qonun, 30.08.2001."
        )

    # --------------------------------------------------------
    # 119-SON QAROR
    # --------------------------------------------------------

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
                "toliq"
            ]
        )
    ):

        return (
            "119-son Vazirlar Mahkamasi qarori "
            "2021-yil 3-martda qabul qilingan.\n\n"

            "To‘liq nomi:\n"
            "“Moddiy madaniy meros obyektlari va "
            "YuNESKOning Umumjahon merosi ro‘yxatiga "
            "kiritilgan hududlar muhofazasini "
            "kuchaytirish chora-tadbirlari "
            "to‘g‘risida”.\n\n"

            "Manba: O‘zbekiston Respublikasi "
            "Vazirlar Mahkamasining 2021-yil "
            "3-martdagi 119-son qarori."
        )

    return None


# ============================================================
# OPENAI
# ============================================================

def ask_openai(
    question,
    context
):

    system = (
        "Siz Madaniy Meros AI yordamchisisiz. "
        "O‘zbekiston madaniy merosi bo‘yicha savollarga "
        "faqat berilgan bilim bazasiga tayangan holda javob bering. "

        "Huquqiy norma, hujjat raqami, sana yoki bandni "
        "o‘ylab topmang. "

        "Bilim bazasida aniq javob bo‘lmasa, "
        "“Taqdim etilgan bilim bazasida bu savolga "
        "yetarli aniq ma’lumot topilmadi” deb yozing. "

        "Javobni o‘zbek tilida, aniq va amaliy tarzda bering."
    )

    payload = {
        "model": OPENAI_MODEL,
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
                    + "\n\nBilim bazasi:\n"
                    + context[:18000]
                )
            }
        ]
    }

    data = json.dumps(
        payload,
        ensure_ascii=False
    ).encode("utf-8")

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization":
                "Bearer " + OPENAI_API_KEY
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
            result["choices"][0]["message"]["content"]
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
            body[:1000]
        )

        return (
            f"OpenAI API xatosi: {e.code}"
        )

    except Exception:

        logging.exception(
            "OpenAI xatosi"
        )

        return (
            "Javobni shakllantirishda "
            "texnik xatolik yuz berdi."
        )


# ============================================================
# SAVOLGA JAVOB
# ============================================================

def answer_question(question):

    direct = direct_answer(
        question
    )

    if direct:
        return direct

    results = search_kb(
        question
    )

    if not results:

        return (
            "Taqdim etilgan bilim bazasida "
            "bu savolga yetarli aniq "
            "ma’lumot topilmadi."
        )

    context = "\n\n---\n\n".join(
        "HUJJAT: "
        + x["title"]
        + "\nMANBA: "
        + x["source"]
        + "\nMATN:\n"
        + x["text"]
        for x in results
    )

    return ask_openai(
        question,
        context
    )


# ============================================================
# TELEGRAM API
# ============================================================

def telegram_api(
    method,
    payload
):

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

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type":
                "application/json"
        },
        method="POST"
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

    except Exception:

        logging.exception(
            "Telegram API xatosi"
        )

        return {
            "ok": False
        }


def setup_webhook():

    if not RENDER_EXTERNAL_URL:

        logging.warning(
            "RENDER_EXTERNAL_URL topilmadi"
        )

        return

    result = telegram_api(
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


# ============================================================
# TELEGRAM XABARLARI
# ============================================================

def split_message(text):

    if len(text) <= MAX_MESSAGE_LENGTH:
        return [text]

    parts = []

    while len(text) > MAX_MESSAGE_LENGTH:

        cut = text.rfind(
            "\n",
            0,
            MAX_MESSAGE_LENGTH
        )

        if cut < 500:

            cut = text.rfind(
                " ",
                0,
                MAX_MESSAGE_LENGTH
            )

        if cut < 500:
            cut = MAX_MESSAGE_LENGTH

        parts.append(
            text[:cut].strip()
        )

        text = text[cut:].strip()

    if text:
        parts.append(text)

    return parts


def send_message(
    chat_id,
    text
):

    for part in split_message(text):

        telegram_api(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": part
            }
        )


def process_update(update):

    message = update.get(
        "message"
    )

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

    if text.lower().startswith(
        "/start"
    ):

        send_message(
            chat_id,
            "Assalomu alaykum!\n\n"
            "Men Madaniy Meros AI botiman.\n"
            "Savolingizni yozing."
        )

        return

    if text.lower().startswith(
        "/help"
    ):

        send_message(
            chat_id,
            "Masalan:\n"
            "• 269-II-son Qonun qachon qabul qilingan?\n"
            "• 119-sonli qarorning to‘liq nomi nima?\n"
            "• Tarixiy-madaniy ekspertiza tartibi qanday?\n"
            "• Madaniy meros obyektida qurilish mumkinmi?"
        )

        return

    try:

        answer = answer_question(
            text
        )

        send_message(
            chat_id,
            answer
        )

    except Exception:

        logging.exception(
            "Savolni qayta ishlash xatosi"
        )

        send_message(
            chat_id,
            "Kechirasiz, texnik xatolik yuz berdi."
        )


# ============================================================
# WEBHOOK SERVER
# ============================================================

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

        if self.path in [
            "/",
            "/health"
        ]:

            body = (
                "Madaniy Meros AI ishlayapti."
                if self.path == "/"
                else "OK"
            ).encode("utf-8")

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

        if self.path != WEBHOOK_PATH:

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
                raw.decode("utf-8")
            )

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

                self.send_response(
                    200
                )

                self.end_headers()

            except Exception:
                pass


# ============================================================
# ISHGA TUSHIRISH
# ============================================================

def main():

    logging.info(
        "MADANIY MEROS AI BOSHLANDI"
    )

    logging.info(
        "Knowledge base: %s",
        KB_FILE
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
