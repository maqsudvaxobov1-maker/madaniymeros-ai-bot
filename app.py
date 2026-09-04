import os
import re
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6").strip()

PORT = int(os.getenv("PORT", "10000"))

RENDER_EXTERNAL_URL = os.getenv(
    "RENDER_EXTERNAL_URL",
    ""
).rstrip("/")

WEBHOOK_PATH = "/telegram/webhook"

WEBHOOK_URL = (
    RENDER_EXTERNAL_URL + WEBHOOK_PATH
    if RENDER_EXTERNAL_URL
    else ""
)

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)


# ============================================================
# BILIM BAZASI FAYLINI TOPISH
# ============================================================

KB_FILES = [
    "knowledge_base_full_4.json",
    "knowledge_base_4.json",
    "knowledge_base.json",
    "knowledge_base_full.json",
    "knowledge_base_full_old.json"
]


def find_kb_file():
    for filename in KB_FILES:
        path = os.path.join(
            BASE_DIR,
            filename
        )

        if os.path.isfile(path):
            return path

    raise RuntimeError(
        "Bilim bazasi JSON fayli topilmadi"
    )


# ============================================================
# MATNNI NORMALIZATSIYA QILISH
# ============================================================

def norm(text):
    text = str(text or "")

    text = (
        text
        .lower()
        .replace("’", "'")
        .replace("ʻ", "'")
        .replace("ʼ", "'")
        .replace("ё", "е")
    )

    table = str.maketrans({
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ж": "j",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "x",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "sh",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
        "қ": "q",
        "ғ": "g'",
        "ҳ": "h",
        "ў": "o'"
    })

    text = text.translate(table)

    text = re.sub(
        r"[^a-z0-9']+",
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
    path = find_kb_file()

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:
        data = json.load(file)

    if isinstance(data, dict):
        raw_documents = data.get(
            "documents",
            data.get("docs", [])
        )

    elif isinstance(data, list):
        raw_documents = data

    else:
        raw_documents = []

    documents = []

    for item in raw_documents:

        if not isinstance(item, dict):
            continue

        title = str(
            item.get("title", "")
        ).strip()

        source = str(
            item.get(
                "source_file",
                item.get("source", "")
            )
        ).strip()

        text = str(
            item.get(
                "text",
                item.get("content", "")
            )
        ).strip()

        if not text:
            continue

        documents.append({
            "title": title,
            "source_file": source,
            "text": text,
            "ntitle": norm(title),
            "nsource": norm(source),
            "ntext": norm(text)
        })

    if not documents:
        raise RuntimeError(
            "Bilim bazasida hujjatlar topilmadi"
        )

    logging.info(
        "Bilim bazasi yuklandi: %s ta hujjat",
        len(documents)
    )

    logging.info(
        "KB fayl: %s",
        os.path.basename(path)
    )

    return documents


DOCUMENTS = load_kb()


# ============================================================
# SO'ZLAR
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
    "bo'yicha",
    "siz",
    "men",
    "ning",
    "ni",
    "ga",
    "da",
    "dan",
    "mi",
    "mumkin",
    "bolsa"
}


def keywords(question):
    q = norm(question)

    words = q.split()

    result = []

    for word in words:

        if len(word) < 2:
            continue

        if word in STOP_WORDS:
            continue

        if word not in result:
            result.append(word)

    return result


# ============================================================
# HUJJAT RAQAMINI ANIQLASH
# ============================================================

def detect_number(question):
    q = norm(question)

    if re.search(
        r"\b269\s*ii\b",
        q
    ):
        return "269"

    match = re.search(
        r"\b(?:pq|pk)\s*(\d+)\b",
        q
    )

    if match:
        return match.group(1)

    match = re.search(
        r"\b(?:vmq|vm)\s*(\d+)\b",
        q
    )

    if match:
        return match.group(1)

    match = re.search(
        r"\b(\d{1,5})\s*(?:sonli|son|qaror|qonun)\b",
        q
    )

    if match:
        return match.group(1)

    match = re.search(
        r"\b(119|269)\b",
        q
    )

    if match:
        return match.group(1)

    return None


# ============================================================
# MATNNI BO'LISHL
# ============================================================

def make_chunks(
    text,
    size=3500,
    overlap=500
):
    if len(text) <= size:
        return [text]

    result = []

    start = 0

    while start < len(text):

        end = min(
            len(text),
            start + size
        )

        result.append(
            text[start:end]
        )

        if end >= len(text):
            break

        start = end - overlap

    return result


# ============================================================
# EKSPERTIZA SAVOLINI ANIQLASH
# ============================================================

def is_expertise_question(q):

    if "ekspertiza" not in q:
        return False

    words = [
        "tarixiy",
        "madaniy",
        "muddat",
        "xulosa",
        "tartib",
        "kengash",
        "30 kun"
    ]

    return any(
        word in q
        for word in words
    )


# ============================================================
# BILIM BAZASIDAN QIDIRISH
# ============================================================

