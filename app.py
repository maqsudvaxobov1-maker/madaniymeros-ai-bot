import os
import re
import json
import logging
import threading
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

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

KB_NAMES = [
    "knowledge_base_full_4.json",
    "knowledge_base_full_v3.json",
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
        if f.lower().endswith(".json") and "knowledge" in f.lower()
    )
    if candidates:
        path = os.path.join(BASE_DIR, candidates[0])
        logging.info("Bilim bazasi avtomatik topildi: %s", candidates[0])
        return path
    raise RuntimeError("knowledge_base JSON fayli topilmadi")


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
    text = text.replace("ʻ", "").replace("ʼ", "").replace("’", "").replace("‘", "").replace("'", "")
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load_kb():
    with open(KB_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    docs = data.get("documents", []) if isinstance(data, dict) else data
    if not isinstance(docs, list) or not docs:
        raise RuntimeError("Bilim bazasida documents topilmadi")
    logging.info("%s ta hujjat yuklandi", len(docs))
    return docs


DOCUMENTS = load_kb()

# Official Madaniy meros Agentligi pages used as a supplemental source.
# If an official page is temporarily unavailable, the local knowledge base
# remains fully usable.
OFFICIAL_SOURCE_URLS = [
    ("Agentlikning vazifalari", "https://gov.uz/oz/madaniymeros/pages/about"),
    ("Ilmiy-ekspert kengashi Nizomi", "https://gov.uz/oz/madaniymeros/sections/view/22396"),
]

def _html_to_text(html):
    html = re.sub(r"<(script|style|noscript).*?</\\1>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<br\\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"</(p|div|li|h[1-6]|tr|section|article)>", "\n", html, flags=re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    html = html.replace("&nbsp;", " ").replace("&amp;", "&")
    html = re.sub(r"\\s+", " ", html)
    return html.strip()

def load_official_sources():
    extra = []
    for title, url in OFFICIAL_SOURCE_URLS:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "MadaniyMerosAI/1.0"}
            )
            with urllib.request.urlopen(req, timeout=20) as response:
                raw = response.read().decode("utf-8", errors="ignore")
            text = _html_to_text(raw)
            if len(text) >= 500:
                extra.append({
                    "title": title,
                    "document_number": "",
                    "date": "",
                    "source_file": url,
                    "text": text,
                    "sections": [{
                        "section_id": 0,
                        "label": title,
                        "search_key": norm(title),
                        "text": text,
                        "text_normalized": norm(text),
                    }],
                })
                logging.info("Rasmiy manba yuklandi: %s", title)
        except Exception as exc:
            logging.warning("Rasmiy manba yuklanmadi: %s | %s", title, exc)
    return extra

DOCUMENTS.extend(load_official_sources())
logging.info("Jami manbalar: %s ta", len(DOCUMENTS))

STOP = {
    "va","ham","bu","shu","uchun","bilan","qanday","qaysi","nima","qachon",
    "menga","kerak","bering","ber","haqida","boyicha","bo‘yicha","siz","men",
    "ning","ni","ga","da","dan","mi","mumkin","edi","ekan","boladi","boladi"
}

TOPICS = {
    "ekspertiza": ["ekspertiza", "ekspert", "tarixiy madaniy", "xulosa", "kengash", "metodika"],
    "qurilish": ["qurilish", "qurilish montaj", "shaharsozlik", "rekonstruksiya", "bino", "inshoot"],
    "ruxsat": ["ruxsat", "ruxsatnoma", "kelishuv", "kelishish", "ijozat", "tasdiq"],
    "muhofaza": ["muhofaza", "qoriqlanadigan", "tegrasi", "himoya", "saqlash", "asrash"],
    "restavratsiya": ["restavratsiya", "tamirlash", "konservatsiya", "tiklash"],
    "xizmat": ["davlat xizmati", "xizmat", "tolov", "yigim", "boj", "tarif", "haq"],
    "arxeologiya": ["arxeolog", "arxeologiya", "qazishma", "qidiruv", "ochiq varaq", "ruxsatnoma", "ilmiy tadqiqot", "arxeologiya ashyosi", "davlat katalogi"],
    "muzey": ["muzey", "muzey ashyosi", "muzey kolleksiyasi", "milliy muzey fondi", "davlat katalogi", "ekspozitsiya", "muzeylashtirish"],
    "kadastr": ["kadastr", "royxat", "milliy royxat", "toifa", "hisob"],
}


