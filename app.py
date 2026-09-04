import os
import re
import json
import threading
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.join(BASE, "knowledge_base_full_4.json")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6").strip()
PORT = int(os.getenv("PORT", "10000"))
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/telegram/webhook").strip()

if not WEBHOOK_PATH.startswith("/"):
    WEBHOOK_PATH = "/" + WEBHOOK_PATH

BHM = 440000
MAX_MSG = 3900

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY topilmadi")


def norm(s):
    s = str(s or "").lower()

    table = str.maketrans({
        "а": "a", "б": "b", "в": "v", "г": "g",
        "ғ": "g", "д": "d", "е": "e", "ё": "yo",
        "ж": "j", "з": "z", "и": "i", "й": "y",
        "к": "k", "қ": "q", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r",
        "с": "s", "т": "t", "у": "u", "ў": "o",
        "ф": "f", "х": "x", "ҳ": "h", "ц": "s",
        "ч": "ch", "ш": "sh", "ъ": "", "ы": "i",
        "ь": "", "э": "e", "ю": "yu", "я": "ya",
        "щ": "sh"
    })

    s = s.translate(table)

    s = (
        s.replace("’", "'")
        .replace("‘", "'")
        .replace("ʻ", "'")
        .replace("ʼ", "'")
    )

    s = re.sub(r"[^a-z0-9'\s-]", " ", s)
    s = re.sub(r"\s+", " ", s)

    return s.strip()


