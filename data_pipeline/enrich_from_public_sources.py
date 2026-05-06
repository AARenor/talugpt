"""Enrich existing farm records from additional public producer directories.

The script keeps the dataset conservative: it only updates records that can be
matched to public producer profiles by strong name/contact evidence. It does
not create new map records because new records would need separate geocoding
and manual de-duplication.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import html
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data_pipeline" / "Full farm data.json"
CACHE_FILE = ROOT / "public_source_cache.json"
_CACHE: dict[str, dict[str, Any]] | None = None

USER_AGENT = "TaluGPT public source enrichment (+https://github.com/AARenor/talugpt)"
TIMEOUT_SECONDS = 18
MAX_WORKERS = 10
RUN_SOURCE_ID = "public-source-enrichment-2026-05"

PUBLIC_SOURCE_NOTES = [
    {
        "name": "Loode-Eesti Toit tootjaprofiilid",
        "url": "https://toit.loode-eesti.ee/tootjad/",
        "use": "Harju-, Laane- ja Raplamaa tootjate profiilid, kontaktid ja tooteliigid",
    },
    {
        "name": "Uma Mekk tootjate kataloog",
        "url": "https://umamekk.ee/tootjad/",
        "use": "Vorumaa ja Vana-Vorumaa tootjate detailkirjeldused ning tootekategooriad",
    },
    {
        "name": "Ehtne Talutoit tootjaprofiilid",
        "url": "https://talutoit.ee/wp-sitemap-posts-producer-1.xml",
        "use": "Ehtne Talutoit / OTT profiilid, talumeiereid ja vaiketootjad",
    },
    {
        "name": "Sibulatee liikmete kataloog",
        "url": "https://www.sibulatee.ee/Sibulateelised/",
        "use": "Peipsimaa toidu-, ostu- ja kohalikku tootmist puudutavad liikmeprofiilid",
    },
    {
        "name": "Minu Saaremaa - Tarbi saaremaist sook ja jook",
        "url": "https://minusaaremaa.ee/index.php/kasulikud-kontaktid/tarbisaaremaist/sook-ja-jook",
        "use": "Saaremaa kohalike tootjate kontaktid, e-poed ja tootevaldkonnad",
    },
]

FOOD_TERMS = [
    "toorpiim",
    "piim",
    "kitsepiim",
    "juust",
    "jogurt",
    "kohupiim",
    "soir",
    "munad",
    "mesi",
    "mahemesi",
    "suir",
    "taruvaik",
    "veiseliha",
    "lambaliha",
    "sealiha",
    "vorst",
    "sink",
    "kala",
    "suitsukala",
    "forell",
    "angerjas",
    "leib",
    "pagaritooted",
    "kupsetised",
    "gluteenivaba",
    "jahu",
    "kaer",
    "tatar",
    "lina",
    "linajahu",
    "linaseeme",
    "raps",
    "kartul",
    "sibul",
    "kuuslauk",
    "koogivili",
    "juurvili",
    "maasikad",
    "vaarikad",
    "mustikad",
    "astelpaju",
    "oun",
    "ounamahl",
    "mahl",
    "siirup",
    "siider",
    "koduoLu",
    "vein",
    "kombucha",
    "kasemahl",
    "limonaad",
    "moos",
    "hoidis",
    "marmelaad",
    "sokolaad",
    "maiused",
    "taimetee",
    "ravimtaimed",
    "maitsetaimed",
    "teesegu",
    "maitseained",
    "maitsesool",
    "sinep",
    "kadakasiirup",
    "gelato",
    "jaatis",
    "musli",
    "granola",
]

TERM_ALIASES = {
    "koduoLu": "koduõlu",
    "kuuslauk": "küüslauk",
    "koogivili": "köögivili",
    "oun": "õun",
    "ounamahl": "õunamahl",
    "sokolaad": "šokolaad",
    "soir": "sõir",
    "kupsetised": "küpsetised",
    "jaatis": "jäätis",
    "musli": "müsli",
}

BAD_WEBSITE_HOSTS = {
    "addtoany.com",
    "doubleclick.net",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "google.com",
    "google-analytics.com",
    "googletagmanager.com",
    "gstatic.com",
    "schema.org",
    "wordpress.org",
    "wp.com",
}

SOURCE_HOSTS = {
    "talutoit.ee",
    "umamekk.ee",
    "toit.loode-eesti.ee",
    "sibulatee.ee",
    "www.sibulatee.ee",
    "minusaaremaa.ee",
}

SOCIAL_HOSTS = {"facebook.com", "www.facebook.com", "instagram.com", "www.instagram.com"}

EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", re.IGNORECASE)
HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:(?:\+|00)?372[\s().-]*)?(?:\d[\s().-]*){7,8}")

LEGAL_WORDS = {
    "as",
    "fie",
    "mtu",
    "mtu",
    "mtu",
    "mtu",
    "mtu",
    "mtu",
    "mtu",
    "ou",
    "sa",
    "tu",
    "osa",
    "uhistu",
    "osaühing",
    "tulundusuhistu",
    "aktsiaselts",
    "sihtasutus",
    "mittetulundusuhing",
    "mittetulundusühing",
}

SOFT_WORDS = {
    "talu",
    "mahetalu",
    "farm",
    "pruulikoda",
    "meierei",
    "pagarikoda",
    "tootja",
    "pood",
}


def load_cache() -> dict[str, dict[str, Any]]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    if not CACHE_FILE.exists():
        _CACHE = {}
        return _CACHE
    _CACHE = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return _CACHE


def save_cache(cache: dict[str, dict[str, Any]]) -> None:
    global _CACHE
    _CACHE = cache
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def cache_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]


def fetch_url_uncached(url: str) -> dict[str, Any]:
    started = time.time()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read(2_500_000)
            charset = response.headers.get_content_charset() or "utf-8"
            return {
                "ok": True,
                "url": response.geturl(),
                "status": getattr(response, "status", 200),
                "content_type": response.headers.get("content-type", ""),
                "text": body.decode(charset, errors="replace"),
                "elapsed_ms": int((time.time() - started) * 1000),
            }
    except (TimeoutError, OSError, urllib.error.URLError) as error:
        return {
            "ok": False,
            "url": url,
            "error": str(error),
            "elapsed_ms": int((time.time() - started) * 1000),
        }


def fetch_urls(urls: list[str]) -> dict[str, dict[str, Any]]:
    cache = load_cache()
    missing = [url for url in dict.fromkeys(urls) if cache_key(url) not in cache]
    if missing:
        print(f"fetching {len(missing)} public source URLs")
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            future_map = {pool.submit(fetch_url_uncached, url): url for url in missing}
            for i, future in enumerate(concurrent.futures.as_completed(future_map), start=1):
                url = future_map[future]
                cache[cache_key(url)] = future.result()
                if i % 25 == 0:
                    print(f"  fetched {i}/{len(missing)}")
                    save_cache(cache)
        save_cache(cache)
    return {url: cache[cache_key(url)] for url in dict.fromkeys(urls)}


def fetch_text(url: str) -> str:
    return fetch_urls([url])[url].get("text") or ""


def fetch_json(url: str) -> Any:
    text = fetch_text(url)
    return json.loads(text)


def strip_html(raw: str) -> str:
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", raw)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p>|</li>|</div>|</tr>|</h[1-6]>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    return clean_text(html.unescape(text))


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(text))).strip()


def fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    ascii_text = ascii_text.replace("õ", "o").replace("š", "s").replace("ž", "z")
    return ascii_text


def normalize_name(text: str) -> str:
    text = fold(html.unescape(text))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = [t for t in text.split() if t not in LEGAL_WORDS]
    return " ".join(tokens)


def strong_tokens(text: str) -> set[str]:
    tokens = set()
    for token in normalize_name(text).split():
        if len(token) >= 3 and token not in LEGAL_WORDS:
            tokens.add(token)
    return tokens


def distinctive_tokens(text: str) -> set[str]:
    return {token for token in strong_tokens(text) if token not in SOFT_WORDS and len(token) >= 4}


def clean_url(raw: str, base: str | None = None) -> str | None:
    raw = html.unescape(str(raw)).strip()
    if not raw or raw.startswith(("#", "javascript:")):
        return None
    if raw.startswith("mailto:") or raw.startswith("tel:"):
        return None
    if base:
        raw = urllib.parse.urljoin(base, raw)
    raw = raw.rstrip(".,);]")
    try:
        parsed = urllib.parse.urlparse(raw)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    parsed = parsed._replace(fragment="")
    return urllib.parse.urlunparse(parsed)


def host(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.casefold().removeprefix("www.")


def normalize_phone(raw: str, context: str = "") -> str | None:
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("00372"):
        digits = digits[2:]
    if digits.startswith("372"):
        local = digits[3:]
    else:
        local = digits
        if context and not re.search(r"tel|telefon|phone|mobiil|kontakt", context, re.I):
            return None
    if len(local) not in {7, 8}:
        return None
    if local.startswith(("000", "123", "199", "201", "202")):
        return None
    return f"+372 {local}"


def extract_emails(raw: str) -> list[str]:
    decoded = html.unescape(urllib.parse.unquote(raw))
    emails: list[str] = []
    for href in HREF_RE.findall(decoded):
        if href.casefold().startswith("mailto:"):
            value = href.split(":", 1)[1].split("?", 1)[0]
            emails.append(value)
    emails.extend(match.group(0) for match in EMAIL_RE.finditer(decoded))
    cleaned: list[str] = []
    for email in emails:
        email = email.strip(".,;:()[]{}<>").casefold()
        if EMAIL_RE.fullmatch(email) and not email.endswith((".png", ".jpg", ".jpeg", ".webp")):
            cleaned.append(email)
    return list(dict.fromkeys(cleaned))


def extract_phones(raw: str) -> list[str]:
    decoded = html.unescape(urllib.parse.unquote(raw))
    phones: list[str] = []
    for href in HREF_RE.findall(decoded):
        if href.casefold().startswith("tel:"):
            phone = normalize_phone(href.split(":", 1)[1], "tel")
            if phone:
                phones.append(phone)
    text = strip_html(decoded)
    for match in PHONE_RE.finditer(text):
        context = text[max(0, match.start() - 50) : min(len(text), match.end() + 50)]
        phone = normalize_phone(match.group(0), context)
        if phone:
            phones.append(phone)
    return list(dict.fromkeys(phones))


def is_good_website(url: str, source_url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    h = parsed.netloc.casefold()
    folded = url.casefold()
    if any(bad in folded for bad in BAD_WEBSITE_HOSTS):
        return False
    if parsed.path.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".pdf")):
        return False
    if "share" in folded or "sharer" in folded:
        return False
    if h.removeprefix("www.") == host(source_url) and parsed.path in {"", "/"}:
        return False
    return True


def extract_websites(raw: str, source_url: str) -> list[str]:
    candidates: list[str] = []
    for href in HREF_RE.findall(raw):
        url = clean_url(href, source_url)
        if url and is_good_website(url, source_url):
            candidates.append(url)

    def website_score(url: str) -> tuple[int, str]:
        h = urllib.parse.urlparse(url).netloc.casefold()
        if h.removeprefix("www.") in SOURCE_HOSTS:
            return (0, url)
        if h in SOCIAL_HOSTS:
            return (1, url)
        return (2, url)

    unique = list(dict.fromkeys(candidates))
    unique.sort(key=website_score, reverse=True)
    return unique


def render_wp_title(value: Any) -> str:
    if isinstance(value, dict):
        return strip_html(str(value.get("rendered") or ""))
    return strip_html(str(value or ""))


def wp_collection(base: str, rest_base: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for page in range(1, 20):
        url = f"{base.rstrip('/')}/wp-json/wp/v2/{rest_base}?per_page=100&page={page}"
        try:
            batch = fetch_json(url)
        except json.JSONDecodeError:
            break
        if not isinstance(batch, list) or not batch:
            break
        items.extend(batch)
        if len(batch) < 100:
            break
    return items


def wp_taxonomy(base: str, taxonomy: str) -> dict[int, str]:
    try:
        raw = fetch_json(f"{base.rstrip('/')}/wp-json/wp/v2/{taxonomy}?per_page=100")
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, list):
        return {}
    return {int(item["id"]): clean_text(item.get("name") or "") for item in raw if item.get("id")}


def product_terms(text: str, categories: list[str]) -> list[str]:
    folded = fold(" ".join([text, *categories]))
    found: list[str] = []
    for term in FOOD_TERMS:
        if re.search(rf"\b{re.escape(fold(term))}\w*\b", folded):
            found.append(TERM_ALIASES.get(term, term))
    if re.search(r"\bõli\w*\b", " ".join([text, *categories]).casefold()):
        found.append("õli")
    return list(dict.fromkeys(found))[:10]


def source_summary(text: str) -> str | None:
    text = clean_text(text)
    text = re.sub(r"\b(?:Kontakt|Tutvustus)\b", " ", text, flags=re.I)
    text = re.sub(r"\S+@\S+", " ", text)
    text = re.sub(r"(?:\+372\s*)?\d[\d\s().-]{6,}\d", " ", text)
    text = re.sub(r"https?://\S+|www\.\S+", " ", text, flags=re.I)
    text = clean_text(text)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sentence in sentences:
        sentence = clean_text(sentence)
        if 60 <= len(sentence) <= 260 and not re.search(
            r"cookie|privacy|facebook|instagram|pangaling|ulekandearve|ülekandearve|pakiautomaat",
            sentence,
            re.I,
        ):
            return sentence
    if 60 <= len(text) <= 260:
        return text
    if len(text) > 260:
        return text[:257].rsplit(" ", 1)[0] + "..."
    return None


def extract_legal_names(text: str) -> list[str]:
    names: list[str] = []
    pattern = re.compile(
        r"\b(?:[A-ZÕÄÖÜŠŽ][\wÕÄÖÜŠŽõäöüšž'-]{1,}\s+){0,4}"
        r"(?:OÜ|OU|AS|FIE|MTÜ|SA)\s*"
        r"(?:[A-ZÕÄÖÜŠŽ][\wÕÄÖÜŠŽõäöüšž'-]{1,}){0,4}",
    )
    for match in pattern.finditer(text):
        name = clean_text(match.group(0))
        if 4 <= len(name) <= 80:
            names.append(name)
    return list(dict.fromkeys(names))


def make_profile(
    source_id: str,
    source_name: str,
    source_url: str,
    title: str,
    text: str,
    categories: list[str] | None = None,
    email: str | None = None,
    phone: str | None = None,
    website: str | None = None,
    region_tag: str | None = None,
    extra_names: list[str] | None = None,
) -> dict[str, Any]:
    categories = [clean_text(c) for c in (categories or []) if clean_text(c)]
    text = clean_text(text)
    emails = extract_emails(text) if not email else [email]
    phones = extract_phones(text) if not phone else [phone]
    websites = extract_websites(text, source_url) if not website else [website]
    names = [title, *(extra_names or []), *extract_legal_names(text)]
    names = [clean_text(n) for n in names if clean_text(n)]
    return {
        "source_id": source_id,
        "source_name": source_name,
        "source_url": source_url,
        "title": clean_text(title),
        "names": list(dict.fromkeys(names)),
        "text": text,
        "categories": categories,
        "products": product_terms(text, categories),
        "email": emails[0] if emails else None,
        "phone": phones[0] if phones else None,
        "website": websites[0] if websites else source_url,
        "region_tag": region_tag,
        "summary": source_summary(text),
    }


def loode_profiles() -> list[dict[str, Any]]:
    base = "https://toit.loode-eesti.ee"
    cats = wp_taxonomy(base, "tootja_kat")
    profiles = []
    for item in wp_collection(base, "tootja"):
        title = render_wp_title(item.get("title"))
        text = strip_html(str((item.get("content") or {}).get("rendered") or ""))
        categories = [cats[c] for c in item.get("tootja_kat") or [] if c in cats]
        profiles.append(
            make_profile(
                "loode-eesti-toit-2026-05",
                "Loode-Eesti Toit",
                str(item.get("link") or base),
                title,
                text,
                categories,
                region_tag="Loode-Eesti Toit",
            )
        )
    return profiles


def umamekk_profiles() -> list[dict[str, Any]]:
    base = "https://umamekk.ee"
    cats = wp_taxonomy(base, "tootekategooriad")
    profiles = []
    for item in wp_collection(base, "tootja"):
        title = render_wp_title(item.get("title"))
        text = strip_html(str((item.get("content") or {}).get("rendered") or ""))
        categories = [cats[c] for c in item.get("tootekategooriad") or [] if c in cats]
        profiles.append(
            make_profile(
                "umamekk-detail-2026-05",
                "Uma Mekk",
                str(item.get("link") or base),
                title,
                text,
                categories,
                region_tag="Uma Mekk",
            )
        )
    return profiles


def sibulatee_profiles() -> list[dict[str, Any]]:
    base = "https://www.sibulatee.ee"
    cats = wp_taxonomy(base, "members_category")
    profiles = []
    for item in wp_collection(base, "members"):
        if item.get("lang") and item.get("lang") != "et":
            continue
        title = render_wp_title(item.get("title"))
        category_names = [cats[c] for c in item.get("members_category") or [] if c in cats]
        text = " ".join(
            [
                strip_html(str((item.get("excerpt") or {}).get("rendered") or "")),
                strip_html(str((item.get("content") or {}).get("rendered") or "")),
                str(item.get("address") or ""),
                str(item.get("webpage") or ""),
            ]
        )
        if not (
            {"Osta", "Söö"} & set(category_names)
            or re.search(r"toit|sibul|kala|mesi|pood|kohvik|restoran|talutoode", text, re.I)
        ):
            continue
        website = clean_url(str(item.get("webpage") or ""), base)
        phone = normalize_phone(str(item.get("telefon") or ""), "telefon")
        email = str(item.get("email") or "").strip().casefold() or None
        profiles.append(
            make_profile(
                "sibulatee-2026-05",
                "Sibulatee",
                str(item.get("link") or base),
                title,
                text,
                category_names,
                email=email,
                phone=phone,
                website=website,
                region_tag="Sibulatee",
            )
        )
    return profiles


def talutoit_profiles() -> list[dict[str, Any]]:
    sitemap = "https://talutoit.ee/wp-sitemap-posts-producer-1.xml"
    xml = fetch_text(sitemap)
    urls = re.findall(r"<loc>(.*?)</loc>", xml)
    fetch_urls(urls)
    profiles = []
    for url in urls:
        raw = fetch_text(url)
        title_match = (
            re.search(r'(?is)<h1[^>]*class="[^"]*entry-title[^"]*"[^>]*>(.*?)</h1>', raw)
            or re.search(r"(?is)<h1[^>]*>(.*?)</h1>", raw)
            or re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
        )
        title = strip_html(title_match.group(1)) if title_match else urllib.parse.urlparse(url).path.strip("/")
        title = re.sub(r"\s*\|\s*$", "", title)
        content_start = raw.find('<div class="entry-content cms">')
        content_end = raw.find("</article>", content_start)
        content = raw[content_start:content_end] if content_start >= 0 and content_end > content_start else raw
        text = strip_html(content)
        text = re.split(r"\b(?:Kust osta|Vaata ka|Sarnased|E-turg)\b", text, maxsplit=1)[0]
        text = text[:2500]
        profiles.append(
            make_profile(
                "talutoit-producer-2026-05",
                "Ehtne Talutoit",
                url,
                title,
                text,
                ["Ehtne Talutoit"],
                region_tag="Ehtne Talutoit",
            )
        )
    return profiles


def minusaaremaa_profiles() -> list[dict[str, Any]]:
    url = "https://minusaaremaa.ee/index.php/kasulikud-kontaktid/tarbisaaremaist/sook-ja-jook"
    raw = fetch_text(url)
    chunks = re.split(r'<div class="col-12 col-md-6 col-lg-4 element[^"]*">', raw)
    profiles = []
    for chunk in chunks[1:]:
        name_match = re.search(r"(?is)<h6[^>]*>(.*?)</h6>", chunk)
        product_match = re.search(r'(?is)<div class="mb-2">(.*?)</div>', chunk)
        if not name_match:
            continue
        name = strip_html(name_match.group(1))
        products = strip_html(product_match.group(1)) if product_match else ""
        card = chunk.split('<div class="col-12 col-md-6 col-lg-4 element', 1)[0]
        websites = extract_websites(card, url)
        emails = extract_emails(card)
        phones = extract_phones(card)
        profile = make_profile(
            "minu-saaremaa-food-2026-05",
            "Minu Saaremaa kohalik toit",
            url,
            name,
            f"{name}. {products}. {strip_html(card)}",
            ["Saaremaa kohalik toit"],
            email=emails[0] if emails else None,
            phone=phones[0] if phones else None,
            website=websites[0] if websites else None,
            region_tag="EHTNE Saaremaa",
        )
        if products:
            profile["summary"] = products
        if len(products) >= 12:
            profile["products"] = list(dict.fromkeys([*profile.get("products", []), products]))
        profiles.append(profile)
    return profiles


def profile_contact_keys(profile: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    if profile.get("email"):
        keys.add(f"email:{profile['email']}")
    if profile.get("website"):
        website = str(profile["website"])
        website_host = host(website)
        if website_host not in SOURCE_HOSTS and website_host not in {"facebook.com", "instagram.com"}:
            keys.add(f"domain:{website_host}")
        elif website_host in {"facebook.com", "instagram.com"}:
            keys.add(f"url:{website.rstrip('/').casefold()}")
    return keys


def record_contact_keys(record: dict[str, Any]) -> set[str]:
    contact = record.get("contact") or {}
    keys: set[str] = set()
    email = str(contact.get("email") or "").casefold()
    website = str(contact.get("website") or "")
    if email:
        keys.add(f"email:{email}")
    if website:
        website_host = host(website)
        if website_host not in SOURCE_HOSTS and website_host not in {"facebook.com", "instagram.com"}:
            keys.add(f"domain:{website_host}")
        elif website_host in {"facebook.com", "instagram.com"}:
            keys.add(f"url:{website.rstrip('/').casefold()}")
    return keys


def record_names(record: dict[str, Any]) -> list[str]:
    names = [
        str(record.get("display_name") or ""),
        str(record.get("name") or ""),
        str(record.get("slug") or "").replace("-", " "),
    ]
    return [name for name in names if name.strip()]


def name_score(profile_name: str, record_name: str) -> int:
    pn = normalize_name(profile_name)
    rn = normalize_name(record_name)
    if not pn or not rn:
        return 0
    if pn == rn:
        return 100
    if len(pn) >= 7 and len(rn) >= 7 and (pn in rn or rn in pn):
        return 94
    pt = strong_tokens(profile_name)
    rt = strong_tokens(record_name)
    if not pt or not rt:
        return 0
    dt = distinctive_tokens(profile_name)
    drt = distinctive_tokens(record_name)
    intersection = len(pt & rt)
    union = len(pt | rt)
    jaccard = intersection / union
    if dt and dt <= drt:
        return 92 if len(dt) >= 2 else 84
    if drt and drt <= dt:
        return 91 if len(drt) >= 2 else 83
    if jaccard >= 0.8:
        return 90
    if jaccard >= 0.6 and intersection >= 2:
        return 86
    return 0


def record_region_bonus(profile: dict[str, Any], record: dict[str, Any]) -> int:
    region = str(profile.get("region_tag") or "")
    county = str(record.get("county") or "")
    municipality = str(record.get("municipality") or "")
    blob = fold(" ".join([county, municipality, " ".join(record.get("tags") or [])]))
    if "Saaremaa" in region and "saare" in blob:
        return 5
    if "Uma Mekk" in region and ("voru" in blob or "vana voru" in blob):
        return 5
    if "Loode-Eesti" in region and any(term in blob for term in ["harju", "laane", "rapla"]):
        return 5
    if "Sibulatee" in region and any(term in blob for term in ["tartu", "jogeva", "peipsi"]):
        return 5
    return 0


def match_profile(profile: dict[str, Any], records: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, int]:
    contact_keys = profile_contact_keys(profile)
    scored: list[tuple[int, dict[str, Any]]] = []
    for record in records:
        score = 0
        if contact_keys & record_contact_keys(record):
            score = 99
        for profile_name in profile.get("names") or []:
            for record_name in record_names(record):
                score = max(score, name_score(profile_name, record_name))
        if score:
            score += record_region_bonus(profile, record)
            scored.append((score, record))
    if not scored:
        return None, 0
    scored.sort(key=lambda item: item[0], reverse=True)
    top_score, top_record = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0
    if top_score >= 92 and top_score - second_score >= 4:
        return top_record, top_score
    if top_score >= 99 and top_score > second_score:
        return top_record, top_score
    return None, top_score


def add_unique(values: list[str], additions: list[str], limit: int | None = None) -> int:
    changed = 0
    seen = {v.casefold() for v in values}
    for value in additions:
        value = clean_text(value)
        if not value or value.casefold() in seen:
            continue
        values.append(value)
        seen.add(value.casefold())
        changed += 1
        if limit and len(values) >= limit:
            break
    return changed


def has_source(record: dict[str, Any], ref: str) -> bool:
    for source in record.get("sources") or []:
        if source.get("source_id") == RUN_SOURCE_ID and source.get("ref") == ref:
            return True
    return False


def apply_profile(record: dict[str, Any], profile: dict[str, Any], score: int) -> dict[str, int]:
    stats = Counter()
    products = record.setdefault("products", [])
    tags = record.setdefault("tags", [])
    categories = record.setdefault("categories", [])
    contact = record.setdefault("contact", {"email": None, "phone": None, "website": None})

    stats["products_added"] += add_unique(products, profile.get("products") or [], limit=28)
    tag_additions = [
        str(profile.get("source_name") or ""),
        str(profile.get("region_tag") or ""),
        "kohalik toit",
        "toiduvõrgustik",
        *[product for product in (profile.get("products") or []) if len(product) <= 40],
        *[
            category
            for category in (profile.get("categories") or [])
            if category.casefold() not in {"toit", "söö", "soo", "osta"}
        ],
    ]
    stats["tags_added"] += add_unique(tags, tag_additions, limit=60)
    stats["categories_added"] += add_unique(categories, profile.get("categories") or [], limit=24)

    for field in ("email", "phone", "website"):
        value = profile.get(field)
        if value and not contact.get(field):
            contact[field] = value
            stats[f"{field}_added"] += 1

    summary = profile.get("summary")
    if summary:
        description = str(record.get("description") or "")
        if fold(summary[:80]) not in fold(description):
            record["description"] = clean_text(
                f"{description} Avalik tootjaprofiil lisab: {summary}"
            )
            stats["description_updated"] += 1

    if not has_source(record, str(profile["source_url"])):
        record.setdefault("sources", []).append(
            {
                "source_id": RUN_SOURCE_ID,
                "ref": profile["source_url"],
                "verification_note": (
                    f"Matched public profile from {profile['source_name']} "
                    f"with score {score}; used only source-visible products, "
                    "tags and missing contact fields."
                ),
            }
        )
        stats["sources_added"] += 1
    return dict(stats)


def collect_profiles() -> list[dict[str, Any]]:
    fetchers = [loode_profiles, umamekk_profiles, talutoit_profiles, sibulatee_profiles, minusaaremaa_profiles]
    profiles: list[dict[str, Any]] = []
    for fetcher in fetchers:
        fetched = fetcher()
        print(f"{fetcher.__name__}: {len(fetched)} profiles")
        profiles.extend(fetched)
    return profiles


def main() -> None:
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    records = data.get("records") or []
    profiles = collect_profiles()

    stats = Counter()
    by_source = Counter()
    unmatched = Counter()
    matched_record_ids: set[str] = set()

    for profile in profiles:
        record, score = match_profile(profile, records)
        if not record:
            unmatched[str(profile.get("source_name") or "unknown")] += 1
            continue
        changed = apply_profile(record, profile, score)
        if changed:
            matched_record_ids.add(str(record.get("id")))
            by_source[str(profile.get("source_name") or "unknown")] += 1
            stats.update(changed)

    meta = data.setdefault("meta", {})
    enrichment = meta.setdefault("enrichment_2026_05", {})
    enrichment["additional_public_sources"] = {
        "method": (
            "Searched and fetched additional public producer directories, then "
            "matched profiles to existing geocoded records by strict name/contact "
            "evidence. No new ungeocoded records were created."
        ),
        "profiles_collected": len(profiles),
        "records_matched": len(matched_record_ids),
        "profile_matches_by_source": dict(by_source),
        "unmatched_profiles_by_source": dict(unmatched),
        "fields_changed": dict(stats),
        "sources": PUBLIC_SOURCE_NOTES,
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    meta["generated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    meta["record_count"] = len(records)

    DATASET.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    print(f"profiles collected: {len(profiles)}")
    print(f"records matched: {len(matched_record_ids)}")
    print(f"matches by source: {dict(by_source)}")
    print(f"unmatched by source: {dict(unmatched)}")
    print(f"fields changed: {dict(stats)}")


if __name__ == "__main__":
    main()
