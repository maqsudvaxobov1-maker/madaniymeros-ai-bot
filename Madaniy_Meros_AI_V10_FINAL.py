VERSION = "V10_FINAL"
import os
import re
import json
import logging
import threading
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ============================================================
# MADANIY MEROS AI — PROFESSIONAL / STRICT LEGAL MODE
# Version: V10_FINAL
# ============================================================

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
# BILIM BAZASI
# ------------------------------------------------------------

KB_NAMES = [
    "knowledge_base_full_v4.json",
    "knowledge_base_full_4.json",
    "knowledge_base_full_4(1).json",
    "knowledge_base_full_v3.json",
    "knowledge_base_v4.json",
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

    candidates = sorted(
        f for f in os.listdir(BASE_DIR)
        if f.lower().endswith(".json")
        and "knowledge" in f.lower()
    )
    if candidates:
        path = os.path.join(BASE_DIR, candidates[0])
        logging.info("Bilim bazasi avtomatik topildi: %s", candidates[0])
        return path

    raise RuntimeError("Knowledge base JSON topilmadi")

KB_FILE = find_kb()

# ------------------------------------------------------------
# NORMALIZATSIYA
# ------------------------------------------------------------

CYR_TO_LAT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
    "е": "e", "ё": "yo", "ж": "j", "з": "z", "и": "i",
    "й": "y", "к": "k", "қ": "q", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s",
    "т": "t", "у": "u", "ў": "o", "ф": "f", "х": "x",
    "ҳ": "h", "ц": "s", "ч": "ch", "ш": "sh", "ъ": "",
    "ь": "", "э": "e", "ю": "yu", "я": "ya"
})

def norm(text):
    text = str(text or "").lower().strip()
    text = text.translate(CYR_TO_LAT)
    text = (
        text.replace("ʻ", "")
        .replace("ʼ", "")
        .replace("’", "")
        .replace("‘", "")
        .replace("`", "")
        .replace("'", "")
    )
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()

# ------------------------------------------------------------
# HUJJATLARNI YUKLASH
# ------------------------------------------------------------