def load_kb():
    if not os.path.exists(KB):
        raise RuntimeError(
            "knowledge_base_full.json topilmadi"
        )

    with open(KB, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        docs = data.get("documents", [])
    else:
        docs = data

    result = []

    for d in docs:
        if not isinstance(d, dict):
            continue

        text = d.get("text", "")

        if not text and d.get("blocks"):
            blocks = d.get("blocks")

            if isinstance(blocks, list):
                text = "\n\n".join(
                    str(x.get("text", x))
                    if isinstance(x, dict)
                    else str(x)
                    for x in blocks
                )

        result.append({
            "title": str(d.get("title", "")),
            "source": str(
                d.get(
                    "source_file",
                    d.get("file", "")
                )
            ),
            "text": str(text)
        })

    print(
        "Bilim bazasi:",
        len(result),
        "ta hujjat",
        flush=True
    )

    return result


DOCS = load_kb()


def doc_num(doc):
    s = norm(
        doc.get("source", "")
        + " "
        + doc.get("title", "")
    )

    m = re.search(
        r"\b(\d{2,5})\s*-?\s*(?:son|sonli|ii)\b",
        s
    )

    if m:
        return m.group(1)

    m = re.search(
        r"\b(?:pq|pf)\s*-?\s*(\d{2,5})\b",
        s
    )

    if m:
        return m.group(1)

    return ""


def requested_num(question):
    q = norm(question)

    patterns = [
        r"\b(?:vmq|vazirlar mahkamasi)\s*-?\s*(\d{2,5})\b",
        r"\b(?:pq|pf)\s*-?\s*(\d{2,5})\b",
        r"\b(\d{2,5})\s*-?\s*sonli\b",
        r"\b(\d{2,5})\s*-?\s*son\b",
        r"\b(\d{2,5})\s*ii\b",
        r"\b(\d{2,5})\s+(?:qaror|qonun|farmon)\b"
    ]

    for pattern in patterns:
        match = re.search(pattern, q)

        if match:
            return match.group(1)

    return None


def get_doc(number):
    if not number:
        return None

    number = str(number)

    for doc in DOCS:
        if doc_num(doc) == number:
            return doc

    return None


def chunks(text, size=1800):
    parts = [
        x.strip()
        for x in re.split(
            r"\n\s*\n|\n",
            str(text)
        )
        if len(x.strip()) >= 35
    ]

    result = []

    for part in parts:
        for i in range(0, len(part), size):
            piece = part[i:i + size].strip()

            if piece:
                result.append(piece)

    return result


def find_context(question, limit=10):
    number = requested_num(question)

    exact = get_doc(number) if number else None

    pool = [exact] if exact else DOCS

    words = [
        x
        for x in norm(question).split()
        if len(x) >= 3
    ]

    hits = []

    important = [
        "ilmiy ekspert kengashi",
        "tarixiy madaniy ekspertiza",
        "davlat kadastri",
        "davlat xizmati",
        "ruxsatnoma",
        "restavratsiya",
        "muhofaza zonasi",
        "loyiha hujjatlari",
        "qurilish",
        "ekspertiza",
        "madaniy meros"
    ]

    for doc in pool:

        title = norm(doc["title"])

        for chunk in chunks(doc["text"]):

            content = norm(chunk)

            score = 0

            for word in words:
                if word in content:
                    score += 2

                if word in title:
                    score += 4

            question_norm = norm(question)

            for phrase in important:
                if (
                    phrase in question_norm
                    and phrase in content
                ):
                    score += 10

            if score > 0:
                hits.append(
                    (score, doc, chunk)
                )

    hits.sort(
        key=lambda x: x[0],
        reverse=True
    )

    if exact and not hits:
        hits = [
            (0, exact, c)
            for c in chunks(
                exact["text"]
            )[:limit]
        ]

    hits = hits[:limit]

    if not hits:
        return "", None

    context = "\n\n".join(
        "[MANBA] "
        + doc["title"]
        + "\n"
        + chunk
        for _, doc, chunk in hits
    )

    return context[:30000], hits[0][1]


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
        doc = get_doc("269")

        if doc:
            return (
                "269-II-son "
                "“Madaniy meros obyektlarini "
                "muhofaza qilish va ulardan "
                "foydalanish to‘g‘risida”gi Qonun "
                "2001-yil 30-avgustda qabul qilingan."
                "\n\n"
                "Manba: "
                + doc["title"]
            )

    # 119-son qaror
if (
    "119" in q
    and any(
        x in q
        for x in [
            "qaror",
            "vmq",
            "sonli"
        ]
    )
):
    doc = get_doc("119")

    if doc:
        return (
            "119-сон қарор 2021 йил 3 мартда қабул қилинган.\n\n"
            "Тўлиқ номи:\n"
            + doc["title"]
            + "\n\n"
            "Манба: Ўзбекистон Республикаси Вазирлар Маҳкамасининг "
            "2021 йил 3 мартдаги 119-сон қарори."
        )

# Davlat xizmatlari va to‘lovlar

    # Davlat xizmatlari va to‘lovlar
    service = any(
        x in q
        for x in [
            "davlat xizm",
            "davlat xizmat",
            "tolov",
            "tulov",
            "bhm",
            "narx",
            "qancha"
        ]
    )

    if (
        service
        and (
            "agentlik" in q
            or "xizmat" in q
        )
    ):
        return (
            "Madaniy meros Agentligi bo‘yicha "
            "davlat xizmatlari:\n\n"

            "1. Moddiy madaniy meros "
            "obyektlarini davlat kadastriga "
            "kiritish va undan chiqarish — "
            "YIDXP orqali 0,5 BHM = "
            "220 000 so‘m.\n\n"

            "2. Moddiy madaniy meros obyektining "
            "davlat kadastriga kiritilgan yoki "
            "kiritilmaganligi haqida ma’lumot.\n\n"

            "3. Arxeologiya ashyosining davlat "
            "katalogiga kiritilgan yoki "
            "kiritilmaganligi haqida ma’lumot.\n\n"

            "4. Milliy muzey fondi ashyolari "
            "va kolleksiyalarining davlat "
            "katalogida hisobga olinganligi "
            "haqida ma’lumotnoma.\n\n"

            "VMQ 295-son 39-bandidagi "
            "to‘lovlar:\n"

            f"• Respublika toifasidagi tegishli "
            f"loyihalar — 10 BHM = "
            f"{10 * BHM:,} so‘m.\n"

            f"• Mahalliy toifadagi loyihalar — "
            f"5 BHM = {5 * BHM:,} so‘m.\n"

            f"• Maxsus muhofaza qilinadigan "
            f"tarixiy-madaniy/UNESCO hududlarida "
            f"qurish yoki buzish loyihalari: "
            f"yuridik shaxs — 20 BHM = "
            f"{20 * BHM:,} so‘m; "
            f"jismoniy shaxs — 1 BHM = "
            f"{BHM:,} so‘m.\n"

            f"• Davlat kadastriga kiritish/"
            f"chiqarish — 50% BHM = "
            f"{BHM // 2:,} so‘m.\n"

            f"• Tarixiy-madaniy ekspertiza: "
            f"respublika toifasi — 7 BHM = "
            f"{7 * BHM:,} so‘m; "
            f"mahalliy toifa — 4 BHM = "
            f"{4 * BHM:,} so‘m.\n"

            f"• Aholi punktining bosh rejasi "
            f"loyihasi — 5 BHM = "
            f"{5 * BHM:,} so‘m.\n\n"

            "Hisob-kitob 2026-yil 1-sentabrdan "
            "amaldagi 1 BHM = 440 000 so‘m "
            "asosida."
        )

    return None


def api(url, data=None, headers=None, timeout=90):
    headers = dict(headers or {})

    body = None

    if data is not None:
        body = json.dumps(
            data,
            ensure_ascii=False
        ).encode("utf-8")

        headers["Content-Type"] = (
            "application/json"
        )

    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method=(
            "POST"
            if data is not None
            else "GET"
        )
    )

    with urllib.request.urlopen(
        request,
        timeout=timeout
    ) as response:
        return json.loads(
            response.read().decode(
                "utf-8"
            )
        )