def requested_number(question):
    q = norm(question)
    if re.search(r"\b269\s*ii\b", q):
        return "269-II"
    patterns = [
        r"\b(?:vmq|vazirlar mahkamasi)\s*-?\s*(\d{2,5})\b",
        r"\b(?:pq|pf)\s*-?\s*(\d{2,5})\b",
        r"\b(\d{2,5})\s*-?\s*sonli?\b",
        r"\b(\d{2,5})\s*-?\s*qaror\b",
    ]
    for p in patterns:
        m = re.search(p, q)
        if m:
            return m.group(1)
    return None


def doc_number(doc):
    raw = " ".join(str(doc.get(k, "")) for k in ("title", "document_number", "canonical_document_number", "source_file"))
    n = norm(raw)
    if re.search(r"269\s*ii", n):
        return "269-II"
    m = re.search(r"\b(119|177|265|269|295|649|5150)\b", n)
    return m.group(1) if m else ""


def topics_for(question):
    q = norm(question)
    found = []
    for topic, aliases in TOPICS.items():
        if any(norm(a) in q for a in aliases):
            found.append(topic)
    return found


def section_items(doc):
    sections = doc.get("sections") or []
    if sections:
        out = []
        for i, sec in enumerate(sections):
            if not isinstance(sec, dict):
                continue
            text = str(sec.get("text", "")).strip()
            label = str(sec.get("label", sec.get("search_key", ""))).strip()
            if text:
                out.append({"index": i, "id": sec.get("section_id", i), "label": label, "text": text})
        if out:
            return out
    text = str(doc.get("text", "")).strip()
    return [{"index": 0, "id": 0, "label": doc.get("title", ""), "text": text}] if text else []


def doc_priority(doc, topics, number):
    n = doc_number(doc)
    title = norm(str(doc.get("title", "")))
    score = 0
    if number and n == number:
        score += 300
    if "ekspertiza" in topics and n == "269":
        score += 180
    if any(x in topics for x in ("qurilish", "ruxsat", "muhofaza", "restavratsiya")) and n == "265":
        score += 90
    if "xizmat" in topics and n in ("295", "119"):
        score += 90
    if "arxeologiya" in topics and n in ("269-II", "5150", "295"):
        score += 60
    if "muzey" in topics and n in ("119", "295", "649", "261"):
        score += 75
    if "ekspertiza" in title:
        score += 40
    return score


