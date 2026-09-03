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
        print("Bilim bazasi yuklandi:", len(docs), "ta hujjat", flush=True)
        return docs
    except Exception as e:
        print("Bilim bazasini yuklashda xato:", e, flush=True)
        return []


DOCUMENTS = load_knowledge()


def http_json(url, data=None, headers=None, timeout=60):
    if headers is None:
        headers = {}

    body = None
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers = dict(headers)
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method="POST" if data is not None else "GET"
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        print(f"HTTP ERROR {e.code}: {error_body}", flush=True)
        raise
    except Exception as e:
        print(f"HTTP ERROR: {e}", flush=True)
        raise


TELEGRAM_API = "https://api.telegram.org/bot" + BOT_TOKEN + "/"


def telegram(method, data=None):
    return http_json(
        TELEGRAM_API + method,
        data=data,
        timeout=TELEGRAM_TIMEOUT
    )


def check_telegram():
    result = telegram("getMe")

    if not result.get("ok"):
        raise RuntimeError("Telegram token ishlamayapti")

    bot = result.get("result", {})
    print("Telegram bot OK: @" + str(bot.get("username")), flush=True)


def remove_webhook():
    try:
        result = telegram(
            "deleteWebhook",
            {"drop_pending_updates": False}
        )
        print("Webhook holati:", result, flush=True)
    except Exception as e:
        print("Webhook o'chirishda xato:", e, flush=True)


def clean_answer(text):
    if not text:
        return "Javob tayyorlashda xatolik yuz berdi."

    text = str(text)

    # Telegramda ** belgilarining oddiy matn sifatida chiqib qolishini oldini olamiz.
    text = text.replace("**", "")
    text = text.replace("__", "")
    text = text.replace("```", "")
    text = text.replace("`", "")

    # Ortiqcha bo'sh qatorlarni kamaytirish.
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def send_message(chat_id, text):
    text = clean_answer(text)
    max_length = 4000

    for i in range(0, len(text), max_length):
        part = text[i:i + max_length]

        try:
            telegram(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": part
                }
            )
        except Exception as e:
            print("Xabar yuborishda xato:", e, flush=True)


def normalize(text):
    text = str(text).lower()

    # O'zbek kirill/lotin harflari saqlanadi.
    text = re.sub(
        r"[^a-zа-яёўқғҳқʼʻ'0-9\s-]",
        " ",
        text
    )

    return re.sub(r"\s+", " ", text).strip()