def load_kb():
    with open(KB_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    raw_docs = data.get("documents", data.get("docs", [])) if isinstance(data, dict) else data
    if not isinstance(raw_docs, list):
        raw_docs = []

    docs = []

    for item in raw_docs:
        if not isinstance(item, dict):
            continue

        title = str(item.get("title", "")).strip()
        number = str(item.get("document_number", "")).strip()
        date = str(item.get("date", "")).strip()
        source = str(item.get("source_file", "")).strip()
        text = str(item.get("text", item.get("content", ""))).strip()
        aliases = item.get("aliases", item.get("search_aliases", []))

        if not text:
            continue

        if not isinstance(aliases, list):
            aliases = []

        docs.append({
            "title": title,
            "number": number,
            "date": date,
            "source_file": source,
            "aliases": [str(x) for x in aliases],
            "text": text,
            "ntitle": norm(title),
            "nnumber": norm(number),
            "nsource": norm(source),
            "naliases": [norm(x) for x in aliases],
            "ntext": norm(text),
        })

    if not docs:
        raise RuntimeError("Knowledge base ichida hujjatlar topilmadi")

    logging.info("Knowledge base: %s ta hujjat", len(docs))
    return docs

DOCUMENTS = load_kb()

# V10 FINAL startup checks
if not any(d.get("nnumber") == "846" or "846" in d.get("ntitle", "") for d in DOCUMENTS):
    logging.warning("846-son qaror alohida KB hujjati sifatida topilmadi; full-list source alohida tekshiriladi.")

# ------------------------------------------------------------
# 846-SON QARORNING TO'LIQ MILLIY RO'YXATI
# Foydalanuvchi taqdim etgan 04.10.2019 hujjatidan olingan.
# ------------------------------------------------------------

def load_846_source():
    candidates = [
        os.path.join(BASE_DIR, "846_full.txt"),
        os.path.join(BASE_DIR, "846 04.10.2019.txt"),
        os.path.join(BASE_DIR, "national_list_846.txt"),
    ]
    for path in candidates:
        if path.exists() and path.stat().st_size > 100000:
            text = path.read_text(encoding="utf-8", errors="ignore")
            logging.info("846 milliy ro'yxat yuklandi: %s belgidan", len(text))
            return {
                "title": NATIONAL_LIST_SOURCE,
                "number": "846",
                "date": "04.10.2019",
                "source_file": path.name,
                "aliases": ["846-son", "846 qaror", "milliy ro'yxat", "moddiy madaniy meros milliy ro'yxati"],
                "text": text,
                "ntitle": norm(NATIONAL_LIST_SOURCE),
                "nnumber": "846",
                "nsource": norm(path.name),
                "naliases": [norm(x) for x in ["846-son", "846 qaror", "milliy ro'yxat", "moddiy madaniy meros milliy ro'yxati"]],
                "ntext": norm(text),
            }
    logging.warning("846 to'liq matni topilmadi")
    return None

_846_DOC = load_846_source()
if _846_DOC:
    DOCUMENTS.append(_846_DOC)

# ------------------------------------------------------------
# AMALDAGI ILMIY-EKSPERT KENGASHI QOIDALARI
# Muhim: bular 2002-yilgi 269-son Nizom bilan aralashtirilmaydi.
# ------------------------------------------------------------

CURRENT_COUNCIL_SOURCE = (
    "O‘zbekiston Respublikasi Madaniy meros agentligining "
    "Ilmiy-ekspert kengashi to‘g‘risida NIZOM"
)

CURRENT_COUNCIL_RULES = """
AMALDAGI ILMIY-EKSPERT KENGASHI NIZOMI — USTUVOR QOIDALAR:

1) Kengash yuridik shaxs emas va Madaniy meros agentligiga hisobot beradi.
2) Kengash tarkibiga tarix, me’morchilik va moddiy madaniy meros sohasida
   ilmiy-amaliy tajribaga ega 9–11 nafar olim va yuqori malakali mutaxassislar
   kiritiladi. Agentlik direktorining birinchi o‘rinbosari Kengash raisi.
3) Agentlik hududiy boshqarmalari huzurida Ilmiy-maslahat kengashlari tashkil etiladi.
4) Kengash mas’ul kotibi Kengash tarkibiga kirmaydi va ovoz berish vakolatiga ega emas.
5) Kengash yig‘ilishlari bir oyda kamida ikki marta o‘tkaziladi.
6) Yig‘ilish kamida 2/3 a’zo qatnashganda vakolatli hisoblanadi.
7) Qaror qatnashayotgan a’zolarning ko‘pchilik ovozi bilan qabul qilinadi.
   Ovozlar teng bo‘lsa, raislik qiluvchining ovozi hal qiluvchi.
   Betaraf qolish mumkin emas. Alohida fikr bildirish mumkin.
8) Kengash moddiy madaniy meros obyektlari va ularning qo‘riqlanadigan
   tegralarida yer qazish, yer tuzish, qurilish, melioratsiya va boshqa
   xo‘jalik ishlari, asrashga doir ishlar hamda ilmiy/ilmiy-texnik tadqiqot
   loyihalariga xulosa beradi.
9) Kengash loyihaoldi va loyiha-smeta hujjatlari bo‘yicha xulosa beradi.
10) Arizalar Agentlikning avtomatlashtirilgan axborot tizimi orqali beriladi.
11) Agentlik arizani 1 ish kuni ichida tegishli hududiy Ilmiy-maslahat
    kengashiga yuboradi.
12) Hududiy Ilmiy-maslahat kengashi ariza kelib tushganidan boshlab
    7 ish kuni ichida, qo‘shimcha o‘rganish zarur bo‘lsa 14 ish kunigacha,
    loyihaoldi va loyiha-smeta hujjatlari hamda obyektni joyiga chiqib o‘rganadi
    va xulosasini Kengashga yuboradi.
13) Kengash hududiy Ilmiy-maslahat kengashi xulosasi kelib tushganidan boshlab
    7 ish kuni ichida, qo‘shimcha o‘rganish zarur bo‘lsa 14 ish kunigacha,
    tegishli qaror qabul qiladi (xulosa beradi).
14) Kotib qaror qabul qilingandan boshlab 1 ish kuni ichida qarorni
    elektron axborot tizimi orqali yoki talabga ko‘ra qog‘oz shaklida yuboradi.
15) Kengash qaroridan norozi tomon 10 kun muddatda Agentlikka shikoyat qilishi mumkin.
16) To‘lovlar:
    - yer qazish, yer tuzish, qurilish, melioratsiya va boshqa tegishli loyiha:
      respublika toifasida 10 BHM, mahalliy toifada 5 BHM;
    - alohida muhofaza qilinadigan tarixiy-madaniy hududlar va YUNESKO
      hududlarida bino/inshoot qurish yoki buzish loyihalari:
      yuridik shaxs 20 BHM, jismoniy shaxs 1 BHM;
    - davlat kadastriga kiritish/chiqarish: BHMning 50 foizi;
    - tarixiy-madaniy ekspertiza: respublika toifasi 7 BHM,
      mahalliy toifasi 4 BHM;
    - aholi punktlari bosh rejasi loyihasi: 5 BHM.
    Agentlik va hududiy boshqarmalar tomonidan davlat mulki bo‘lgan moddiy
    madaniy meros obyektlarini kadastrga kiritish/chiqarish va ularni
    tarixiy-madaniy ekspertizadan o‘tkazish uchun taqdim etilgan loyihalar
    bo‘yicha to‘lov undirilmaydi.
17) To‘lov to‘liq to‘lanmasa, murojaatni ko‘rib chiqishni rad etish uchun asos bo‘ladi.
18) Kengash murojaatlarni arxiv ma’lumotlari, tarixiy manbalar, ilmiy adabiyotlar,
    UNESCO Umumjahon merosi markazi tavsiyalari/konvensiya talablari va
    an’anaviy me’morchilik maktablari xususiyatlari asosida ko‘rib chiqadi.
"""

OFFICIAL_SOURCES = [
    {
        "title": CURRENT_COUNCIL_SOURCE,
        "source_file": "https://gov.uz/oz/madaniymeros/sections/view/22396",
        "text": CURRENT_COUNCIL_RULES,
    },
    {
        "title": "846-son qarorning amaldagi o‘zgarishlari — 2026-yil 12-maydagi 239-son qaror",
        "source_file": "https://gov.uz/oz/madaniymeros/news/view/165219",
        "text": (
            "2026-yil 12-maydagi Vazirlar Mahkamasining 239-son qaroriga muvofiq "
            "2019-yil 4-oktabrdagi 846-son qarorga o‘zgartirish va qo‘shimchalar kiritilgan. "
            "Shuning uchun 846-sonning 2019-yilgi to‘liq ro‘yxat matni bilan birga "
            "keyingi o‘zgartirishlarni ham hisobga olish kerak."
        ),
    },
    {
        "title": "Madaniy meros agentligi — rasmiy sahifa",
        "source_file": "https://gov.uz/oz/madaniymeros/pages/about",
        "text": (
            "Madaniy meros agentligining rasmiy sahifasi. "
            "Agentlikning madaniy meros obyektlarini muhofaza qilish, "
            "saqlash va ulardan foydalanish bo‘yicha vakolatlari haqida rasmiy manba."
        ),
    },
]

# 846 bo‘yicha muhim himoya:
# KBda 846 qarorining to‘liq milliy ro‘yxati bo‘lmasa, bot aniq obyekt nomi
# yoki pozitsiyasini o‘ylab topmaydi.
NATIONAL_LIST_SOURCE = (
    "Vazirlar Mahkamasining 2019-yil 4-oktabrdagi 846-son qarori — "
    "“Moddiy madaniy merosning ko‘chmas mulk obyektlari milliy ro‘yxatini "
    "tasdiqlash to‘g‘risida”."
)

# ------------------------------------------------------------
# HUJJAT RAQAMINI ANIQLASH
# ------------------------------------------------------------

def detect_number(question):
    q = norm(question)

    if re.search(r"\b269\s*ii\b", q):
        return "269-II"

    m = re.search(r"\b(?:pq|pk)\s*[-–—]?\s*(\d+)\b", q)
    if m:
        return m.group(1)

    m = re.search(r"\b(?:vmq|vm)\s*[-–—]?\s*(\d+)\b", q)
    if m:
        return m.group(1)

    m = re.search(
        r"\b(\d{1,5})\s*(?:sonli|son|qaror|qonun|nizom)\b",
        q
    )
    if m:
        return m.group(1)

    m = re.search(r"\b(119|269|295|649|265|846|512|239)\b", q)
    return m.group(1) if m else None

# ------------------------------------------------------------
# MAVZU / NIYAT ANIQLASH
# ------------------------------------------------------------

TOPIC_ALIASES = {
    "ekspertiza": [
        "ekspertiza", "tarixiy madaniy ekspertiza",
        "tarixiy madaniy", "xulosa", "ekspert"
    ],
    "kengash": [
        "ilmiy ekspert kengashi", "kengash", "ilmiy maslahat",
        "ilmiy maslaxat", "seksiy", "kotib"
    ],
    "qurilish": [
        "qurilish", "rekonstruksiya", "qayta qurish",
        "buzish", "qurilish montaj", "obodonlashtirish",
        "loyiha smeta", "loyihaoldi"
    ],
    "muhofaza": [
        "muhofaza", "qo‘riqlanadigan tegra", "muhofaza tegrasi",
        "himoya hududi", "alohida muhofaza"
    ],
    "arxeologiya": [
        "arxeolog", "qazishma", "qazish", "arxeologik",
        "ochiq varaq", "ruxsatnoma", "arxeologik qidiruv"
    ],
    "muzey": [
        "muzey", "milliy muzey fondi", "muzey fondi",
        "davlat katalogi", "katalog"
    ],
    "kadastr": [
        "kadastr", "davlat kadastri", "kiritish", "chiqarish"
    ],
    "milliy_royxat": [
        "846", "milliy ro‘yxat", "milliy royxat",
        "milliy ruyxat", "obyekt ro‘yxati", "obyekt royxati"
    ],
    "tolov": [
        "to‘lov", "tolov", "yig‘im", "bhm", "qancha pul", "narxi"
    ],
    "muddat": [
        "muddat", "necha kun", "qancha kunda", "ish kuni"
    ],
}

def detect_topics(question):
    q = norm(question)
    topics = set()

    for topic, aliases in TOPIC_ALIASES.items():
        for alias in aliases:
            if norm(alias) in q:
                topics.add(topic)
                break

    return topics

# ------------------------------------------------------------
# QIDIRUV
# ------------------------------------------------------------

STOP_WORDS = {
    "va", "ham", "bu", "shu", "uchun", "bilan", "qanday", "qaysi",
    "nima", "qachon", "menga", "kerak", "bering", "ber", "haqida",
    "boyicha", "bo‘yicha", "siz", "men", "ning", "ni", "ga", "da",
    "dan", "mi", "mumkin", "uchun", "boladi", "bo‘ladi"
}

def keywords(question):
    words = re.findall(r"[a-z0-9]+", norm(question))
    return list(dict.fromkeys(
        w for w in words
        if len(w) >= 2 and w not in STOP_WORDS
    ))

def chunks(text, size=3500, overlap=450):
    if len(text) <= size:
        return [text]

    result = []
    start = 0

    while start < len(text):
        end = min(start + size, len(text))
        result.append(text[start:end])

        if end >= len(text):
            break

        start = end - overlap

    return result

def document_number_match(number, doc):
    if not number:
        return False

    n = norm(number)

    fields = [
        doc["nnumber"],
        doc["ntitle"],
        doc["nsource"],
        *doc["naliases"],
    ]

    if n == "269 ii":
        return any("269 ii" in x for x in fields)

    return any(re.search(rf"\b{re.escape(n)}\b", x) for x in fields)

def search_kb(question, limit=14):
    q = norm(question)
    keys = keywords(question)
    number = detect_number(question)
    topics = detect_topics(question)

    found = []

    all_docs = DOCUMENTS + [
        {
            "title": x["title"],
            "number": "",
            "date": "",
            "source_file": x["source_file"],
            "aliases": [],
            "text": x["text"],
            "ntitle": norm(x["title"]),
            "nnumber": "",
            "nsource": norm(x["source_file"]),
            "naliases": [],
            "ntext": norm(x["text"]),
        }
        for x in OFFICIAL_SOURCES
    ]

    for doc in all_docs:
        doc_bonus = 0

        if number and document_number_match(number, doc):
            doc_bonus += 140

        title_lower = doc["ntitle"]

        if "kengash" in topics and "ilmiy ekspert" in title_lower:
            doc_bonus += 80

        if "milliy_royxat" in topics and "846" in title_lower:
            doc_bonus += 120

        for chunk in chunks(doc["text"]):
            nchunk = norm(chunk)
            score = doc_bonus

            if len(q) >= 10 and q in nchunk:
                score += 100

            matched_keys = 0
            for key in keys:
                if key in nchunk:
                    score += 4
                    matched_keys += 1
                if key in title_lower:
                    score += 10
                if key in doc["nsource"]:
                    score += 8

            topic_words = {
                "ekspertiza": ["ekspert", "ekspertiza", "xulosa"],
                "kengash": ["kengash", "kotib", "yig‘ilish", "yigilish"],
                "qurilish": ["qurilish", "rekonstruksiya", "loyiha", "buzish"],
                "muhofaza": ["muhofaza", "qo‘riqlanadigan", "tegrasi"],
                "arxeologiya": ["arxeolog", "qazish", "ochiq varaq"],
                "muzey": ["muzey", "fond", "katalog"],
                "kadastr": ["kadastr"],
                "milliy_royxat": ["milliy ro‘yxat", "milliy royxat", "846"],
                "tolov": ["to‘lov", "tolov", "bhm"],
                "muddat": ["muddat", "ish kuni", "kun"],
            }

            for topic in topics:
                for word in topic_words.get(topic, []):
                    nw = norm(word)
                    if nw in nchunk:
                        score += 12

            if matched_keys == 0 and doc_bonus == 0:
                continue

            found.append({
                "score": score,
                "title": doc["title"],
                "source": doc["source_file"],
                "text": chunk,
            })

    found.sort(key=lambda x: x["score"], reverse=True)

    # Bir xil matnlarni olib tashlash
    unique = []
    seen = set()

    for item in found:
        key = (item["title"], item["text"][:500])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    return unique[:limit]


# ------------------------------------------------------------
# V10 FINAL — QAT'IY HUQUQIY HIMOYA
# ------------------------------------------------------------

LEGAL_NUMBER_ALIASES = {
    "846": ["846", "846-son", "846 son", "846 qaror"],
    "295": ["295", "295-son", "295 son", "295 qaror"],
    "119": ["119", "119-son", "119 son", "119 qaror"],
    "239": ["239", "239-son", "239 son", "239 qaror"],
    "269": ["269", "269-son", "269 son", "269 qaror"],
    "269-II": ["269-ii", "269 ii", "269 ii-son"],
}

def detect_dates(question):
    q = str(question or "")
    return re.findall(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b", q)

def is_846_question(question):
    q = norm(question)
    return (
        "846" in q
        or "milliy royxat" in q
        or "milliy ro‘yxat" in q
        or "milliy ruyxat" in q
    )

def is_specific_846_lookup(question):
    q = norm(question)
    location_words = [
        "samarqand", "buxoro", "andijon", "toshkent", "fargona",
        "namangan", "xorazm", "qashqadaryo", "surxondaryo", "jizzax",
        "sirdaryo", "navoiy", "qoraqalpogiston"
    ]
    object_words = [
        "obyekt", "obekt", "pozitsiya", "manzil", "qaysi", "nomi",
        "ro'yxatda", "royxatda", "ruyxatda"
    ]
    return any(x in q for x in location_words + object_words)

def build_strict_context(results):
    """Return only source-backed context, with explicit source labels."""
    blocks = []
    for i, item in enumerate(results, 1):
        blocks.append(
            f"[MANBA {i}]\n"
            f"Hujjat: {item.get('title', '')}\n"
            f"Manba: {item.get('source', '')}\n"
            f"Matn:\n{item.get('text', '')}"
        )
    return "\n\n====================\n\n".join(blocks)

def has_source_backed_number(results, number):
    if not number:
        return False
    n = norm(number)
    for r in results:
        blob = norm(
            f"{r.get('title','')} {r.get('source','')} {r.get('text','')}"
        )
        if n == "269 ii":
            if "269 ii" in blob:
                return True
        elif re.search(rf"\b{re.escape(n)}\b", blob):
            return True
    return False

# ------------------------------------------------------------
# ANIQLIKKA YO‘NALTIRILGAN MAXSUS JAVOBLAR
# ------------------------------------------------------------

def exact_answer(question):
    q = norm(question)
    topics = detect_topics(question)
    number = detect_number(question)

    # 269-II
    if number == "269-II" and any(x in q for x in ["qachon", "qabul", "sana"]):
        return (
            "269-II-son Qonun 2001-yil 30-avgustda qabul qilingan.\n\n"
            "Nomi: “Madaniy meros obyektlarini muhofaza qilish va ulardan "
            "foydalanish to‘g‘risida”gi Qonun.\n\n"
            "Manba: 269-II-son Qonun, 30.08.2001."
        )

    # 119
    if number == "119" and any(x in q for x in ["nomi", "qachon", "sana", "toliq"]):
        return (
            "Vazirlar Mahkamasining 2021-yil 3-martdagi 119-son qarori:\n"
            "“Moddiy madaniy meros obyektlari va YuNESKOning Umumjahon merosi "
            "ro‘yxatiga kiritilgan hududlar muhofazasini kuchaytirish "
            "chora-tadbirlari to‘g‘risida”.\n\n"
            "Manba: VMQ 119-son, 03.03.2021."
        )

    # 846 — to‘liq manba yuklangan bo‘lsa, aniq obyekt/pozitsiya bo‘yicha
    # javobni qidiruv kontekstiga qoldiramiz; manba yo‘q bo‘lsa taxmin qilmaymiz.
    if "846" in q or "milliy royxat" in q or "milliy ro‘yxat" in q:
        if _846_DOC is None and any(x in q for x in ["qaysi obyekt", "obyekt nomi", "pozitsiya", "samarqand", "buxoro", "andijon"]):
            return (
                "Bu savol 846-son qarorning Milliy ro‘yxatidagi aniq obyekt yoki pozitsiyani talab qiladi.\n\n"
                "846-son qarorning to‘liq ro‘yxat matni ushbu ishchi bilim bazasida mavjud emas,\n"
                "shu sababli aniq obyekt nomi yoki pozitsiyasini taxmin qilib bermayman.\n\n"
                "Manba: Vazirlar Mahkamasining 2019-yil 4-oktabrdagi 846-son qarori — "
                "“Moddiy madaniy merosнинг ko‘chmas mulk obyektlari milliy ro‘yxatini tasdiqlash to‘g‘risida”."
            )

    # Hozirgi Kengash — aniq faktlar
    if "kengash" in topics:
        if "shikoyat" in q or "noroz" in q:
            return (
                "Ilmiy-ekspert kengashi qaroridan norozi bo‘lgan tomon "
                "10 kun muddatda Madaniy meros agentligiga shikoyat qilishi mumkin.\n\n"
                f"Manba: {CURRENT_COUNCIL_SOURCE}, 34-band."
            )

        if "necha marta" in q or "oyda" in q or "yigilish" in q or "yig‘ilish" in q:
            return (
                "Ilmiy-ekspert kengashi yig‘ilishlari bir oyda kamida "
                "ikki marta o‘tkaziladi.\n\n"
                f"Manba: {CURRENT_COUNCIL_SOURCE}, 19-band."
            )

        if "tarkib" in q or "nechta" in q or "a'z" in q or "azo" in q:
            return (
                "Kengash tarkibiga 9–11 nafar olim va yuqori malakali "
                "mutaxassislar kiritiladi.\n\n"
                f"Manba: {CURRENT_COUNCIL_SOURCE}, 8-band."
            )

        if "muddat" in q or "necha kun" in q or "ish kuni" in q:
            return (
                "Amaldagi tartib bo‘yicha:\n"
                "• Agentlik arizani 1 ish kuni ichida hududiy Ilmiy-maslahat kengashiga yuboradi;\n"
                "• hududiy Ilmiy-maslahat kengashi — 7 ish kuni, qo‘shimcha "
                "o‘rganish zarur bo‘lsa 14 ish kunigacha;\n"
                "• asosiy Ilmiy-ekspert kengashi — hududiy xulosa kelganidan "
                "keyin 7 ish kuni, qo‘shimcha o‘rganish zarur bo‘lsa 14 ish kunigacha;\n"
                "• qaror qabul qilingach, kotib uni 1 ish kuni ichida yuboradi.\n\n"
                f"Manba: {CURRENT_COUNCIL_SOURCE}, 41–45-bandlar."
            )

        if "tolov" in q or "bhm" in q or "yigim" in q or "yig‘im" in q:
            return (
                "Amaldagi Nizomdagi asosiy to‘lovlar:\n"
                "• yer qazish, yer tuzish, qurilish, melioratsiya va boshqa "
                "tegishli loyihalar: respublika toifasi — 10 BHM, mahalliy "
                "toifa — 5 BHM;\n"
                "• alohida muhofaza qilinadigan tarixiy-madaniy hududlar va "
                "YUNESKO hududlarida bino/inshoot qurish yoki buzish loyihalari: "
                "yuridik shaxs — 20 BHM, jismoniy shaxs — 1 BHM;\n"
                "• tarixiy-madaniy ekspertiza: respublika toifasi — 7 BHM, "
                "mahalliy toifasi — 4 BHM;\n"
                "• davlat kadastriga kiritish/chiqarish — BHMning 50 foizi;\n"
                "• bosh reja loyihasi — 5 BHM.\n\n"
                f"Manba: {CURRENT_COUNCIL_SOURCE}, 39-band."
            )

    # Tarixiy-madaniy ekspertiza — 269-son Nizom
    if "ekspertiza" in topics:
        if "muddat" in q or "necha kun" in q:
            return (
                "Tarixiy-madaniy ekspertiza o‘tkazish muddati "
                "30 kundan oshmasligi kerak.\n\n"
                "Manba: Vazirlar Mahkamasining 2002-yil 29-iyuldagi "
                "269-son qarori bilan tasdiqlangan Nizom, 18-band."
            )

    return None

# ------------------------------------------------------------
# OPENAI — QAT’IY HUQUQIY PROMPT
# ------------------------------------------------------------

def build_system_prompt():
    return f"""
Siz “Madaniy Meros AI” nomli O‘zbekiston madaniy merosi bo‘yicha
huquqiy-amaliy yordamchisiz.

ASOSIY MAQSAD:
Foydalanuvchiga aniq, tekshiriladigan, amaldagi huquqiy manbaga bog‘langan
javob berish. Hech qachon hujjat raqami, sana, band, to‘lov, muddat yoki
vakolatni o‘ylab topmang.

MANBA USTUVORLIGI:
1. Foydalanuvchi bilim bazasidagi hujjatning aniq matni.
2. Amaldagi Ilmiy-ekspert kengashi Nizomi bo‘yicha quyida berilgan
   aniq qoidalar.
3. Agar kerakli norma bilim bazasida bo‘lmasa, buni ochiq ayting.
   Umumiy huquqiy bilimdan aniq norma yasamang.

MUHIM AJRATISH:
- 269-II — QONUN, 30.08.2001.
- 269-son — VAZIRLAR MAHKAMASINING 29.07.2002-yildagi qarori.
- 269-sonning tegishli ilovasidagi tarixiy-madaniy ekspertiza Nizomi
  bilan AMALDAGI Ilmiy-ekspert kengashi Nizomini aralashtirmang.
- 295-son hamda boshqa Vazirlar Mahkamasi qarorlarini Prezident qarori
  deb yozmang.
- 846-son — 04.10.2019-yildagi Vazirlar Mahkamasi qarori.
- 846-sonning to‘liq milliy ro‘yxati alohida manba sifatida yuklangan bo‘lsa,
  obyekt nomi, tartib raqami, toifasi, davri, manzili va mulk huquqi bo‘yicha
  aynan manba matnidan foydalaning.
- 846-sonning 2026-yil 12-maydagi 239-son qaror bilan o‘zgartirilganini ham hisobga oling.
- Agar kerakli obyekt/pozitsiya manbada topilmasa, uni taxmin qilmang.

AMALDAGI KENGASH QOIDALARI:
{CURRENT_COUNCIL_RULES}

JAVOB BERISH QOIDALARI:
1. Avval qisqa va aniq xulosa.
2. Keyin, kerak bo‘lsa, amaliy bosqichlar.
3. Keyin aniq muddat/to‘lov.
4. Oxirida manba: hujjat nomi, sana, band.
5. Agar ikki hujjat bir-biridan farq qilsa, ikkalasining rolini alohida tushuntiring.
6. “Aniq” deb faqat manba qo‘llab-quvvatlagan ma’lumotni ayting.
7. “Odatda”, “amaliyotda” kabi so‘zlar bilan huquqiy normani almashtirmang.
8. To‘lovda BHM miqdorini so‘ralsa, BHMning nechta baravari ekanini ayting.
   Joriy BHM qiymati kontekstda bo‘lmasa, so‘mda aniq summa o‘ylab topmang.
9. 30 kunlik ekspertiza muddatini Kengashning 7/14 ish kunlik ko‘rib
   chiqish muddatlari bilan aralashtirmang.
10. Hududiy Ilmiy-maslahat kengashi va asosiy Ilmiy-ekspert kengashi
    alohida bosqich ekanini saqlang.
11. “Arxeologiya kengashi” degan alohida organ bor deb aytmang.
    Arxeologiya yo‘nalishi va Ilmiy-ekspert kengashini farqlang.
12. Manbada norma yetarli bo‘lmasa:
    “Taqdim etilgan bilim bazasida bu savolga yetarli aniq ma’lumot
     topilmadi” deb ayting va qaysi ma’lumot yetishmasligini ko‘rsating.
"""

def ask_openai(question, context):
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": build_system_prompt()},
            {
                "role": "user",
                "content": (
                    "SAVOL:\n" + question +
                    "\n\nISHONCHLI KONTEKST:\n" + context[:36000]
                )
            }
        ],
        "temperature": 0.1,
    }

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + OPENAI_API_KEY
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            result = json.loads(response.read().decode("utf-8"))

        content = result["choices"][0]["message"]["content"].strip()
        return content

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        logging.error("OpenAI HTTP %s: %s", e.code, body[:1500])

        if e.code == 401:
            return "OpenAI API kaliti noto‘g‘ri yoki eskirgan."
        if e.code == 429:
            return "OpenAI API limiti yoki hisob holati bo‘yicha vaqtinchalik xatolik yuz berdi."
        return f"OpenAI API xatosi: {e.code}"

    except Exception:
        logging.exception("OpenAI xatosi")
        return "Javobni shakllantirishda texnik xatolik yuz berdi."