def search_kb(question, limit=18):
    """
    Manbaga yo'naltirilgan qidiruv.
    Maxsus mavzularda hujjatning barcha asosiy tegishli bandlarini
    bir paket qilib qaytaradi. Oddiy savollarda esa reytingli qidiruv ishlaydi.
    """
    q = norm(question)
    topics = topics_for(question)
    number = requested_number(question)

    # --------------------------------------------------------
    # 1. TARIXIY-MADANIY EKSPERTIZA:
    # VMQ 269-son Nizomining asosiy bandlari + amaliy sxema
    # to'liq kontekstga beriladi.
    # --------------------------------------------------------
    if "ekspertiza" in topics and not number:
        results = []

        for doc in DOCUMENTS:
            if doc_number(doc) != "269":
                continue

            sections = section_items(doc)

            # Nizomning maqsadi, tartibi, Kengash, xulosa,
            # muddat va yig'im bandlari.
            # section_id 7..25 — Nizomning asosiy qismi,
            # 26..31 — ekspertizani o'tkazish amaliy sxemasi.
            wanted = [
                s for s in sections
                if (
                    isinstance(s.get("id"), int)
                    and 7 <= s["id"] <= 31
                )
            ]

            for sec in wanted:
                results.append({
                    "score": 1000 - sec["id"],
                    "doc": doc,
                    "section": sec,
                })

            break

        if results:
            return results

    # --------------------------------------------------------
    # 2. SOHA BO'YICHA KENG QAMROVLI QIDIRUV
    # Arxeologiya va muzey savollarida bir nechta hujjatdagi
    # tegishli bandlarni birgalikda ko'rib chiqish.
    # --------------------------------------------------------
    if any(t in topics for t in ("arxeologiya", "muzey")) and not number:
        broad = []
        words = [w for w in q.split() if len(w) >= 3 and w not in STOP]
        for doc in DOCUMENTS:
            for sec in section_items(doc):
                nt = norm(sec["text"])
                nl = norm(sec["label"])
                score = doc_priority(doc, topics, number)
                score += sum(8 for w in words if w in nt)
                score += sum(14 for w in words if w in nl)
                for topic in topics:
                    score += sum(
                        22 for alias in TOPICS[topic]
                        if norm(alias) in nt
                    )
                if score > 0:
                    broad.append({"score": score, "doc": doc, "section": sec})

        broad.sort(key=lambda x: x["score"], reverse=True)

        # Keep several documents represented, while allowing the strongest
        # sections to dominate.
        result = []
        per_doc = {}
        for item in broad:
            key = id(item["doc"])
            per_doc.setdefault(key, 0)
            if per_doc[key] >= 5:
                continue
            result.append(item)
            per_doc[key] += 1
            if len(result) >= 24:
                break
        if result:
            return result

    # --------------------------------------------------------
    # 2. ANIQ HUJJAT RAQAMI:
    # Shu hujjatning savolga mos barcha kuchli bandlari olinadi.
    # --------------------------------------------------------
    scored = []

    words = [
        w for w in q.split()
        if len(w) >= 3 and w not in STOP
    ]

    for doc in DOCUMENTS:

        dscore = doc_priority(
            doc,
            topics,
            number
        )

        sections = section_items(doc)

        for sec in sections:

            nt = norm(sec["text"])
            nl = norm(sec["label"])

            score = dscore

            matches = sum(
                1 for w in words
                if w in nt
            )

            score += matches * 7

            score += sum(
                1 for w in words
                if w in nl
            ) * 12

            if (
                len(q) >= 12
                and q in nt
            ):
                score += 180

            for topic in topics:

                if any(
                    norm(alias) in nt
                    for alias in TOPICS[topic]
                ):
                    score += 18

            if (
                number
                and doc_number(doc) == number
            ):
                score += 80

            if (
                "ekspertiza" in topics
                and doc_number(doc) == "269"
                and any(
                    x in nt
                    for x in (
                        "ilmiy ekspert kengashi",
                        "ekspert xulosasi",
                        "30 kun",
                        "maxsus yigim",
                        "mustaqil ekspert",
                        "kengash kotibi"
                    )
                )
            ):
                score += 35

            if score > 0:

                scored.append({
                    "score": score,
                    "doc": doc,
                    "section": sec,
                })

    if not scored:
        return []

    # --------------------------------------------------------
    # 3. Har bir hujjatdan eng kuchli bandlarni va qo'shnilarini olish.
    # --------------------------------------------------------
    by_doc = {}

    for item in scored:

        key = id(item["doc"])

        by_doc.setdefault(
            key,
            []
        ).append(item)

    selected = []
    seen = set()

    for items in by_doc.values():

        items.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        strong = items[:8]

        indices = {
            x["section"]["index"]
            for x in strong
        }

        all_sections = section_items(
            items[0]["doc"]
        )

        lookup = {
            s["index"]: s
            for s in all_sections
        }

        for idx in indices:

            base_score = next(
                (
                    x["score"]
                    for x in items
                    if x["section"]["index"] == idx
                ),
                0
            )

            # Qo'shni bandlar kontekst uzilib qolmasligi uchun.
            for near in (
                idx - 1,
                idx,
                idx + 1
            ):

                if near not in lookup:
                    continue

                sec = lookup[near]

                key = (
                    doc_number(items[0]["doc"]),
                    sec["id"]
                )

                if key in seen:
                    continue

                seen.add(key)

                selected.append({
                    "score": (
                        base_score
                        if near == idx
                        else base_score - 8
                    ),
                    "doc": items[0]["doc"],
                    "section": sec,
                })

    selected.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    # Ustuvor hujjat bandlari doimo saqlanadi.
    priority = [
        x for x in selected
        if doc_priority(
            x["doc"],
            topics,
            number
        ) > 0
    ]

    other = [
        x for x in selected
        if doc_priority(
            x["doc"],
            topics,
            number
        ) == 0
    ]

    # limit kichik berilgan taqdirda ham kamida 18 tagacha
    # mazmunli bandni yo'qotmaslik.
    wanted_limit = max(
        int(limit or 0),
        18
    )

    final = (
        priority[:14]
        + other[:max(
            0,
            wanted_limit - min(
                14,
                len(priority)
            )
        )]
    )

    result = []
    seen_text = set()

    for item in final:

        key = norm(
            item["section"]["text"]
        )[:700]

        if key in seen_text:
            continue

        seen_text.add(key)
        result.append(item)

        if len(result) >= wanted_limit:
            break

    return result


