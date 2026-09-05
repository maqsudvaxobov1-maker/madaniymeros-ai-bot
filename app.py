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
        " ",
        text
    ).strip()


# ------------------------------------------------------------
# BILIM BAZASI — SECTION-AWARE
# ------------------------------------------------------------

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

    for item in raw_docs or []:

        if not isinstance(item, dict):
            continue

        title = str(
            item.get("title", "")
        ).strip()

        source = str(
            item.get("source_file", "")
        ).strip()

        number = str(
            item.get("document_number", "")
        ).strip()

        date = str(
            item.get("date", "")
        ).strip()

        aliases = item.get(
            "aliases",
            []
        ) or []

        search_aliases = item.get(
            "search_aliases",
            []
        ) or []

        sections = item.get(
            "sections",
            []
        ) or []

        full_text = str(
            item.get(
                "text",
                item.get("content", "")
            )
        ).strip()

        sec_list = []

        for sec in sections:

            if not isinstance(sec, dict):
                continue

            text = str(
                sec.get("text", "")
            ).strip()

            label = str(
                sec.get("label", "")
            ).strip()

            if not text and not label:
                continue

            sec_list.append({
                "id": sec.get(
                    "section_id"
                ),
                "label": label,
                "text": text or label,
                "nlabel": norm(label),
                "ntext": norm(
                    text or label
                )
            })

        if not sec_list and full_text:

            sec_list = [{
                "id": 0,
                "label": title,
                "text": full_text,
                "nlabel": norm(title),
                "ntext": norm(full_text)
            }]

        docs.append({
            "title": title,
            "source_file": source,
            "document_number": number,
            "date": date,
            "aliases": [
                str(x)
                for x in aliases
            ],
            "search_aliases": [
                str(x)
                for x in search_aliases
            ],
            "ntitle": norm(title),
            "nsource": norm(source),
            "nnumber": norm(number),
            "naliases": norm(
                " ".join(
                    map(
                        str,
                        aliases + search_aliases
                    )
                )
            ),
            "sections": sec_list
        })

    if not docs:
        raise RuntimeError(
            "Bilim bazasida hujjatlar topilmadi"
        )

    logging.info(
        "Bilim bazasi yuklandi: %s ta hujjat",
        len(docs)
    )

    logging.info(
        "Jami bo'limlar: %s",
        sum(
            len(x["sections"])
            for x in docs
        )
    )

    return docs


DOCUMENTS = load_kb()


# ------------------------------------------------------------
# QIDIRUV YORDAMCHILARI
# ------------------------------------------------------------

def detect_number(question):

    q = norm(question)

    if re.search(
        r"\b269\s*ii\b",
        q
    ):
        return "269-ii"

    m = re.search(
        r"\b(?:pq|pk)\s*-?\s*(\d+)\b",
        q
    )

    if m:
        return m.group(1)

    m = re.search(
        r"\b(?:vmq|vm)\s*-?\s*(\d+)\b",
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
        r"\b(119|269|265|295|649|5150|177)\b",
        q
    )

    return m.group(1) if m else None


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
    "mumkin",
    "edi",
    "ekan",
    "boladi",
    "bo‘ladi"
}


def keywords(question):

    words = re.findall(
        r"[a-z0-9]+",
        norm(question)
    )

    return list(
        dict.fromkeys(
            w
            for w in words
            if len(w) >= 2
            and w not in STOP_WORDS
        )
    )


TOPIC_ALIASES = {

    "ekspertiza": [
        "ekspertiza",
        "ekspert",
        "tarixiy madaniy",
        "xulosa",
        "kengash",
        "metodika"
    ],

    "qurilish": [
        "qurilish",
        "qurilish montaj",
        "shaharsozlik",
        "rekonstruksiya",
        "yer foydalanish"
    ],

    "ruxsat": [
        "ruxsat",
        "ruxsatnoma",
        "kelishuv",
        "kelishish",
        "tasdiq",
        "ijozat"
    ],

    "muhofaza": [
        "muhofaza",
        "qo‘riqlanadigan",
        "tegrasi",
        "himoya",
        "saqlash",
        "asrash"
    ],

    "restavratsiya": [
        "restavratsiya",
        "ta’mirlash",
        "konservatsiya",
        "asrashga doir ishlar"
    ],

    "xizmat": [
        "davlat xizmati",
        "xizmat",
        "to‘lov",
        "yig‘im",
        "davlat boji",
        "haq"
    ],

    "arxeologiya": [
        "arxeolog",
        "arxeologiya",
        "qazishma",
        "ilmiy tadqiqot",
        "ruxsatnoma"
    ],

    "kadastr": [
        "kadastr",
        "ro‘yxat",
        "milliy ro‘yxat",
        "toifa",
        "hisob"
    ]
}


def detect_topics(question):

    q = norm(question)

    topics = []

    for topic, aliases in TOPIC_ALIASES.items():

        if any(
            norm(a) in q
            for a in aliases
        ):
            topics.append(topic)

    return topics