def document_number(doc):
    title = str(doc.get("title", ""))
    source = str(doc.get("source_file", ""))

    match = re.search(r"(?<!\d)(\d{2,5})-?(?:ii|son|с[oо]н)", title.lower())
    if match:
        return match.group(1)

    match = re.search(r"(\d{2,5})", source)
    if match:
        return match.group(1)

    match = re.search(r"(?<!\d)(\d{2,5})(?!\d)", title)
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

    # Masalan: "119-sonli qaror", "VMQ 119", "119-son", "119 qaror".
    patterns = [
        r"\b(?:vmq|vazirlar mahkamasi)\s*[- ]?\s*(\d{2,5})\b",
        r"\b(\d{2,5})\s*-\s*son\b",
        r"\b(\d{2,5})\s*sonli\b",
        r"\b(\d{2,5})\s*son\b",
        r"\b(?:pq|pf)\s*[- ]?\s*(\d{2,5})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, q)
        if match:
            return match.group(1)

    return None


def split_chunks(text):
    paragraphs = [
        p.strip()
        for p in re.split(r"\n{2,}|\n", str(text))
        if len(p.strip()) >= 50
    ]

    chunks = []

    for paragraph in paragraphs:
        if len(paragraph) <= 1800:
            chunks.append(paragraph)
        else:
            for i in range(0, len(paragraph), 1500):
                chunks.append(paragraph[i:i + 1500])

    return chunks


def relevant_chunks(doc, question, max_chunks=8):
    chunks = split_chunks(doc.get("text", ""))
    if not chunks:
        return []

    q = normalize(question)
    words = [w for w in q.split() if len(w) >= 3]

    candidates = []

    important_words = [
        "restavrats",
        "ta'mir",
        "loyiha",
        "ekspert",
        "muhofaza",
        "ruxsat",
        "agentlik",
        "madaniy meros",
        "davlat xizmati",
        "to'lov",
        "tartib",
        "kengash",
        "qaror",
        "modda",
        "band",
        "ilova",
    ]

    for index, chunk in enumerate(chunks):
        c = normalize(chunk)
        score = 0

        for word in words:
            if word in c:
                score += 1

        for important in important_words:
            if important in q and important in c:
                score += 4

        # Hujjatning bosh qismi (sana, raqam, nomi) muhim.
        if index < 4:
            score += 1

        if score > 0:
            candidates.append((score, index, chunk))

    candidates.sort(key=lambda x: (x[0], -x[1]), reverse=True)

    selected = []
    seen = set()

    for score, index, chunk in candidates:
        key = normalize(chunk[:200])

        if key in seen:
            continue

        seen.add(key)
        selected.append((index, chunk))

        if len(selected) >= max_chunks:
            break

    # Agar savol faqat "119-sonli qaror" kabi umumiy bo'lsa,
    # hujjatning bosh qismini albatta beramiz.
    if not selected:
        selected = [
            (i, chunk)
            for i, chunk in enumerate(chunks[:max_chunks])
        ]

    selected.sort(key=lambda x: x[0])

    return [chunk for _, chunk in selected]


def find_knowledge(question):
    # 1. Avval hujjat raqamini aniq aniqlaymiz.
    number = requested_document_number(question)

    if number:
        doc = get_document_by_number(number)

        if doc:
            title = doc.get("title", "")
            chunks = relevant_chunks(doc, question, max_chunks=10)

            context = [
                "[ANIQ TANLANGAN MANBA]",
                "Hujjat raqami: " + number,
                "Hujjat nomi: " + title,
                "Manba fayli: " + str(doc.get("source_file", "")),
                "",
                "\n\n".join(chunks)
            ]

            return "\n".join(context), doc

    # 2. Raqam ko'rsatilmagan savollar uchun umumiy qidiruv.
    q = normalize(question)
    words = [w for w in q.split() if len(w) >= 3]

    candidates = []

    for doc in DOCUMENTS:
        title = str(doc.get("title", ""))
        text = str(doc.get("text", ""))

        for index, chunk in enumerate(split_chunks(text)):
            c = normalize(chunk)
            score = 0

            for word in words:
                if word in c:
                    score += 1

            if title:
                title_norm = normalize(title)
                for word in words:
                    if word in title_norm:
                        score += 2

            if score > 0:
                candidates.append(
                    (score, title, index, chunk, doc)
                )

    candidates.sort(
        key=lambda x: (x[0], -x[2]),
        reverse=True
    )

    selected = []
    seen = set()

    for score, title, index, chunk, doc in candidates:
        key = normalize(chunk[:200])

        if key in seen:
            continue

        seen.add(key)
        selected.append((title, chunk, doc))

        if len(selected) >= 8:
            break

    if not selected:
        return "", None

    parts = []

    for title, chunk, doc in selected:
        parts.append(
            "[MANBA: " + title + "]\n" + chunk
        )

    return "\n\n".join(parts), selected[0][2]


def extract_openai_text(result):
    # Chat Completions javobi.
    choices = result.get("choices", [])

    if choices:
        message = choices[0].get("message", {})
        content = message.get("content", "")

        if isinstance(content, str) and content.strip():
            return content.strip()

    # Responses API formatiga mos fallback.
    output_text = result.get("output_text")

    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    output = result.get("output", [])

    if isinstance(output, list):
        parts = []

        for item in output:
            content = item.get("content", [])

            if isinstance(content, list):
                for block in content:
                    text = block.get("text", "")

                    if isinstance(text, str) and text.strip():
                        parts.append(text)

        if parts:
            return "\n".join(parts).strip()

    return ""


def openai_answer(question):
    knowledge, source_doc = find_knowledge(question)

    system_text = (
        "Siz Madaniy Meros AI nomli O'zbekiston madaniy merosi "
        "bo'yicha maxsus huquqiy-amaliy yordamchisiz.\n\n"

        "Asosiy yo'nalishlar:\n"
        "- moddiy madaniy meros obyektlarini muhofaza qilish;\n"
        "- tarixiy-me'moriy obyektlar;\n"
        "- restavratsiya va ta'mirlash;\n"
        "- loyiha hujjatlari;\n"
        "- Ilmiy-ekspert kengashi;\n"
        "- Madaniy meros agentligi;\n"
        "- davlat xizmatlari;\n"
        "- normativ-huquqiy hujjatlar.\n\n"

        "Javobni foydalanuvchi tilida, tushunarli o'zbek tilida bering.\n\n"

        "MUHIM HUQUQIY QOIDALAR:\n"
        "1. Berilgan bilim bazasidagi manbani asosiy manba deb oling.\n"
        "2. Hujjat raqami aniq tanlangan bo'lsa, faqat shu hujjatga "
        "tayangan holda javob bering.\n"
        "3. Manbada yo'q ma'lumotni qonun yoki qaror talabi sifatida "
        "o'ylab topmang.\n"
        "4. Band yoki modda raqami manbada aniq bo'lmasa, uni taxmin qilmang.\n"
        "5. Hujjat nomi, raqami va sanasini imkon qadar aniq ko'rsating.\n"
        "6. Agar savol to'lov, davlat xizmati yoki tartib haqida bo'lsa, "
        "tegishli ilova/banddagi ma'lumotni ajratib ko'rsating.\n"
        "7. Agar manba yetarli bo'lmasa, 'Taqdim etilgan bilim bazasida "
        "bu savolga yetarli aniq ma'lumot topilmadi' deb ayting.\n\n"

        "Javob uslubi:\n"
        "- aniq;\n"
        "- qisqa;\n"
        "- amaliy;\n"
        "- kerak bo'lsa punktlar bilan.\n"
        "- Markdown yulduzchalaridan foydalanmang."
    )

    if knowledge:
        system_text += (
            "\n\nHUQUQIY MANBA MA'LUMOTLARI:\n" +
            knowledge
        )
    else:
        system_text += (
            "\n\nHUQUQIY MANBA TOPILMADI. "
            "Aniq huquqiy faktni o'ylab topmang."
        )

    data = {
        "model": OPENAI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": system_text
            },
            {
                "role": "user",
                "content": question
            }
        ]
    }

    headers = {
        "Authorization": "Bearer " + OPENAI_API_KEY,
        "Content-Type": "application/json"
    }

    result = http_json(
        "https://api.openai.com/v1/chat/completions",
        data=data,
        headers=headers,
        timeout=OPENAI_TIMEOUT
    )

    answer = extract_openai_text(result)

    if not answer:
        return "OpenAI javob qaytarmadi."

    answer = clean_answer(answer)

    # Botga foydalanuvchi so'ramagan ortiqcha manba matnini qo'shmaymiz.
    if source_doc:
        title = str(source_doc.get("title", "")).strip()

        if title and "Manba:" not in answer:
            answer += "\n\nManba: " + title

    return answer