# ------------------------------------------------------------
# JAVOBNI YIG‘ISH
# ------------------------------------------------------------

def answer_question(question):
    # 1. Exact, source-backed answers first.
    exact = exact_answer(question)
    if exact:
        return exact

    number = detect_number(question)
    topics = detect_topics(question)
    results = search_kb(question, limit=18)

    # 2. 846-specific protection: never infer an object/position without
    #    the actual full national-list source.
    if is_846_question(question) and is_specific_846_lookup(question):
        has_full_list = any(
            (
                "846" in norm(r.get("title", ""))
                and len(r.get("text", "")) > 5000
            )
            for r in results
        )
        if not has_full_list and _846_DOC is None:
            return (
                "846-son qarorning milliy ro‘yxatidagi aniq obyektni "
                "tasdiqlash uchun 846-son qarorning to‘liq ro‘yxat matni "
                "kerak. Ishchi bilim bazasida to‘liq ro‘yxat aniqlanmagani "
                "sababli obyekt nomi yoki pozitsiyasini taxmin qilmayman.\n\n"
                f"Manba: {NATIONAL_LIST_SOURCE}"
            )

    # 3. If a user explicitly names a document number but the retrieved
    #    context does not actually contain that number, do not let the LLM
    #    manufacture a citation.
    if number and not has_source_backed_number(results, number):
        return (
            f"Саволда {number}-сон ҳужжат кўрсатилган, аммо тақдим этилган "
            f"билим базасида шу рақамга тегишли тасдиқланган матн топилмади. "
            f"Шу сабабли ҳужжатнинг мазмуни ёки бандини тахмин қилиб бермайман."
        )

    if not results:
        return (
            "Тақдим этилган билим базасида бу саволга етарли аниқ "
            "маълумот топилмади. Аниқ ҳуқуқий хулоса бериш учун "
            "тегишли норматив ҳужжат ёки унинг банди керак."
        )

    context = build_strict_context(results)

    # 4. Stronger system instruction appended at runtime.
    strict_suffix = """
V10 FINAL QAT'IY NAZORAT:
- Javobni faqat ISHONCHLI KONTEKSTdagi matn bilan asosla.
- Kontekstda yo‘q raqam, sana, band, to‘lov, muddat yoki vakolatni yaratma.
- Agar savol 846-son milliy ro‘yxatdagi aniq obyektni so‘rasa,
  faqat ro‘yxat matnida aynan tasdiqlangan obyektni ayt.
- 846-son ro‘yxatda topilmagan obyektni "madaniy meros emas" deb xulosa qilma.
- 295-son, 119-son, 269-son va 269-II-son hujjatlarini bir-biridan ajrat.
- Ilmiy-ekspert kengashi bilan tarixiy-madaniy ekspertiza Nizomini aralashtirma.
- Agar manba yetarli bo‘lmasa, buni ochiq ayt va qaysi ma'lumot yetishmasligini ko‘rsat.
"""
    context = context + "\n\n" + strict_suffix

    return ask_openai(question, context)