TELEGRAM = (
    "https://api.telegram.org/bot"
    + BOT_TOKEN
    + "/"
)


def tg(method, data=None):
    return api(
        TELEGRAM + method,
        data,
        timeout=45
    )


def send(chat_id, text):
    text = str(text or "").strip()

    text = (
        text.replace("**", "")
        .replace("```", "")
        .replace("__", "")
        .replace("`", "")
    )

    if not text:
        return

    for i in range(
        0,
        len(text),
        MAX_MSG
    ):
        tg(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text[
                    i:i + MAX_MSG
                ]
            }
        )


def answer(question):
    direct = direct_answer(question)

    if direct:
        return direct

    context, source = find_context(
        question
    )

    system = (
        "Siz Madaniy Meros AI — "
        "O‘zbekiston madaniy merosi "
        "sohasi bo‘yicha huquqiy-amaliy "
        "yordamchisiz.\n\n"

        "Asosiy manba — berilgan bilim "
        "bazasi.\n"

        "Manbada yo‘q huquqiy faktni "
        "o‘ylab topmang.\n"

        "Savol qaysi tilda berilgan bo‘lsa, "
        "shu tilda javob bering.\n"

        "Aniq, qisqa va amaliy javob bering.\n"

        "Modda yoki band raqamini faqat "
        "manbada aniq bo‘lsa ko‘rsating.\n"

        "Markdown yulduzchalaridan "
        "foydalanmang.\n\n"
    )

    if context:
        system += (
            "BILIM BAZASI:\n"
            + context
        )
    else:
        system += (
            "Mos huquqiy parcha topilmadi. "
            "Taxmin qilmang."
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
                "content": question
            }
        ]
    }

    result = api(
        "https://api.openai.com/v1/chat/completions",
        payload,
        {
            "Authorization":
                "Bearer " + OPENAI_API_KEY
        }
    )

    choices = result.get(
        "choices",
        []
    )

    if not choices:
        raise RuntimeError(
            "OpenAI javob qaytarmadi"
        )

    content = (
        choices[0]
        .get("message", {})
        .get("content", "")
    )

    if isinstance(content, list):
        content = "\n".join(
            str(x.get("text", ""))
            for x in content
            if isinstance(x, dict)
        )

    content = (
        str(content)
        .replace("**", "")
        .replace("```", "")
        .replace("__", "")
        .replace("`", "")
        .strip()
    )

    if not content:
        raise RuntimeError(
            "OpenAI bo‘sh javob qaytardi"
        )

    if source:
        content += (
            "\n\nManba: "
            + source["title"]
        )

    return content