def start_message():
    return (
        "🏛 Assalomu alaykum!\n\n"
        "Men — Madaniy Meros AI yordamchisiman.\n\n"
        "O'zbekiston madaniy merosi, tarixiy-me'moriy obyektlar, "
        "restavratsiya, muhofaza, davlat xizmatlari va loyiha "
        "hujjatlari bo'yicha savollaringizga yordam beraman.\n\n"
        "Masalan:\n"
        "• 119-sonli qaror\n"
        "• 269-II-son Qonun qachon qabul qilingan?\n"
        "• Restavratsiya loyihasini kim ko'rib chiqadi?\n"
        "• Madaniy meros obyektida qurilish uchun nima kerak?\n\n"
        "Savolingizni yuboring."
    )


def help_message():
    return (
        "📚 Savol berish bo'yicha:\n\n"
        "Hujjat raqamini aniq yozsangiz, men avval aynan shu "
        "hujjatni tanlayman.\n\n"
        "Masalan:\n"
        "• 119-sonli qaror\n"
        "• VMQ 119\n"
        "• 269-II-son Qonun\n"
        "• VMQ 295\n"
        "• PQ-177\n\n"
        "Shuningdek, oddiy savol berishingiz mumkin."
    )


def process_update(update):
    try:
        message = update.get("message")

        if not message:
            return

        chat = message.get("chat", {})
        chat_id = chat.get("id")
        text = message.get("text", "")

        if not chat_id or not text:
            return

        text = text.strip()

        print(
            f"Xabar: {chat_id}: {text}",
            flush=True
        )

        if text.startswith("/start"):
            send_message(chat_id, start_message())
            return

        if text.startswith("/help"):
            send_message(chat_id, help_message())
            return

        send_message(
            chat_id,
            "⏳ Savolingiz ko'rib chiqilmoqda..."
        )

        try:
            answer = openai_answer(text)
            send_message(chat_id, answer)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                send_message(
                    chat_id,
                    "⚠️ OpenAI API kaliti bilan bog'liq xatolik."
                )
            elif e.code == 429:
                send_message(
                    chat_id,
                    "⚠️ OpenAI limiti yoki billing bo'yicha muammo yuz berdi."
                )
            else:
                send_message(
                    chat_id,
                    "⚠️ Javob tayyorlashda texnik xatolik yuz berdi."
                )

            print("OpenAI HTTP xatosi:", e, flush=True)

        except Exception as e:
            print("OpenAI xatosi:", e, flush=True)

            send_message(
                chat_id,
                "⚠️ Hozircha javob tayyorlashda texnik xatolik yuz berdi.\n"
                "Birozdan keyin yana urinib ko'ring."
            )

    except Exception as e:
        print("UPDATE XATOSI:", e, flush=True)