def search_kb(
    question,
    limit=8
):
    q = norm(question)

    keys = keywords(question)

    number = detect_number(question)

    candidates = []

    expertise = is_expertise_question(q)

    for doc in DOCUMENTS:

        document_bonus = 0

        title = doc["ntitle"]

        source = doc["nsource"]

        text = doc["ntext"]

        # ----------------------------------------------------
        # HUJJAT RAQAMI ANIQ BO'LSA
        # ----------------------------------------------------

        if number:

            if number in title:
                document_bonus += 180

            if number in source:
                document_bonus += 180

        # ----------------------------------------------------
        # TARIXIY-MADANIY EKSPERTIZA
        # ----------------------------------------------------

        if expertise:

            # 269-son Nizom ustuvor
            if "269" in title:
                document_bonus += 300

            if "269" in source:
                document_bonus += 300

            if "ekspertiza" in text:
                document_bonus += 100

        # ----------------------------------------------------
        # MATNNI BO'LIB QIDIRISH
        # ----------------------------------------------------

        for index, chunk in enumerate(
            make_chunks(doc["text"])
        ):

            normalized_chunk = norm(
                chunk
            )

            score = document_bonus

            # Butun savol
            if (
                len(q) >= 10
                and q in normalized_chunk
            ):
                score += 100

            # Kalit so'zlar
            for key in keys:

                if key in normalized_chunk:
                    score += 4

                if key in title:
                    score += 8

                if key in source:
                    score += 8

            # Muhim so'zlar
            important_words = [
                "ekspertiza",
                "ekspert",
                "qurilish",
                "buzish",
                "ruxsat",
                "muhofaza",
                "kadastr",
                "tolov",
                "xizmat",
                "yunesko"
            ]

            for word in important_words:

                if (
                    word in q
                    and word in normalized_chunk
                ):
                    score += 12

            if score > 0:

                candidates.append(
                    (
                        score,
                        index,
                        doc,
                        chunk
                    )
                )

    candidates.sort(
        key=lambda item: (
            item[0],
            -item[1]
        ),
        reverse=True
    )

    selected = []

    seen = set()

    for (
        score,
        index,
        doc,
        chunk
    ) in candidates:

        unique_key = norm(
            chunk[:250]
        )

        if unique_key in seen:
            continue

        seen.add(unique_key)

        selected.append(
            (
                doc,
                chunk,
                score
            )
        )

        if len(selected) >= limit:
            break

    return selected


# ============================================================
# ANIQ JAVOBLAR
# ============================================================

def direct_answer(question):

    q = norm(question)

    # --------------------------------------------------------
    # 119-SON
    # --------------------------------------------------------

    if (
        "119" in q
        and any(
            word in q
            for word in [
                "qachon",
                "qabul",
                "sana",
                "nomi"
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

    # --------------------------------------------------------
    # 269-II QONUN SANASI
    # --------------------------------------------------------

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
            "269-II-son Qonun "
            "2001-yil 30-avgustda qabul qilingan.\n\n"

            "Qonun nomi:\n"
            "\"Madaniy meros obyektlarini muhofaza qilish "
            "va ulardan foydalanish to'g'risida\".\n\n"

            "Manba: 269-II-son Qonun, 30.08.2001."
        )

    # --------------------------------------------------------
    # TARIXIY-MADANIY EKSPERTIZA
    # --------------------------------------------------------

    if is_expertise_question(q):

        # Muddat + xulosa
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
                "Muddat ekspertiza yo'nalishi, ishning "
                "murakkabligi va hajmiga qarab belgilanadi.\n\n"

                "Ekspertiza xulosasi loyihasi "
                "Ilmiy-ekspert kengashi majlisida "
                "ko'rib chiqiladi. Kengash tomonidan "
                "ma'qullangan xulosa belgilangan "
                "tartibda rasmiylashtiriladi. "
                "Tegishli bayonnoma va xulosa "
                "Agentlikka yuboriladi.\n\n"

                "Manba: Vazirlar Mahkamasining "
                "2002-yil 29-iyuldagi 269-son qarori "
                "bilan tasdiqlangan Nizom, 15–19-bandlar."
            )

        # Umumiy tartib
        if "tartib" in q:

            return (
                "Tarixiy-madaniy ekspertiza O'zbekiston "
                "Respublikasi Madaniy meros agentligining "
                "Ilmiy-ekspert kengashi tomonidan o'tkaziladi.\n\n"

                "Ekspertiza materiallari Kengash kotibiga "
                "kiritiladi. Ekspertiza muddati "
                "30 kundan oshmasligi kerak.\n\n"

                "Ekspertiza xulosasi loyihasi Kengash "
                "majlisida ko'rib chiqiladi. Ma'qullangan "
                "xulosa belgilangan tartibda "
                "rasmiylashtiriladi va tegishli "
                "hujjatlar Agentlikka yuboriladi.\n\n"

                "Manba: Vazirlar Mahk