# ------------------------------------------------------------
# TELEGRAM
# ------------------------------------------------------------

def telegram_api(method, payload):
    url = "https://api.telegram.org/bot" + BOT_TOKEN + "/" + method

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=40) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        logging.exception("Telegram API xatosi")
        return {"ok": False}

def setup_webhook():
    if not RENDER_EXTERNAL_URL:
        logging.warning("RENDER_EXTERNAL_URL topilmadi")
        return

    result = telegram_api(
        "setWebhook",
        {
            "url": WEBHOOK_URL,
            "drop_pending_updates": False
        }
    )

    logging.info("Webhook: %s", result)

def split_message(text):
    if len(text) <= MAX_MESSAGE_LENGTH:
        return [text]

    parts = []

    while len(text) > MAX_MESSAGE_LENGTH:
        cut = text.rfind("\n", 0, MAX_MESSAGE_LENGTH)

        if cut < 500:
            cut = text.rfind(" ", 0, MAX_MESSAGE_LENGTH)

        if cut < 500:
            cut = MAX_MESSAGE_LENGTH

        parts.append(text[:cut].strip())
        text = text[cut:].strip()

    if text:
        parts.append(text)

    return parts

def send_message(chat_id, text):
    for part in split_message(text):
        telegram_api(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": part
            }
        )