def build_context(results, max_chars=36000):
    blocks = []
    total = 0
    for i, x in enumerate(results, 1):
        doc = x["doc"]
        sec = x["section"]
        block = (
            f"[{i}] Hujjat: {doc.get('title','')}\n"
            f"Raqam: {doc.get('document_number', doc_number(doc))}\n"
            f"Sana: {doc.get('date','')}\n"
            f"Manba: {doc.get('source_file','')}\n"
            f"Band/bo'lim: {sec.get('label','')}\n"
            f"Matn:\n{sec.get('text','')}"
        )
        if total + len(block) > max_chars:
            continue
        blocks.append(block)
        total += len(block)
    return "\n\n==============================\n\n".join(blocks)


def direct_answer(question):
    q = norm(question)
    if "269 ii" in q and any(x in q for x in ("qachon", "qabul", "sana")):
        return (
            "269-II-son Qonun 2001-yil 30-avgustda qabul qilingan.\n\n"
            "Nomi: “Madaniy meros obyektlarini muhofaza qilish va ulardan foydalanish to‘g‘risida”gi Qonun.\n\n"
            "Manba: 269-II-son Qonun, 30.08.2001."
        )
    if re.search(r"\b119\b", q) and any(x in q for x in ("qaror", "vmq", "son", "nomi", "qachon")):
        return (
            "119-son Vazirlar Mahkamasi qarori 2021-yil 3-martda qabul qilingan.\n\n"
            "To‘liq nomi: “Moddiy madaniy meros obyektlari va YuNESKOning Umumjahon merosi ro‘yxatiga kiritilgan hududlar muhofazasini kuchaytirish chora-tadbirlari to‘g‘risida”.\n\n"
            "Manba: O‘zbekiston Respublikasi Vazirlar Mahkamasining 2021-yil 3-martdagi 119-son qarori."
        )
    return None


def openai_answer(question, results):
    context = build_context(results)
    system = (
        "Siz Madaniy Meros AI — O‘zbekiston madaniy merosi bo‘yicha manbaga asoslangan huquqiy yordamchisiz.\\n\n"
        "ASOSIY QOIDA: faqat kontekstda berilgan hujjatlar va rasmiy manbalarga tayaning. "
        "Manbada yo‘q fakt, band, muddat, to‘lov, vakolat, hujjatlar ro‘yxati yoki protsedurani ixtiro qilmang.\n"
        "Savol bir nechta masalani qamrasa, har bir masalani alohida ajrating va tegishli hujjatlarni birlashtiring. "
        "Bir hujjatdagi norma boshqa hujjatdagi norma bilan almashtirilmasin.\n"
        "ILMIY-EKSPERT KENGASHI: bu alohida organ. Uni 'Arxeologiya kengashi' deb atamang. "
        "Arxeologiya — alohida soha; Ilmiy-ekspert kengashi esa madaniy meros masalalarini ko‘rib chiquvchi kengash.\n"
        "269-son Nizom bo‘yicha 1–19-bandlarni Nizomning asosiy bandlari sifatida, "
        "unga ilova qilingan sxemaning 1–6-bandlarini esa alohida amaliy bosqichlar sifatida ko‘rsating. "
        "Sxema 6-bandini Nizomning 6-bandi deb yozmang.\n"
        "Agar 269-son Nizom 18-bandi kontekstda mavjud bo‘lsa, uning aniq mazmunini aynan bering: "
        "tarixiy-madaniy ekspertizani o‘tkazish muddati materiallarning yo‘nalishi, murakkabligi va hajmiga qarab "
        "o‘ttiz kundan oshmasligi kerak. 'Manbada muddat ko‘rsatilmagan' deb yozmang.\n"
        "269-son Nizom 19-bandida maxsus yig‘im mavjudligi ko‘rsatilgan bo‘lsa, uni aniq ayting. "
        "Lekin aniq summa kontekstda bo‘lmasa, summani o‘ylab topmang; summa qaysi hujjat/jadvaldan olinishi kerakligini ayting.\n"
        "Muzey savollarida muzeylar, Milliy muzey fondi, muzey ashyolari va kolleksiyalari, Davlat katalogi, "
        "hisobga olish, saqlash, restavratsiya, davlat xizmatlari va to‘lovlarga oid barcha mos manbalarni birlashtiring.\n"
        "Arxeologiya savollarida arxeologik qidiruv, qazishma, ochiq varaq/ruxsatnoma, ilmiy tadqiqot, "
        "hisobot, arxeologiya ashyolari, Davlat katalogi va muzeylashtirishga oid mos manbalarni birlashtiring.\n"
        "Kengash bo‘yicha savollarda materialning kiritilishi, kotib, rais, yo‘nalishlar bo‘yicha seksiyalar, "
        "ekspert xulosasi, xulosa loyihasi, majlis, ovoz berish, alohida fikr, bayonnoma, Agentlikka yuborish, "
        "shikoyat va murojaatlarni ko‘rib chiqish muddatlarini faqat manbada qanday berilgan bo‘lsa shunday tushuntiring.\n"
        "Agar amaldagi rasmiy Nizom bilan eski Nizom o‘rtasida farq ko‘rinsa, hujjat sanasi/tahririni aniq ko‘rsating "
        "va ularni aralashtirmang.\n"
        "Javob tuzilishi: 1) Qisqa xulosa; 2) Amaliy tartib; 3) Huquqiy asos; 4) Muddat va to‘lov; "
        "5) Манба (hujjat nomi, sana, band/ilova). Keraksiz takror va 'agar xohlasangiz' kabi yakuniy iboralarni yozmang.\n"
        "Javob o‘zbek tilida, aniq, professional va amaliy bo‘lsin. Markdown yulduzchalarini ishlatmang."
    )
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": "Savol:\n" + question + "\n\nBilim bazasi:\n" + context},
        ],
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + OPENAI_API_KEY},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        data = json.loads(response.read().decode("utf-8"))
    answer = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return str(answer).strip() or "OpenAI javob qaytarmadi."


