import os
import json
import time
import threading
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


# ============================================================
# MADANIY MEROS AI
# Telegram + OpenAI Responses API + knowledge_base.json
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

PORT = int(os.getenv("PORT", "10000"))

# Render Environment Variables orqali o'zgartirish mumkin
OPENAI_MODEL = os.getenv(
    "OPENAI_MODEL",
    "gpt-5.6"
).strip()

KNOWLEDGE_FILE = "knowledge_base.json"

TELEGRAM_TIMEOUT = 40
OPENAI_TIMEOUT = 90


# ============================================================
# STARTUP TEKSHIRUV
# ============================================================

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN topilmadi. Render Environment Variables ni tekshiring."
    )

if not OPENAI_API_KEY:
    raise RuntimeError(
        "OPENAI_API_KEY topilmadi. Render Environment Variables ni tekshiring."
    )


# ============================================================
# URL
# ============================================================

TELEGRAM_API = (
    "https://api.telegram.org/bot"
    + BOT_TOKEN
    + "/"
)

OPENAI_URL = (
    "https://api.openai.com/v1/responses"
)


# ============================================================
# UMUMIY HTTP FUNKSIYA
# ============================================================

def http_json(
    url,
    data=None,
    headers=None,
    timeout=60
):

    if headers is None:
        headers = {}

    body = None

    if data is not None:

        body = json.dumps(
            data,
            ensure_ascii=False
        ).encode("utf-8")

        headers = dict(headers)

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

    try:

        with urllib.request.urlopen(
            request,
            timeout=timeout
        ) as response:

            raw = response.read().decode(
                "utf-8"
            )

            return json.loads(raw)

    except urllib.error.HTTPError as e:

        error_body = e.read().decode(
            "utf-8",
            errors="ignore"
        )

        print(
            "HTTP ERROR "
            + str(e.code)
            + ": "
            + error_body,
            flush=True
        )

        raise

    except Exception as e:

        print(
            "HTTP ERROR: "
            + str(e),
            flush=True
        )

        raise


# ============================================================
# TELEGRAM
# ============================================================

def telegram(
    method,
    data=None
):

    return http_json(
        TELEGRAM_API + method,
        data=data,
        timeout=TELEGRAM_TIMEOUT
    )


def check_telegram():

    print(
        "Telegram token tekshirilmoqda...",
        flush=True
    )

    result = telegram(
        "getMe"
    )

    if not result.get("ok"):

        raise RuntimeError(
            "Telegram token ishlamayapti: "
            + str(result)
        )

    bot = result.get(
        "result",
        {}
    )

    print(
        "Telegram bot OK: @"
        + str(
            bot.get("username")
        ),
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
            "Webhook o'chirildi.",
            flush=True
        )

        print(
            result,
            flush=True
        )

    except Exception as e:

        print(
            "Webhook o'chirishda xato: "
            + str(e),
            flush=True
        )


# ============================================================
# TELEGRAM XABAR YUBORISH
# ============================================================

def send_message(
    chat_id,
    text
):

    if not text:

        text = (
            "Javob tayyorlashda "
            "xatolik yuz berdi."
        )

    text = str(text)

    # Telegram 4096 belgidan oshgan xabarlarni
    # bo'lib yuboradi
    max_length = 4000

    for start in range(
        0,
        len(text),
        max_length
    ):

        part = text[
            start:start + max_length
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
                "Xabar yuborishda xato: "
                + str(e),
                flush=True
            )


# ============================================================
# KNOWLEDGE BASE
# ============================================================