def telegram_polling():
    print("Telegram polling boshlandi...", flush=True)

    offset = None

    while True:
        try:
            data = {
                "timeout": 30,
                "limit": 100,
                "allowed_updates": ["message"]
            }

            if offset is not None:
                data["offset"] = offset

            result = telegram("getUpdates", data)

            if not result.get("ok"):
                print(
                    "getUpdates xatosi:",
                    result,
                    flush=True
                )
                time.sleep(5)
                continue

            updates = result.get("result", [])

            for update in updates:
                update_id = update.get("update_id")

                if update_id is not None:
                    offset = update_id + 1

                process_update(update)

        except Exception as e:
            print(
                "Telegram polling xatosi:",
                e,
                flush=True
            )
            time.sleep(5)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = (
            "Madaniy Meros AI Bot ishlayapti!"
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

    def do_HEAD(self):
        self.send_response(200)
        self.send_header(
            "Content-Type",
            "text/plain"
        )
        self.end_headers()

    def log_message(self, format, *args):
        return


def run_web_server():
    server = ThreadingHTTPServer(
        ("0.0.0.0", PORT),
        HealthHandler
    )

    print(
        f"Web server PORT={PORT}",
        flush=True
    )

    server.serve_forever()


def main():
    print(
        "====================================",
        flush=True
    )
    print(
        "MADANIY MEROS AI BOT",
        flush=True
    )
    print(
        "====================================",
        flush=True
    )

    check_telegram()
    remove_webhook()

    web_thread = threading.Thread(
        target=run_web_server,
        daemon=True
    )
    web_thread.start()

    telegram_polling()


if __name__ == "__main__":
    main()