def process_update(update):
    message = update.get("message")

    if not isinstance(message, dict):
        return

    chat_id = message.get("chat", {}).get("id")
    text = str(message.get("text", "")).strip()

    if not chat_id or not text:
        return

    logging.info("Savol: %s", text[:500])

    if text.lower().startswith("/start"):
        send_message(
            chat_id,
            "Assalomu alaykum!\n\n"
            "Men Madaniy Meros AI botiman.\n"
            "Madaniy meros, tarixiy-madaniy ekspertiza, "
            "Ilmiy-ekspert kengashi, qurilish, restavratsiya, "
            "arxeologiya, muzey va tegishli hujjatlar bo‘yicha savolingizni yozing."
        )
        return

    if text.lower().startswith("/help"):
        send_message(
            chat_id,
            "Savol namunalari:\n"
            "• 269-II-son Qonun qachon qabul qilingan?\n"
            "• 269-son qaror nimani tartibga soladi?\n"
            "• Tarixiy-madaniy ekspertiza muddati qancha?\n"
            "• Ilmiy-ekspert kengashi qanday muddatda qaror qiladi?\n"
            "• Qurilish loyihasi uchun Kengash ko‘rib chiqish tartibi qanday?\n"
            "• Kengashga shikoyat qilish muddati qancha?\n"
            "• 846-son qaror bo‘yicha milliy ro‘yxat nima?"
        )
        return

    try:
        answer = answer_question(text)
        send_message(chat_id, answer)

    except Exception:
        logging.exception("Savolni qayta ishlash xatosi")
        send_message(
            chat_id,
            "Kechirasiz, texnik xatolik yuz berdi."
        )