def doc_number_match(doc, number):

    if not number:
        return False

    n = norm(number)

    hay = " ".join([
        doc["ntitle"],
        doc["nsource"],
        doc["nnumber"],
        doc["naliases"]
    ])

    if n == "269-ii":

        return (
            "269 ii" in hay
            or "269 ii son" in hay
        )

    return bool(
        re.search(
            r"\b" + re.escape(n) + r"\b",
            hay
        )
    )


def topic_doc_bonus(doc, topics):

    bonus = 0

    hay = " ".join([
        doc["ntitle"],
        doc["nsource"],
        doc["naliases"]
    ])

    for topic in topics:

        if (
            topic == "ekspertiza"
            and (
                "269 son" in hay
                or
                "tarixiy madaniy ekspertiza" in hay
            )
        ):
            bonus += 80

        elif (
            topic in (
                "qurilish",
                "ruxsat",
                "muhofaza",
                "restavratsiya"
            )
            and "265 son" in hay
        ):
            bonus += 55

        elif (
            topic == "xizmat"
            and (
                "295 son" in hay
                or
                "119 son" in hay
            )
        ):
            bonus += 55

        elif (
            topic == "arxeologiya"
            and (
                "269 ii" in hay
                or
                "5150" in hay
                or
                "295 son" in hay
            )
        ):
            bonus += 35

    return bonus


# ------------------------------------------------------------
# ASOSIY QIDIRUV ALGORITMI
# ------------------------------------------------------------

def search_kb(question, limit=14):

    q = norm(question)

    keys = keywords(question)

    number = detect_number(question)

    topics = detect_topics(question)

    scored = []

    for doc in DOCUMENTS:

        base = topic_doc_bonus(
            doc,
            topics
        )

        if number and doc_number_match(
            doc,
            number
        ):
            base += 220

        for sec in doc["sections"]:

            text = sec["ntext"]

            label = sec["nlabel"]

            score = base

            # Butun savol iborasi.
            if (
                len(q) >= 12
                and q in text
            ):
                score += 160

            # Savol kalit so'zlari.
            matched = 0

            for key in keys:

                if key in text:
                    score += 5
                    matched += 1

                if key in label:
                    score += 10
                    matched += 1

            # Mavzu terminlari.
            for topic in topics:

                for alias in TOPIC_ALIASES[topic]:

                    na = norm(alias)

                    if (
                        na
                        and na in text
                    ):
                        score += 22
                        break

            # Aniq hujjat raqami.
            if (
                number
                and doc_number_match(
                    doc,
                    number
                )
            ):
                score += 100

            # Agar umuman moslik bo'lmasa.
            if (
                matched == 0
                and base == 0
            ):
                continue

            # Juda kichik bandlarni pasaytirish.
            if len(text) < 80:
                score -= 10

            scored.append({
                "score": score,
                "title": doc["title"],
                "source": doc["source_file"],
                "document_number": doc[
                    "document_number"
                ],
                "date": doc["date"],
                "section_id": sec["id"],
                "label": sec["label"],
                "text": sec["text"]
            })

    scored.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    # Takroriy bandlarni olib tashlash.
    unique = []

    seen = set()

    for item in scored:

        key = (
            item["source"],
            item["section_id"],
            norm(item["text"])[:300]
        )

        if key in seen:
            continue

        seen.add(key)

        unique.append(item)

    # Bir nechta bandni qaytarish.
    return unique[:limit]


# ------------------------------------------------------------
# KONTEXT YIG'ISH
# ------------------------------------------------------------

def build_context(
    question,
    results,
    max_chars=30000
):

    if not results:
        return ""

    blocks = []

    used = 0

    for i, x in enumerate(
        results,
        1
    ):

        block = (
            f"[{i}] HUJJAT: {x['title']}\n"
            f"SANA: {x['date']}\n"
            f"MANBA FAYL: {x['source']}\n"
            f"BAND/BO'LIM: {x['label']}\n"
            f"MATN:\n{x['text']}"
        )

        if (
            used + len(block)
            > max_chars
        ):
            continue

        blocks.append(block)

        used += len(block)

    return (
        "\n\n====================\n\n"
        .join(blocks)
    )


# ------------------------------------------------------------
# ANIQ JAVOBLAR
# ------------------------------------------------------------

def direct_answer(question):

    q = norm(question)

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
            "269-II-son Qonun "
            "2001-yil 30-avgustda "
            "qabul qilingan.\n\n"

            "Qonun nomi:\n"

            "“Madaniy meros obyektlarini "
            "muhofaza qilish va ulardan "
            "foydalanish to‘g‘risida”gi "
            "Qonun.\n\n"

            "Manba: 269-II-son Qonun, "
            "30.08.2001."
        )

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
                "toliq"
            ]
        )
    ):

        return (
            "119-son Vazirlar Mahkamasi "
            "qarori 2021-yil 3-martda "
            "qabul qilingan.\n\n"

            "To‘liq nomi:\n"

            "“Moddiy madaniy meros "
            "obyektlari va YuNESKOning "
            "Umumjahon merosi ro‘yxatiga "
            "kiritilgan hududlar "
            "muhofazasini kuchaytirish "
            "chora-tadbirlari "
            "to‘g‘risida”.\n\n"

            "Manba: O‘zbekiston "
            "Respublikasi Vazirlar "
            "Mahkamasining 2021-yil "
            "3-martdagi 119-son qarori."
        )

    return None


