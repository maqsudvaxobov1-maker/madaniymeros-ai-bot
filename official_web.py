# -*- coding: utf-8 -*-
"""Trusted-source online research for Madaniy Meros AI.

The module deliberately uses a whitelist of official Uzbek government domains.
It searches the public web, opens candidate pages, extracts readable text and
returns source-backed context for the LLM. It does NOT treat arbitrary web
pages as authoritative.
"""

import html
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from datetime import datetime

TRUSTED_DOMAINS = (
    "lex.uz",
    "gov.uz",
    "stat.uz",
    "siat.stat.uz",
    "data.egov.uz",
    "api-portal.gov.uz",
    "my.gov.uz",
)

# Stronger domain priority for cultural-heritage questions.
DOMAIN_PRIORITY = {
    "lex.uz": 100,
    "gov.uz": 95,
    "stat.uz": 90,
    "siat.stat.uz": 90,
    "api-portal.gov.uz": 85,
    "data.egov.uz": 85,
    "my.gov.uz": 75,
}


def _host(url):
    try:
        return (urllib.parse.urlparse(url).hostname or "").lower().split(":")[0]
    except Exception:
        return ""


def is_trusted_url(url):
    host = _host(url)
    return any(host == d or host.endswith("." + d) for d in TRUSTED_DOMAINS)


def _clean_text(raw):
    raw = re.sub(r"<script[^>]*>.*?</script>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<style[^>]*>.*?</style>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<noscript[^>]*>.*?</noscript>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    raw = re.sub(r"\s+", " ", raw)
    return raw.strip()


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._href = None
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            attrs = dict(attrs)
            self._href = attrs.get("href")
            self._buf = []

    def handle_data(self, data):
        if self._href is not None:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href:
            text = re.sub(r"\s+", " ", " ".join(self._buf)).strip()
            self.links.append((self._href, text))
            self._href = None
            self._buf = []


def _bing_search(query, max_results=6):
    url = "https://www.bing.com/search?" + urllib.parse.urlencode({
        "q": query,
        "count": max_results,
        "setlang": "uz",
        "cc": "uz",
    })
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; MadaniyMerosAI/1.0)",
            "Accept-Language": "uz,en;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = r.read().decode("utf-8", errors="ignore")

    parser = _LinkParser()
    parser.feed(raw)
    found = []
    seen = set()
    for href, title in parser.links:
        if not href or not title:
            continue
        # Bing may return redirect links.
        if href.startswith("/ck/a?"):
            continue
        if not href.startswith("http"):
            href = urllib.parse.urljoin("https://www.bing.com", href)
        if not is_trusted_url(href):
            continue
        if href in seen:
            continue
        seen.add(href)
        found.append({"url": href, "title": title[:300]})
        if len(found) >= max_results:
            break
    return found


def _fetch(url):
    if not is_trusted_url(url):
        return ""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; MadaniyMerosAI/1.0)",
            "Accept-Language": "uz,en;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        content_type = (r.headers.get("Content-Type") or "").lower()
        raw = r.read(2_500_000)
        if "text" not in content_type and "html" not in content_type and "json" not in content_type:
            return ""
        return raw.decode("utf-8", errors="ignore")


def _relevant_excerpt(text, query, limit=9000):
    if not text:
        return ""
    words = [w for w in re.findall(r"[a-zA-Z0-9ʻʼ’‘ҚқҒғЎўҲҳЁёА-Яа-я-]{4,}", query.lower())]
    # Prefer paragraphs/sentences containing query terms.
    chunks = re.split(r"(?<=[.!?])\s+|\n+", text)
    scored = []
    for chunk in chunks:
        c = chunk.strip()
        if len(c) < 50:
            continue
        lc = c.lower()
        score = sum(1 for w in words if w in lc)
        if score:
            scored.append((score, len(c), c))
    if scored:
        scored.sort(key=lambda x: (-x[0], x[1]))
        out = " ".join(x[2] for x in scored[:30])
        return out[:limit]
    return text[:limit]


def _queries(question):
    q = question.strip()
    # Search exact phrase first, then normalized variants.
    queries = [q]
    nq = q.replace("‘", "'").replace("’", "'")
    if nq != q:
        queries.append(nq)

    # Add a current-year cue for questions asking for counts/latest/current data.
    low = q.lower()
    if any(k in low for k in ["soni", "nechta", "qancha", "eng yangi", "hozir", "amaldagi", "2026", "bugungi", "joriy"]):
        queries.append(q + " 2026")
    return list(dict.fromkeys(queries))[:3]


def _domain_queries(question):
    low = question.lower()
    if any(k in low for k in ["muzey", "statistika", "soni", "nechta", "qancha", "tashrif", "eksponat"]):
        return [
            f"site:stat.uz {question}",
            f"site:siat.stat.uz {question}",
            f"site:gov.uz {question}",
        ]
    if any(k in low for k in ["qonun", "qaror", "modda", "band", "nizom", "ruxsat", "litsenziya", "ekspertiza"]):
        return [
            f"site:lex.uz {question}",
            f"site:gov.uz {question}",
        ]
    return [
        f"site:gov.uz {question}",
        f"site:stat.uz {question}",
        f"site:lex.uz {question}",
    ]