def clean_answer(text):
    text = str(text or "").replace("**", "").replace("```", "").replace("`", "")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def telegram(method, payload):
    url = "https://api.telegram.org/bot" + BOT_TOKEN + "/" + method
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=40) as response:
        return json.loads(response.read().decode("utf-8"))


def send_message(chat_id, text):
    text = clean_answer(text)
    for i in range(0, len(text), MAX_MESSAGE_LENGTH):
        telegram("sendMessage", {"chat_id": chat_id, "text": text[i:i + MAX_MESSAGE_LENGTH]})


def process_update(update):
    message = update.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    text = str(message.get("text", "")).strip()
    if not chat_id or not text:
        return
    logging.info("Savol: %s", text[:500])
    if text.startswith("/start"):
        send_message(chat_id, "Assalomu alaykum!\n\nMen Madaniy Meros AI yordamchisiman. Savolingizni yozing.")
        return
    if text.startswith("/help"):
        send_message(chat_id, "Masalan:\n• Tarixiy-madaniy ekspertiza tartibi qanday?\n• Madaniy meros obyektida qurilish mumkinmi?\n• Qaysi holatda ruxsat kerak?\n• 119-sonli qaror nima haqida?")
        return
    send_message(chat_id, "⏳ Savolingiz ko‘rib chiqilmoqda...")
    try:
        direct = direct_answer(text)
        if direct:
            answer = direct
        else:
            results = search_kb(text, 18)
            if not results:
                answer = "Taqdim etilgan bilim bazasida bu savolga yetarli aniq ma’lumot topilmadi."
            else:
                answer = openai_answer(text, results)
        send_message(chat_id, answer)
    except urllib.error.HTTPError as e:
        logging.exception("HTTP xatosi")
        if e.code == 401:
            send_message(chat_id, "⚠️ OpenAI API kaliti bilan bog‘liq xatolik.")
        elif e.code == 429:
            send_message(chat_id, "⚠️ OpenAI limiti yoki billing bo‘yicha muammo yuz berdi.")
        else:
            send_message(chat_id, "⚠️ Javob tayyorlashda texnik xatolik yuz berdi.")
    except Exception:
        logging.exception("Savolni qayta ishlash xatosi")
        send_message(chat_id, "⚠️ Javob tayyorlashda texnik xatolik yuz berdi.")


def setup_webhook():
    if not RENDER_EXTERNAL_URL:
        logging.warning("RENDER_EXTERNAL_URL topilmadi")
        return
    result = telegram("setWebhook", {"url": WEBHOOK_URL, "drop_pending_updates": False})
    logging.info("Webhook: %s", result)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        body = b"OK"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != WEBHOOK_PATH:
            self.send_response(404)
            self.end_headers()
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            update = json.loads(raw.decode("utf-8"))
            self.send_response(200)
            self.end_headers()
            threading.Thread(target=process_update, args=(update,), daemon=True).start()
        except Exception:
            logging.exception("Webhook xatosi")
            try:
                self.send_response(200)
                self.end_headers()
            except Exception:
                pass


def main():
    logging.info("MADANIY MEROS AI ishga tushmoqda")
    logging.info("KB=%s | MODEL=%s | PORT=%s", KB_FILE, OPENAI_MODEL, PORT)
    setup_webhook()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