# ------------------------------------------------------------
# WEBHOOK SERVER
# ------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        return

    def do_GET(self):
        if self.path in ["/", "/health"]:
            body = (
                "Madaniy Meros AI ishlayapti."
                if self.path == "/"
                else "OK"
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
                self.headers.get("Content-Length", "0")
            )

            raw = self.rfile.read(length)
            update = json.loads(raw.decode("utf-8"))

            self.send_response(200)
            self.send_header(
                "Content-Type",
                "text/plain"
            )
            self.end_headers()
            self.wfile.write(b"OK")

            threading.Thread(
                target=process_update,
                args=(update,),
                daemon=True
            ).start()

        except Exception:
            logging.exception("Webhook xatosi")
            try:
                self.send_response(200)
                self.end_headers()
            except Exception:
                pass

# ------------------------------------------------------------
# START
# ------------------------------------------------------------

def main():
    logging.info("========================================")
    logging.info("MADANIY MEROS AI V10_FINAL BOSHLANDI")
    logging.info("KB: %s", KB_FILE)
    logging.info("Documents: %s", len(DOCUMENTS))
    logging.info("Model: %s", OPENAI_MODEL)
    logging.info("Port: %s", PORT)
    logging.info("Webhook: %s", WEBHOOK_URL)
    logging.info("========================================")

    setup_webhook()

    server = ThreadingHTTPServer(
        ("0.0.0.0", PORT),
        Handler
    )

    server.serve_forever()

if __name__ == "__main__":
    main()