# ------------------------------------------------------------
# OPENAI
# ------------------------------------------------------------

def ask_openai(
    question,
    context
):

    system = (
        "Siz Madaniy Meros AI "
        "yordamchisisiz. "

        "Faqat berilgan bilim "
        "bazasidagi amaldagi va "
        "manbada mavjud ma’lumotlarga "
        "tayangan holda javob bering. "

        "Savol bir nechta masalani "
        "so‘rasa, har bir qismini "
        "alohida yoritib, tegishli "
        "barcha bandlarni birlashtiring. "

        "Hujjat raqami, sana, band, "
        "kichik band, ilova va "
        "vakolatli organni o‘ylab "
        "topmang. "

        "Manbada norma o‘z kuchini "
        "yo‘qotgan deb ko‘rsatilgan "
        "bo‘lsa, uni amaldagi talab "
        "sifatida qo‘llamang. "

        "Agar turli hujjatlar "
        "bir-birini to‘ldirsa, "
        "ularni alohida ko‘rsatib "
        "birlashtiring. "

        "Javobni quyidagi tartibda "
        "tuzing: "

        "1) qisqa xulosa; "
        "2) talablar/tartib; "
        "3) zarur hujjatlar yoki "
        "ruxsatlar; "
        "4) muddat/to‘lov bo‘lsa; "
        "5) aniq manbalar. "

        "Savolga javob beruvchi "
        "bandlar kontekstda mavjud "
        "bo‘lsa, ularni tashlab "
        "ketmang. "

        "Faqat bilim bazasida "
        "javob bo‘lmasa, bu haqda "
        "ochiq ayting. "

        "Javobni o‘zbek tilida, "
        "aniq, huquqiy jihatdan "
        "ehtiyotkor va amaliy "
        "tarzda bering."
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
                    +
                    "\n\nBilim bazasi:\n"
                    + context
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
            f"OpenAI API xatosi: "
            f"{e.code}"
        )

    except Exception:

        logging.exception(
            "OpenAI xatosi"
        )

        return (
            "Javobni shakllantirishda "
            "texnik xatolik yuz berdi."
        )


# ------------------------------------------------------------
# SAVOLGA JAVOB
# ------------------------------------------------------------

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
            "Taqdim etilgan bilim "
            "bazasida bu savolga "
            "yetarli aniq ma’lumot "
            "topilmadi."
        )

    context = build_context(
        question,
        results,
        max_chars=30000
    )

    return ask_openai(
        question,
        context
    )


# ------------------------------------------------------------
# TELEGRAM API
# ------------------------------------------------------------

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


# ------------------------------------------------------------
# WEBHOOK
# ------------------------------------------------------------

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

            "drop_pending_updates":
                False
        }
    )

    logging.info(
        "Webhook: %s",
        result
    )


# ------------------------------------------------------------
# UZUN JAVOBNI BO'LISH
# ------------------------------------------------------------

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

    for part in split_message(
        text
    ):

        telegram_api(

            "sendMessage",

            {
                "chat_id": chat_id,
                "text": part
            }
        )


# ------------------------------------------------------------
# UPDATE QAYTA ISHLASH
# ------------------------------------------------------------

def process_update(update):

    message = update.get(
        "message"
    )

    if not isinstance(
        message,
        dict
    ):
        return

    chat_id = (
        message
        .get("chat", {})
        .get("id")
    )

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

    # START
    if text.lower().startswith(
        "/start"
    ):

        send_message(

            chat_id,

            "Assalomu alaykum!\n\n"
            "Men Madaniy Meros AI "
            "botiman.\n"
            "Savolingizni yozing."
        )

        return

    # HELP
    if text.lower().startswith(
        "/help"
    ):

        send_message(

            chat_id,

            "Masalan:\n"

            "• 269-II-son Qonun "
            "qachon qabul qilingan?\n"

            "• 119-sonli qarorning "
            "to‘liq nomi nima?\n"

            "• Tarixiy-madaniy "
            "ekspertiza tartibi "
            "qanday?\n"

            "• Madaniy meros "
            "obyektida qurilish "
            "mumkinmi?"
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

            "Kechirasiz, texnik "
            "xatolik yuz berdi."
        )


# ------------------------------------------------------------
# WEBHOOK SERVER
# ------------------------------------------------------------

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

                "Madaniy Meros AI "
                "ishlayapti."

                if self.path == "/"

                else "OK"

            ).encode(
                "utf-8"
            )

            self.send_response(
                200
            )

            self.send_header(
                "Content-Type",
                "text/plain; "
                "charset=utf-8"
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
                raw.decode(
                    "utf-8"
                )
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


# ------------------------------------------------------------
# START
# ------------------------------------------------------------

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