def load_knowledge_base():

    if not os.path.exists(
        KNOWLEDGE_FILE
    ):

        print(
            "DIQQAT: "
            + KNOWLEDGE_FILE
            + " topilmadi.",
            flush=True
        )

        return []

    try:

        with open(
            KNOWLEDGE_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        print(
            "Bilim bazasi yuklandi.",
            flush=True
        )

        if isinstance(data, list):

            print(
                "Hujjatlar soni: "
                + str(len(data)),
                flush=True
            )

        elif isinstance(data, dict):

            print(
                "Bilim bazasi: dict format.",
                flush=True
            )

        return data

    except Exception as e:

        print(
            "Bilim bazasini o'qishda xato: "
            + str(e),
            flush=True
        )

        return []


KNOWLEDGE_BASE = load_knowledge_base()


# ============================================================
# ISTALGAN JSON ELEMENTNI MATNGA AYLANTIRISH
# ============================================================

def value_to_text(value):

    if value is None:

        return ""

    if isinstance(
        value,
        str
    ):

        return value

    if isinstance(
        value,
        list
    ):

        parts = []

        for item in value:

            item_text = value_to_text(
                item
            )

            if item_text:

                parts.append(
                    item_text
                )

        return "\n".join(parts)

    if isinstance(
        value,
        dict
    ):

        parts = []

        for key, item in value.items():

            item_text = value_to_text(
                item
            )

            if item_text:

                parts.append(
                    str(key)
                    + ": "
                    + item_text
                )

        return "\n".join(parts)

    return str(value)


# ============================================================
# HUJJAT NOMINI ANIQLASH
# ============================================================

def get_document_title(
    document,
    index
):

    if isinstance(
        document,
        dict
    ):

        possible_keys = [
            "title",
            "name",
            "document_title",
            "act_title",
            "ACT_TITLE",
            "filename",
            "file"
        ]

        for key in possible_keys:

            if key in document:

                value = str(
                    document.get(key)
                ).strip()

                if value:

                    return value

    return (
        "Hujjat "
        + str(index + 1)
    )


# ============================================================
# BILIM BAZASINI HUJJATLARGA AJRATISH
# ============================================================

def get_documents():

    data = KNOWLEDGE_BASE

    if isinstance(
        data,
        list
    ):

        return data

    if isinstance(
        data,
        dict
    ):

        # Agar asosiy kalitlardan biri list bo'lsa
        for key in [
            "documents",
            "docs",
            "knowledge",
            "items",
            "data"
        ]:

            value = data.get(key)

            if isinstance(
                value,
                list
            ):

                return value

        # Dictning o'zini bitta hujjat deb olamiz
        return [data]

    return [data]


# ============================================================
# SAVOL BO'YICHA BILIM BAZASIDAN ENG MOS HUJJATLARNI TOPISH
# ============================================================

def search_knowledge(
    question
):

    documents = get_documents()

    if not documents:

        return ""

    question_words = (
        question
        .lower()
        .replace(",", " ")
        .replace(".", " ")
        .replace("?", " ")
        .replace("!", " ")
        .replace(":", " ")
        .replace(";", " ")
        .replace("(", " ")
        .replace(")", " ")
        .replace('"', " ")
        .replace("'", " ")
        .split()
    )

    # Juda umumiy so'zlarni hisobga olmaslik
    stop_words = {
        "va",
        "ham",
        "bu",
        "shu",
        "uchun",
        "bilan",
        "qanday",
        "nima",
        "qachon",
        "qayerda",
        "mumkin",
        "kerak",
        "bor",
        "bir",
        "men",
        "siz",
        "ning",
        "dan",
        "ga",
        "ni",
        "da",
        "mi",
        "to",
        "g",
        "the"
    }

    useful_words = []

    for word in question_words:

        if (
            len(word) >= 3
            and word not in stop_words
        ):

            useful_words.append(
                word
            )

    scored = []

    for index, document in enumerate(
        documents
    ):

        text = value_to_text(
            document
        )

        if not text:

            continue

        lower_text = text.lower()

        score = 0

        for word in useful_words:

            if word in lower_text:

                score += 1

        title = get_document_title(
            document,
            index
        )

        title_lower = title.lower()

        for word in useful_words:

            if word in title_lower:

                score += 3

        scored.append(
            (
                score,
                title,
                text
            )
        )

    scored.sort(
        key=lambda item: item[0],
        reverse=True
    )

    selected = []

    for score, title, text in scored:

        if score <= 0:

            continue

        # Har bir hujjatdan maksimal 6000 belgi
        excerpt = text[:6000]

        selected.append(
            "MANBA: "
            + title
            + "\n"
            + excerpt
        )

        if len(selected) >= 3:

            break

    if not selected:

        return ""

    result = "\n\n".join(
        selected
    )

    # OpenAI prompt juda katta bo'lib ketmasligi uchun
    return result[:18000]


# ============================================================
# OPENAI RESPONSES API
# ============================================================

def extract_openai_text(
    result
):

    # Responses API ning oddiy output_text varianti
    output_text = result.get(
        "output_text"
    )

    if isinstance(
        output_text,
        str
    ) and output_text.strip():

        return output_text.strip()

    # Zaxira parser
    output = result.get(
        "output",
        []
    )

    parts = []

    if isinstance(
        output,
        list
    ):

        for item in output:

            if not isinstance(
                item,
                dict
            ):

                continue

            content = item.get(
                "content",
                []
            )

            if not isinstance(
                content,
                list
            ):

                continue

            for block in content:

                if not isinstance(
                    block,
                    dict
                ):

                    continue

                text = block.get(
                    "text"
                )

                if isinstance(
                    text,
                    str
                ) and text:

                    parts.append(
                        text
                    )

    if parts:

        return "\n".join(
            parts
        ).strip()

    return ""


def openai_answer(
    question
):

    knowledge = search_knowledge(
        question
    )

    system_text = (
        "Siz Madaniy Meros AI "
        "nomli O'zbekiston madaniy "
        "merosi bo'yicha ixtisoslashgan "
        "yordamchisiz.\n\n"

        "Asosiy yo'nalishlar:\n"
        "- madaniy meros obyektlari;\n"
        "- tarixiy-me'moriy obyektlar;\n"
        "- muhofaza qilish;\n"
        "- restavratsiya;\n"
        "- konservatsiya;\n"
        "- ta'mirlash;\n"
        "- moslashtirish;\n"
        "- loyiha hujjatlari;\n"
        "- ilmiy-ekspert kengashi;\n"
        "- muhofaza zonalari;\n"
        "- madaniy meros hududlaridagi "
        "qurilish.\n\n"

        "Javoblarni o'zbek tilida bering.\n"
        "Javob aniq va amaliy bo'lsin.\n"
        "Kerak bo'lsa punktlardan foydalaning.\n\n"

        "MUHIM QOIDA:\n"
        "Agar quyida bilim bazasidan "
        "ma'lumot berilgan bo'lsa, "
        "avvalo shu ma'lumotga tayaning.\n"

        "Qonun, qaror, sana yoki raqamni "
        "o'ylab topmang.\n"

        "Bilim bazasida javob uchun yetarli "
        "ma'lumot bo'lmasa, buni ochiq "
        "ayting va tasdiqlanmagan faktni "
        "aniq fakt sifatida bermang."
    )

    if knowledge:

        system_text += (
            "\n\n"
            "BILIM BAZASIDAN TOPILGAN "
            "TEGISHLI MA'LUMOTLAR:\n"
            "--------------------------------\n"
            + knowledge
            + "\n"
            "--------------------------------\n"
        )

    request_data = {

        "model": OPENAI_MODEL,

        "instructions": system_text,

        "input": question
    }

    headers = {

        "Authorization":
            "Bearer " + OPENAI_API_KEY,

        "Content-Type":
            "application/json"
    }

    try:

        result = http_json(
            OPENAI_URL,
            data=request_data,
            headers=headers,
            timeout=OPENAI_TIMEOUT
        )

        answer = extract_openai_text(
            result
        )

        if answer:

            return answer

        print(
            "OpenAI bo'sh javob qaytardi.",
            flush=True
        )

        return (
            "Kechirasiz, javob tayyorlashda "
            "ma'lumot olinmadi."
        )

    except urllib.error.HTTPError as e:

        print(
            "OPENAI HTTP ERROR "
            + str(e.code),
            flush=True
        )

        raise

    except Exception as e:

        print(
            "OPENAI XATOSI: "
            + str(e),
            flush=True
        )

        raise


# ============================================================
# START
# ============================================================

def start_message():

    return (
        "🏛 Assalomu alaykum!\n\n"

        "Men — Madaniy Meros AI "
        "yordamchisiman.\n\n"

        "O'zbekiston madaniy merosi, "
        "tarixiy-me'moriy obyektlar, "
        "restavratsiya, muhofaza va "
        "loyiha hujjatlari bo'yicha "
        "savollaringizga yordam beraman.\n\n"

        "Savolingizni yuboring."
    )


# ============================================================
# HELP
# ============================================================

def help_message():

    return (
        "📚 Madaniy Meros AI\n\n"

        "Savolingizni oddiy matn "
        "ko'rinishida yuboring.\n\n"

        "Masalan:\n"
        "• Madaniy meros obyekti nima?\n"
        "• 269-II-son Qonun qachon "
        "qabul qilingan?\n"
        "• Restavratsiya loyihasida "
        "nimalar bo'lishi kerak?\n"
        "• Ilmiy-ekspert kengashi "
        "nima bilan shug'ullanadi?\n"
        "• Tarixiy binoning tashqi "
        "ko'rinishini o'zgartirish "
        "mumkinmi?"
    )


# ============================================================
# UPDATE QAYTA ISHLASH
# ============================================================

def process_update(
    update
):

    try:

        message = update.get(
            "message"
        )

        if not message:

            return

        chat = message.get(
            "chat",
            {}
        )

        chat_id = chat.get(
            "id"
        )

        text = message.get(
            "text",
            ""
        )

        if not chat_id:

            return

        if not text:

            return

        text = text.strip()

        if not text:

            return

        print(
            "Savol: "
            + text,
            flush=True
        )

        # /start
        if text.startswith(
            "/start"
        ):

            send_message(
                chat_id,
                start_message()
            )

            return

        # /help
        if text.startswith(
            "/help"
        ):

            send_message(
                chat_id,
                help_message()
            )

            return

        # Savol qabul qilindi
        send_message(
            chat_id,
            "⏳ Savolingiz ko'rib chiqilmoqda..."
        )

        try:

            answer = openai_answer(
                text
            )

            send_message(
                chat_id,
                answer
            )

        except urllib.error.HTTPError as e:

            error_code = e.code

            if error_code == 401:

                message_text = (
                    "⚠️ OpenAI API kaliti "
                    "qabul qilinmadi.\n\n"
                    "Render Environment Variables "
                    "bo'limidagi OPENAI_API_KEY "
                    "qiymatini tekshirish kerak."
                )

            elif error_code == 429:

                message_text = (
                    "⚠️ OpenAI API limiti yoki "
                    "billing bilan bog'liq muammo."
                )

            else:

                message_text = (
                    "⚠️ OpenAI xizmatida "
                    "texnik xatolik yuz berdi.\n"
                    "Birozdan keyin yana urinib ko'ring."
                )

            send_message(
                chat_id,
                message_text
            )

        except Exception as e:

            print(
                "Savolga javob berishda xato: "
                + str(e),
                flush=True
            )

            send_message(
                chat_id,
                (
                    "⚠️ Hozircha javob "
                    "tayyorlashda texnik xatolik "
                    "yuz berdi.\n"
                    "Birozdan keyin yana urinib ko'ring."
                )
            )

    except Exception as e:

        print(
            "UPDATE XATOSI: "
            + str(e),
            flush=True
        )


# ============================================================
# TELEGRAM POLLING
# ============================================================

def telegram_polling():

    print(
        "Telegram polling boshlandi...",
        flush=True
    )

    offset = None

    while True:

        try:

            request_data = {

                "timeout": 30,

                "limit": 100,

                "allowed_updates": [
                    "message"
                ]
            }

            if offset is not None:

                request_data[
                    "offset"
                ] = offset

            result = telegram(
                "getUpdates",
                request_data
            )

            if not result.get(
                "ok"
            ):

                print(
                    "getUpdates xatosi: "
                    + str(result),
                    flush=True
                )

                time.sleep(5)

                continue

            updates = result.get(
                "result",
                []
            )

            for update in updates:

                update_id = update.get(
                    "update_id"
                )

                if update_id is not None:

                    offset = (
                        update_id + 1
                    )

                process_update(
                    update
                )

        except urllib.error.HTTPError as e:

            if e.code == 409:

                print(
                    "Telegram 409: boshqa "
                    "polling instance mavjud.",
                    flush=True
                )

                time.sleep(10)

            else:

                print(
                    "Telegram HTTP xatosi: "
                    + str(e),
                    flush=True
                )

                time.sleep(5)

        except Exception as e:

            print(
                "Telegram polling xatosi: "
                + str(e),
                flush=True
            )

            time.sleep(5)


# ============================================================
# RENDER HEALTH SERVER
# ============================================================

class HealthHandler(
    BaseHTTPRequestHandler
):

    def do_GET(
        self
    ):

        body = (
            "Madaniy Meros AI Bot ishlayapti!"
        ).encode(
            "utf-8"
        )

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

    def do_HEAD(
        self
    ):

        self.send_response(
            200
        )

        self.send_header(
            "Content-Type",
            "text/plain"
        )

        self.end_headers()

    def log_message(
        self,
        format,
        *args
    ):

        return


def run_web_server():

    server = ThreadingHTTPServer(
        (
            "0.0.0.0",
            PORT
        ),
        HealthHandler
    )

    print(
        "Web server PORT="
        + str(PORT),
        flush=True
    )

    server.serve_forever()


# ============================================================
# MAIN
# ============================================================

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
        "Model: "
        + OPENAI_MODEL,
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


# ============================================================
# START PROGRAM
# ============================================================

if __name__ == "__main__":

    main()