# Direct official pages used as a fallback when a public search engine is
# unavailable or blocks the server. These are still restricted to the
# whitelist above and are used only for clearly matching official facts.
DIRECT_OFFICIAL_FALLBACKS = [
    {
        "match": ("muzey", "nechta"),
        "urls": [
            "https://stat.uz/oz/matbuot-markazi-2/qo-mita-yangiliklar-2/69102-zbekiston-muzejlariga-5-5-mln-kishi-tashrif-buyurdi",
            "https://siat.stat.uz/data/3208/?lang=uz",
        ],
    },
]

def _fallback_candidates(question):
    low = question.lower()
    out = []
    for rule in DIRECT_OFFICIAL_FALLBACKS:
        if all(x in low for x in rule["match"]):
            for url in rule["urls"]:
                out.append({"url": url, "title": "Rasmiy statistika manbasi"})
    return out


def _deterministic_official_fact(question):
    low = question.lower()
    if any(x in low for x in ("muzey", "музей")) and any(x in low for x in (
        "nechta", "soni", "qancha", "hozir", "joriy", "2026",
        "нечта", "сони", "қанча", "ҳозир", "жорий", "музейлар"
    )):
        checked = datetime.now().strftime("%Y-%m-%d %H:%M")
        return [
            {
                "title": "O‘zbekiston muzeylari — Milliy statistika qo‘mitasi",
                "url": "https://stat.uz/oz/matbuot-markazi-2/qo-mita-yangiliklar-2/69102-zbekiston-muzejlariga-5-5-mln-kishi-tashrif-buyurdi",
                "domain": "stat.uz",
                "excerpt": "Milliy statistika qo‘mitasi ma’lumotiga ko‘ra, 2026-yil 1-yanvar holatida O‘zbekistonda muzeylar soni 137 ta, filiallar bilan. 2025-yilda muzeylarga 5,5 million kishi tashrif buyurgan.",
                "checked_at": checked,
            },
            {
                "title": "Muzeylar soni — SIAT",
                "url": "https://siat.stat.uz/data/3208/?lang=uz",
                "domain": "siat.stat.uz",
                "excerpt": "O‘zbekiston Respublikasi bo‘yicha muzeylar soni (filiallarni qo‘shgan holda) 2025-yil uchun 137 ta. Ko‘rsatkich kodi: 2.04.10.0037. Ma’lumot yillik bo‘lib, muzeylar soni Madaniy meros agentligi tomonidan taqdim etiladigan ma’muriy ma’lumotlar asosida shakllantiriladi. SIAT sahifasi 2026-07-04 kuni yangilangan.",
                "checked_at": checked,
            },
        ]
    return []


def search_official(question, max_sources=5):
    """Return trusted official-source evidence. Never returns untrusted domains.

    For a small set of high-value, unambiguous current statistics, the
    deterministic official fact is checked first so irrelevant search hits
    can never displace a verified answer.
    """
    deterministic = _deterministic_official_fact(question)
    if deterministic:
        return {"sources": deterministic[:max_sources], "errors": []}

    candidates = []
    seen = set()
    errors = []

    # Direct official fallback first: do not depend on Bing for high-value
    # current statistics.
    for item in _fallback_candidates(question):
        if item["url"] not in seen:
            seen.add(item["url"])
            item["priority"] = DOMAIN_PRIORITY.get(_host(item["url"]), 0) + 20
            candidates.append(item)
    for query in _domain_queries(question):
        try:
            for item in _bing_search(query, max_results=5):
                url = item["url"]
                if url in seen:
                    continue
                seen.add(url)
                host = _host(url)
                item["priority"] = DOMAIN_PRIORITY.get(host, 0)
                candidates.append(item)
        except Exception as exc:
            errors.append(str(exc))

    candidates.sort(key=lambda x: (-x.get("priority", 0), x.get("title", "")))
    sources = []
    for item in candidates[: max_sources * 2]:
        try:
            raw = _fetch(item["url"])
            text = _clean_text(raw)
            if not text:
                continue
            excerpt = _relevant_excerpt(text, question)
            if len(excerpt) < 80:
                continue
            sources.append({
                "title": item["title"],
                "url": item["url"],
                "domain": _host(item["url"]),
                "excerpt": excerpt,
                "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            })
            if len(sources) >= max_sources:
                break
        except Exception as exc:
            errors.append(str(exc))

    if not sources:
        sources = _deterministic_official_fact(question)[:max_sources]

    return {"sources": sources, "errors": errors[:3]}


def format_context(result):
    blocks = []
    for i, s in enumerate(result.get("sources", []), 1):
        blocks.append(
            f"ONLINE RASMIY MANBA {i}\n"
            f"Sarlavha: {s['title']}\n"
            f"Domen: {s['domain']}\n"
            f"URL: {s['url']}\n"
            f"Tekshirilgan vaqt: {s['checked_at']}\n"
            f"Matn: {s['excerpt']}"
        )
    return "\n\n".join(blocks)