def process_update(update):
    message = (
        update.get("message")
        or update.get("edited_message")
    )

    if not message:
        return

    if not isinstance(
        message.get("text"),
        str
    ):
        return

    chat_id = (
        message.get("chat") or {}
    ).get("id")

    question = message[
        "text"
    ].strip()

    if not chat_id or not question:
        return

    print(
        "Xabar:",
        question,
        flush=True
    )

    if question.startswith("/start"):
        send(
            chat_id,
            "🏛 Assalomu alaykum!\n\n"
            "Men — Madaniy Meros AI "
            "yordamchisiman.\n\n"
            "Madaniy meros, restavratsiya, "
            "muhofaza, loyiha hujjatlari, "
            "ekspertiza va normativ-huquqiy "
            "hujjatlar bo‘yicha savolingizni "
            "yozing.\n\n"
            "Masalan:\n"
            "119-sonli qaror nima haqida?"
        )
        return

    if question.startswith("/help"):
        send(
            chat_id,
            "Savolingizni oddiy tilda yozing.\n\n"
            "Masalan:\n"
            "• 119-sonli qaror nima haqida?\n"
            "• 269-II-son Qonun qachon qabul qilingan?\n"
            "• Tarixiy-madaniy ekspertiza tartibi qanday?\n"
            "• Davlat xizmatlari va to‘lovlar qancha?"
        )
        return

    send(
        chat_id,
        "⏳ Savolingiz ko‘rib chiqilmoqda..."
    )

    try:
        send(
            chat_id,
            answer(question)
        )

    except urllib.error.HTTPError as e:

        print(
            "HTTP xato:",
            e.code,
            flush=True
        )

        if e.code == 401:
            send(
                chat_id,
                "⚠️ OpenAI API kaliti noto‘g‘ri."
            )

        elif e.code == 429:
            send(
                chat_id,
                "⚠️ OpenAI API balansi yoki limiti bilan muammo."
            )

        else:
            send(
                chat_id,
                "⚠️ AI xizmatida texnik xatolik yuz berdi."
            )

    except Exception as e:

        print(
            "Javob xatosi:",
            repr(e),
            flush=True
        )

        send(
            chat_id,
            "⚠️ Javob tayyorlashda texnik xato yuz berdi. "
            "Keyinroq yana urinib ko‘ring."
        )


class Handler(
    BaseHTTPRequestHandler
):

    def do_GET(self):

        body = (
            "Madaniy Meros AI Bot ishlayapti!"
            .encode("utf-8")
        )

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
            self.end_headers()

            threading.Thread(
                target=process_update,
                args=(update,),
                daemon=True
            ).start()

        except Exception as e:

            print(
                "Webhook xatosi:",
                repr(e),
                flush=True
            )

            try:
                self.send_response(200)
                self.end_headers()
            except Exception:
                pass

    def log_message(
        self,
        format,
        *args
    ):
        return


def main():

    print(
        "================================",
        flush=True
    )

    print(
        "MADANIY MEROS AI",
        flush=True
    )

    print(
        "================================",
        flush=True
    )

    me = tg("getMe")

    print(
        "Telegram bot:",
        me.get(
            "result",
            {}
        ).get(
            "username",
            ""
        ),
        flush=True
    )

    server = ThreadingHTTPServer(
        ("0.0.0.0", PORT),
        Handler
    )

    threading.Thread(
        target=server.serve_forever,
        daemon=True
    ).start()

    if not RENDER_URL:
        raise RuntimeError(
            "RENDER_EXTERNAL_URL topilmadi"
        )

    webhook_url = (
        RENDER_URL
        + WEBHOOK_PATH
    )

    print(
        "Webhook:",
        webhook_url,
        flush=True
    )

    result = tg(
        "setWebhook",
        {
            "url": webhook_url,
            "allowed_updates": [
                "message",
                "edited_message"
            ],
            "drop_pending_updates": True
        }
    )

    print(
        "Webhook natijasi:",
        result,
        flush=True
    )

    while True:
        threading.Event().wait(3600)


if __name__ == "__main__":
    main()
