"""Add more source-backed farms, shops, food places, and events.

The script uses public directories that already expose coordinates:
- Eesti Toidutee provider catalog
- Sibulatee member catalog
- a small curated set of Eesti Toidutee 2026 event listings with fixed venues

It avoids creating records from source entries that already match an existing
record name closely enough.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data_pipeline" / "Full farm data.json"
USER_AGENT = "TaluGPT extra public records (+https://github.com/AARenor/talugpt)"
SOURCE_ID = "extra-public-records-2026-05"
EVENT_SOURCE_ID = "toidutee-events-2026-05"
UMAMEKK_SOURCE_ID = "umamekk-public-2026-05"


FOOD_TERMS = [
    "kohalik toit",
    "talupood",
    "pood",
    "kohvik",
    "restoran",
    "toitlustus",
    "degusteerimine",
    "õpituba",
    "mesi",
    "mesindus",
    "piim",
    "juust",
    "jäätis",
    "liha",
    "kala",
    "suitsukala",
    "leib",
    "pagarikoda",
    "pagaritooted",
    "köögivili",
    "sibul",
    "marjad",
    "puuviljad",
    "maitsetaimed",
    "ravimtaimed",
    "siider",
    "vein",
    "õlu",
    "pruulikoda",
    "kalapood",
    "koduköök",
    "kodukohvik",
    "pirukad",
]


def clean_text(text: Any) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(text))).strip()


def strip_html(raw: str) -> str:
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", raw)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p>|</div>|</li>|</tr>|</h[1-6]>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    return clean_text(text)


def quote_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    netloc = parts.netloc.encode("idna").decode("ascii")
    path = urllib.parse.quote(parts.path, safe="/%")
    query = urllib.parse.quote(parts.query, safe="=&%/:;,+@")
    fragment = urllib.parse.quote(parts.fragment, safe="=&%/:;,+@")
    return urllib.parse.urlunsplit((parts.scheme, netloc, path, query, fragment))


def fetch_text(url: str) -> str:
    request = urllib.request.Request(quote_url(url), headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=22) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read(3_000_000).decode(charset, errors="replace")
    except (TimeoutError, OSError, urllib.error.URLError):
        return ""


def fetch_json(url: str) -> Any:
    return json.loads(fetch_text(url))


def fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    text = text.replace("õ", "o").replace("š", "s").replace("ž", "z")
    return text


LEGAL_WORDS = {
    "as",
    "fie",
    "mtu",
    "mtü",
    "ou",
    "oü",
    "sa",
    "tu",
    "tuh",
    "tüh",
    "osaühing",
    "aktsiaselts",
    "sihtasutus",
}

SOFT_WORDS = {
    "talu",
    "talupood",
    "kohvik",
    "restoran",
    "resto",
    "pood",
    "korts",
    "kõrts",
    "kulalistemaja",
    "külalistemaja",
}


def name_words(text: str, drop_soft: bool = True) -> list[str]:
    folded = fold(text)
    words = re.sub(r"[^a-z0-9]+", " ", folded).split()
    blocked = LEGAL_WORDS | (SOFT_WORDS if drop_soft else set())
    return [word for word in words if word not in blocked]


def raw_name_key(text: str) -> str:
    return " ".join(name_words(text, drop_soft=False))


def name_key(text: str) -> str:
    return " ".join(name_words(text, drop_soft=True))


def token_set(text: str) -> set[str]:
    return {word for word in name_words(text) if len(word) >= 3}


def is_existing_name(name: str, records: list[dict[str, Any]]) -> bool:
    raw = raw_name_key(name)
    key = name_key(name)
    tokens = token_set(name)
    for record in records:
        existing = str(record.get("display_name") or record.get("name") or "")
        eraw = raw_name_key(existing)
        ekey = name_key(existing)
        etokens = token_set(existing)
        if raw and eraw and (raw == eraw or (len(raw) >= 7 and (raw in eraw or eraw in raw))):
            return True
        if key and ekey and (key == ekey or (len(key) >= 8 and (key in ekey or ekey in key))):
            return True
        if tokens and etokens:
            overlap = len(tokens & etokens)
            union = len(tokens | etokens)
            if overlap >= 2 and overlap / union >= 0.75:
                return True
    return False


def stable_id(seed: str) -> str:
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def slugify(text: str, suffix: str) -> str:
    slug = fold(text)
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return f"{slug[:72].strip('-')}-{suffix[:6]}"


def unique(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = clean_text(value)
        if value and value.casefold() not in seen:
            output.append(value)
            seen.add(value.casefold())
    return output


def extract_email(raw: str) -> str | None:
    emails = re.findall(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", html.unescape(raw), re.I)
    cleaned = unique([email.strip().casefold() for email in emails])
    return cleaned[-1] if cleaned else None


def extract_phone(raw: str) -> str | None:
    text = html.unescape(raw)
    patterns = [
        r"(?i)(?:kontakttelefon|telefon|phone|mobiil|tel\.?)\s*[:.]?\s*((?:(?:\+|00)?372[\s().-]*)?(?:\d[\s().-]*){7,8})",
        r"(?<![\d.,:-])((?:\+|00)?372[\s().-]*(?:\d[\s().-]*){7,8})(?![\d.,:-])",
        r"(?<![\d.,:-])([3-8]\d(?:[\s().-]*\d){5,6})(?![\d.,:-])",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            candidate = match.group(1)
            digits = re.sub(r"\D", "", candidate)
            if digits.startswith("00372"):
                digits = digits[2:]
            if digits.startswith("372"):
                digits = digits[3:]
            if len(digits) in {7, 8} and digits[0] in "345678":
                return f"+372 {digits}"
    return None


def extract_website(block: str, base_url: str) -> str | None:
    for href in re.findall(r"""href=["']([^"']+)["']""", block, re.I):
        href = html.unescape(href)
        if href.startswith(("mailto:", "tel:", "#", "javascript:")):
            continue
        url = urllib.parse.urljoin(base_url, href)
        host = urllib.parse.urlparse(url).netloc.casefold()
        if not host or "toidutee.ee" in host or "sibulatee.ee" in host:
            continue
        if any(bad in host for bad in ["google", "gstatic", "facebook.com/sharer"]):
            continue
        return urllib.parse.urlunparse(urllib.parse.urlparse(url)._replace(fragment=""))
    return None


def tags_from_text(text: str, categories: list[str]) -> list[str]:
    blob = f"{text} {' '.join(categories)}".casefold()
    tags = ["kohalik toit", "otse tootjalt", *categories]
    for term in FOOD_TERMS:
        if term.casefold() in blob:
            tags.append(term)
    return unique(tags)[:36]


def food_categories_from_text(text: str, categories: list[str]) -> list[str]:
    blob = f"{text} {' '.join(categories)}".casefold()
    cats: list[str] = []
    if any(word in blob for word in ["kohvik", "restoran", "resto", "toitlustus", "trahter", "kõrts"]):
        cats.append("restaurant_cafe")
    if any(word in blob for word in ["pood", "talupood", "müük", "osta"]):
        cats.append("shop")
    if any(word in blob for word in ["piim", "juust", "meierei", "jäätis"]):
        cats.append("dairy")
    if any(word in blob for word in ["kala", "kalapood"]):
        cats.append("fish")
    if any(word in blob for word in ["liha", "vorst", "sink"]):
        cats.append("meat")
    if any(word in blob for word in ["mesi", "mesindus"]):
        cats.append("honey")
    if any(word in blob for word in ["leib", "pagar", "küpsetis"]):
        cats.append("grain_bakery")
    if any(word in blob for word in ["vein", "siider", "õlu", "pruulikoda"]):
        cats.append("beverages")
    if any(word in blob for word in ["marja", "puuvil", "õun"]):
        cats.append("fruit_berries")
    if any(word in blob for word in ["köögivil", "sibul", "kurk", "tomat"]):
        cats.append("vegetables")
    if any(word in blob for word in ["ravimtaim", "maitsetaim", "tee"]):
        cats.append("herbs_spices")
    return unique(cats) or ["mixed_farm"]


def kind_from_text(name: str, text: str, categories: list[str]) -> str:
    blob = f"{name} {text} {' '.join(categories)}".casefold()
    if any(word in blob for word in ["talupood", "kalapood", "pood", "kauplus", "keskus"]):
        return "shop"
    if any(word in blob for word in ["talu", "farm", "aiand", "mesila", "puukool"]):
        return "farm"
    if any(word in blob for word in ["väiketootja", "pruulikoda", "veinitehas", "siidritalu", "tootmine"]):
        return "producer"
    return "shop"


def kind_label(kind: str) -> str:
    return {
        "farm": "Talu või põllumajandustootja",
        "producer": "Tootja",
        "shop": "Pood või müügikoht",
        "event": "Sündmus",
    }.get(kind, "Toidukoht")


def county_from_address(address: str) -> str | None:
    counties = [
        "Harjumaa",
        "Hiiumaa",
        "Ida-Virumaa",
        "Järvamaa",
        "Jõgevamaa",
        "Lääne-Virumaa",
        "Läänemaa",
        "Pärnumaa",
        "Põlvamaa",
        "Raplamaa",
        "Saaremaa",
        "Tartumaa",
        "Valgamaa",
        "Viljandimaa",
        "Võrumaa",
    ]
    folded = address.casefold()
    for county in counties:
        if county.casefold() in folded:
            return county
    return None


def make_record(
    *,
    name: str,
    source_id: str,
    source_url: str,
    lat: float,
    lng: float,
    text: str,
    categories: list[str],
    address: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    website: str | None = None,
    source_name: str,
) -> dict[str, Any]:
    record_id = stable_id(f"{source_id}|{source_url}|{name}")
    food_categories = food_categories_from_text(text, categories)
    kind = kind_from_text(name, text, categories)
    if "restaurant_cafe" in food_categories and kind == "producer":
        kind = "shop"
    products = unique([*categories, *[term for term in FOOD_TERMS if term.casefold() in text.casefold()]])[:18]
    tags = tags_from_text(text, categories)
    county = county_from_address(address or "")
    description = (
        f"Ülevaade: {name} on avalikus {source_name} kataloogis märgitud kohaliku toidu pakkuja. "
        f"{clean_text(text)[:320]}"
    ).strip()
    return {
        "id": record_id,
        "slug": slugify(name, record_id),
        "name": name,
        "display_name": name,
        "kind": kind,
        "kind_label_et": kind_label(kind),
        "lat": lat,
        "lng": lng,
        "coord_precision": "source_gps",
        "county": county,
        "municipality": None,
        "registry_address": address,
        "food_categories": food_categories,
        "primary_food_category": food_categories[0],
        "tags": tags,
        "consumer_relevance": "direct_sale",
        "description": description,
        "products": products,
        "categories": unique(categories),
        "contact": {"email": email, "phone": phone, "website": website or source_url},
        "data_quality_score": 84,
        "sources": [
            {
                "source_id": source_id,
                "ref": source_url,
                "verification_note": f"Added from {source_name} public catalog with source coordinates.",
            }
        ],
    }


def parse_toidutee() -> list[dict[str, Any]]:
    url = "https://www.toidutee.ee/index.php?id=ettevotted&onpage=all"
    raw = fetch_text(url)
    title_matches = list(re.finditer(r'<h2 class="title"><a href="([^"]+)">([\s\S]*?)</a></h2>', raw))
    profiles: list[dict[str, Any]] = []
    for i, match in enumerate(title_matches):
        start = match.start()
        end = title_matches[i + 1].start() if i + 1 < len(title_matches) else len(raw)
        block = raw[start:end]
        coord = re.search(r'data-cord="([0-9.-]+),([0-9.-]+)"', block)
        if not coord:
            continue
        name = strip_html(match.group(2))
        link = html.unescape(match.group(1))
        category_matches = re.findall(r'<p class="title-small">([\s\S]*?)</p>', block)
        categories = [strip_html(category) for category in category_matches]
        desc_match = re.search(r'<div class="description"><p>([\s\S]*?)</p></div>', block)
        short_desc = strip_html(desc_match.group(1)) if desc_match else ""
        email = extract_email(block)
        phone = extract_phone(block)
        detail_raw = fetch_text(link)
        detail_text = strip_html(detail_raw)
        address = None
        anchor = short_desc[:60]
        if anchor:
            idx = detail_text.find(anchor)
            if idx >= 0:
                tail = detail_text[idx + len(anchor) : idx + len(anchor) + 400]
                address_match = re.search(
                    r"Meeldib! Lisa minu toiduteele\s+(.*?)\s+(?:\+372|[A-Za-z0-9._%+-]+@)",
                    tail,
                )
                if address_match:
                    address = clean_text(address_match.group(1))
        website = extract_website(detail_raw, link)
        desc = short_desc
        more_match = re.search(r"üldinfo Saada päring\s+(.*?)(?:Veateade|Asukoht|Eesti Toidutee ühine väärtus)", detail_text)
        if more_match:
            more = clean_text(more_match.group(1))
            if len(more) > len(desc):
                desc = more
        profiles.append(
            make_record(
                name=name,
                source_id=SOURCE_ID,
                source_url=link,
                lat=float(coord.group(1)),
                lng=float(coord.group(2)),
                text=desc or short_desc,
                categories=categories,
                address=address,
                email=email,
                phone=phone,
                website=website,
                source_name="Eesti Toidutee",
            )
        )
    return profiles


def parse_sibulatee() -> list[dict[str, Any]]:
    base = "https://www.sibulatee.ee"
    categories_raw = fetch_json(f"{base}/wp-json/wp/v2/members_category?per_page=100")
    category_map = {item["id"]: clean_text(item["name"]) for item in categories_raw}
    members = []
    for page in (1, 2):
        members.extend(fetch_json(f"{base}/wp-json/wp/v2/members?per_page=100&page={page}"))
    profiles: list[dict[str, Any]] = []
    for item in members:
        if item.get("lang") != "et":
            continue
        item_categories = [category_map.get(cat_id, "") for cat_id in item.get("members_category") or []]
        if not {"Osta", "Söö"} & set(item_categories):
            continue
        coords = item.get("map_coordinates") or {}
        if not coords.get("latitude") or not coords.get("longitude"):
            continue
        title = strip_html(str((item.get("title") or {}).get("rendered") or ""))
        excerpt = strip_html(str((item.get("excerpt") or {}).get("rendered") or ""))
        content = strip_html(str((item.get("content") or {}).get("rendered") or ""))
        webpage = str(item.get("webpage") or "").strip()
        if webpage and not webpage.startswith(("http://", "https://")):
            webpage = f"https://{webpage}"
        profiles.append(
            make_record(
                name=title,
                source_id=SOURCE_ID,
                source_url=str(item.get("link") or base),
                lat=float(coords["latitude"]),
                lng=float(coords["longitude"]),
                text=f"{excerpt} {content}",
                categories=["Sibulatee", *item_categories],
                address=clean_text(item.get("address") or ""),
                email=clean_text(item.get("email") or "").casefold() or None,
                phone=extract_phone(str(item.get("telefon") or "")),
                website=webpage or None,
                source_name="Sibulatee",
            )
        )
    return profiles


def parse_umamekk() -> list[dict[str, Any]]:
    page_url = "https://umamekk.ee/maitseteteekond/"
    kml_url = "https://www.google.com/maps/d/kml?mid=1JGvXbkTeSFD8QHW8ZdVuZOMy7ZsUajw&forcekml=1"
    raw = fetch_text(page_url)
    heading_matches = list(re.finditer(r"<h3>(.*?)</h3>", raw, flags=re.S | re.I))
    footer_start = raw.find('<div  class="footer"')
    if footer_start < 0:
        footer_start = raw.find("<footer")
    content_end = footer_start if footer_start >= 0 else len(raw)
    sections: list[dict[str, Any]] = []
    for i, match in enumerate(heading_matches):
        start = match.start()
        end = heading_matches[i + 1].start() if i + 1 < len(heading_matches) else content_end
        end = min(end, content_end)
        block = raw[start:end]
        name = strip_html(match.group(1))
        text = strip_html(block)
        hashtags = [tag.replace("-", " ") for tag in re.findall(r"#([^\s#<]+)", text)]
        sections.append(
            {
                "name": name,
                "tokens": token_set(name),
                "text": text,
                "categories": unique(["Uma Mekk", "Maitsete teekond", *hashtags]),
                "email": extract_email(block),
                "phone": extract_phone(block),
                "website": extract_website(block, page_url),
            }
        )

    kml = fetch_text(kml_url)
    profiles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for placemark in re.findall(r"<Placemark>(.*?)</Placemark>", kml, flags=re.S | re.I):
        name_match = re.search(r"<name>(.*?)</name>", placemark, flags=re.S | re.I)
        coord_match = re.search(r"<coordinates>\s*([0-9.-]+),([0-9.-]+),", placemark, flags=re.S | re.I)
        if not name_match or not coord_match:
            continue
        name = strip_html(name_match.group(1))
        if not name:
            continue
        lat = float(coord_match.group(2))
        lng = float(coord_match.group(1))
        key = f"{name_key(name)}|{lat:.5f}|{lng:.5f}"
        if key in seen:
            continue
        seen.add(key)

        desc_match = re.search(r"<description><!\[CDATA\[(.*?)\]\]></description>", placemark, flags=re.S | re.I)
        kml_desc_raw = desc_match.group(1) if desc_match else ""
        kml_desc = strip_html(kml_desc_raw)
        website = None
        url_match = re.search(r"https?://[^\s<]+", html.unescape(kml_desc_raw))
        if url_match:
            website = url_match.group(0).rstrip(".,)")

        tokens = token_set(name)
        best_section = None
        best_score = 0.0
        for section in sections:
            section_tokens = section["tokens"]
            if not tokens or not section_tokens:
                continue
            overlap = len(tokens & section_tokens)
            score = overlap / min(len(tokens), len(section_tokens))
            if score > best_score:
                best_score = score
                best_section = section
        if best_score < 0.75:
            best_section = None

        section_text = str(best_section.get("text") or "") if best_section else ""
        categories = list(best_section.get("categories") or []) if best_section else ["Uma Mekk", "Maitsete teekond"]
        text = clean_text(f"{kml_desc} {section_text}")
        profiles.append(
            make_record(
                name=name,
                source_id=UMAMEKK_SOURCE_ID,
                source_url=page_url,
                lat=lat,
                lng=lng,
                text=text,
                categories=categories,
                address=None,
                email=best_section.get("email") if best_section else None,
                phone=best_section.get("phone") if best_section else None,
                website=(best_section.get("website") if best_section else None) or website,
                source_name="Uma Mekk maitsete teekond",
            )
        )
    return profiles


TOIDUTEE_EVENTS = [
    {
        "name": "Suur Tallinna Toidutänav 2026",
        "date": "2026-05-22",
        "date_end": "2026-05-24",
        "lat": 59.44462,
        "lng": 24.80704,
        "county": "Harjumaa",
        "municipality": "Tallinn",
        "venue": "Tallinna Lauluväljak",
        "description": "Toidutee 2026 sündmuste koondleht märgib Suure Tallinna Toidutänava 22.-24. mail Tallinna Lauluväljakul.",
    },
    {
        "name": "Tallinn Craft Beer Weekend 2026",
        "date": "2026-05-29",
        "date_end": "2026-05-30",
        "lat": 59.44507,
        "lng": 24.75348,
        "county": "Harjumaa",
        "municipality": "Tallinn",
        "venue": "Kultuurikatel",
        "description": "Toidutee 2026 sündmuste koondleht märgib Tallinn Craft Beer Weekendit 29.-30. mail Kultuurikatlas.",
    },
    {
        "name": "Eesti leiva päev ja sügislaat 2026",
        "date": "2026-09-20",
        "lat": 59.43195,
        "lng": 24.63775,
        "county": "Harjumaa",
        "municipality": "Tallinn",
        "venue": "Eesti Vabaõhumuuseum",
        "description": "Toidutee 2026 sündmuste koondleht märgib Eesti leiva päeva ja sügislaada 20. septembril Eesti Vabaõhumuuseumis.",
    },
    {
        "name": "Piiriveere sibula ja kala päev ning seto mihklipäiv 2026",
        "date": "2026-10-03",
        "lat": 59.43195,
        "lng": 24.63775,
        "county": "Harjumaa",
        "municipality": "Tallinn",
        "venue": "Eesti Vabaõhumuuseum",
        "description": "Toidutee 2026 sündmuste koondleht märgib Piiriveere sibula ja kala päeva ning seto mihklipäeva 3. oktoobril Eesti Vabaõhumuuseumis.",
    },
    {
        "name": "Suur Rapla Toidutänav 2026",
        "date": "2026-05-02",
        "lat": 59.00752,
        "lng": 24.79285,
        "county": "Raplamaa",
        "municipality": "Rapla vald",
        "venue": "Rapla kesklinn",
        "description": "Toidutee 2026 sündmuste koondleht märgib Suure Rapla Toidutänava 2. mail Rapla kesklinnas.",
    },
    {
        "name": "XX piimapäev: Piim - päeva pärl! 2026",
        "date": "2026-07-14",
        "lat": 58.7312,
        "lng": 25.7589,
        "county": "Järvamaa",
        "municipality": "Järva vald",
        "venue": "Eesti Piimandusmuuseumi park",
        "description": "Toidutee 2026 sündmuste koondleht märgib XX piimapäeva 14. juulil Eesti Piimandusmuuseumi pargis.",
    },
]


def make_event(seed: dict[str, Any]) -> dict[str, Any]:
    source_url = "https://www.toidutee.ee/208"
    record_id = stable_id(f"{EVENT_SOURCE_ID}|{seed['name']}")
    tags = unique(["sündmus", "toidufestival", "kohalik toit", seed["venue"], seed["county"]])
    products = unique(["Toidusündmus", "Kohalik toit", seed["venue"]])
    record: dict[str, Any] = {
        "id": record_id,
        "slug": slugify(seed["name"], record_id),
        "name": seed["name"],
        "display_name": seed["name"],
        "kind": "event",
        "kind_label_et": "Sündmus",
        "lat": seed["lat"],
        "lng": seed["lng"],
        "coord_precision": "venue",
        "county": seed["county"],
        "municipality": seed.get("municipality"),
        "registry_address": seed["venue"],
        "food_categories": ["event", "restaurant_cafe", "market"],
        "primary_food_category": "event",
        "tags": tags,
        "consumer_relevance": "direct_sale",
        "description": f"Ülevaade: {seed['description']} Soovitus: kontrolli enne minekut korraldaja lehelt ajakava.",
        "products": products,
        "categories": ["Eesti Toidutee 2026 sündmused"],
        "contact": {"email": None, "phone": None, "website": source_url},
        "date": seed["date"],
        "data_quality_score": 82,
        "sources": [
            {
                "source_id": EVENT_SOURCE_ID,
                "ref": source_url,
                "verification_note": "Added from Eesti Toidutee 2026 event roundup; venue coordinates are fixed public venue coordinates.",
            }
        ],
    }
    if seed.get("date_end"):
        record["date_end"] = seed["date_end"]
    return record


def refresh_counts(data: dict[str, Any]) -> None:
    records = data.get("records") or []
    data["counts_by_kind"] = dict(Counter(record.get("kind") or "unknown" for record in records))
    data["counts_by_county"] = dict(Counter(record.get("county") or "unknown" for record in records))
    data["counts_by_primary_food_category"] = dict(
        Counter(record.get("primary_food_category") or "other" for record in records)
    )
    data.setdefault("meta", {})["record_count"] = len(records)
    data["meta"]["generated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def has_source(record: dict[str, Any], source_ids: set[str]) -> bool:
    return any((source.get("source_id") in source_ids) for source in (record.get("sources") or []))


def normalize_contact_phone(phone: Any) -> str | None:
    if not phone:
        return None
    text = str(phone).strip()
    digits = re.sub(r"\D", "", text)
    if digits.startswith("00372"):
        digits = digits[2:]
    if digits.startswith("372"):
        local = digits[3:]
        if len(local) in {7, 8} and local[0] in "345678":
            return f"+372 {local}"
        return None
    if digits.startswith("358"):
        local = digits[3:]
        if len(local) in {8, 9, 10}:
            return f"+358 {local}"
        return None
    if len(digits) in {7, 8} and digits[0] in "345678":
        return f"+372 {digits}"
    return text if text.startswith("+") else None


def sanitize_contact_phones(records: list[dict[str, Any]], stats: Counter) -> None:
    for record in records:
        contact = record.get("contact") or {}
        phone = contact.get("phone")
        if not phone:
            continue
        normalized = normalize_contact_phone(phone)
        if normalized == phone:
            continue
        contact["phone"] = normalized
        if normalized:
            stats["phones_normalized"] += 1
        else:
            stats["invalid_phones_removed"] += 1


def main() -> None:
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    source_ids = {SOURCE_ID, UMAMEKK_SOURCE_ID, EVENT_SOURCE_ID}
    original_records = data.get("records") or []
    records = [record for record in original_records if not has_source(record, source_ids)]
    data["records"] = records
    stats: Counter = Counter()
    stats["removed_previous_source_records"] = len(original_records) - len(records)

    candidates = parse_toidutee()
    stats["toidutee_candidates"] = len(candidates)
    for candidate in candidates:
        if is_existing_name(candidate["display_name"], records):
            stats["toidutee_skipped_existing"] += 1
            continue
        records.append(candidate)
        stats["toidutee_added"] += 1

    sib_candidates = parse_sibulatee()
    stats["sibulatee_candidates"] = len(sib_candidates)
    for candidate in sib_candidates:
        if is_existing_name(candidate["display_name"], records):
            stats["sibulatee_skipped_existing"] += 1
            continue
        records.append(candidate)
        stats["sibulatee_added"] += 1

    umamekk_candidates = parse_umamekk()
    stats["umamekk_candidates"] = len(umamekk_candidates)
    for candidate in umamekk_candidates:
        if is_existing_name(candidate["display_name"], records):
            stats["umamekk_skipped_existing"] += 1
            continue
        records.append(candidate)
        stats["umamekk_added"] += 1

    for event in [make_event(seed) for seed in TOIDUTEE_EVENTS]:
        if is_existing_name(event["display_name"], records):
            stats["events_skipped_existing"] += 1
            continue
        records.append(event)
        stats["events_added"] += 1

    sanitize_contact_phones(records, stats)
    refresh_counts(data)
    data.setdefault("meta", {}).setdefault("enrichment_2026_05", {})["more_public_records"] = {
        "method": (
            "Added more source-backed local food providers from Eesti Toidutee, Sibulatee, "
            "and Uma Mekk where source coordinates were available; added selected 2026 food "
            "events from Eesti Toidutee's event roundup with fixed venue coordinates; "
            "normalized existing phone formats and removed obvious time-range false positives."
        ),
        "fields_changed": dict(stats),
        "sources": [
            "https://www.toidutee.ee/index.php?id=ettevotted&onpage=all",
            "https://www.toidutee.ee/208",
            "https://www.sibulatee.ee/Sibulateelised/",
            "https://www.sibulatee.ee/wp-json/wp/v2/members?per_page=100",
            "https://umamekk.ee/maitseteteekond/",
            "https://www.google.com/maps/d/kml?mid=1JGvXbkTeSFD8QHW8ZdVuZOMy7ZsUajw&forcekml=1",
        ],
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    DATASET.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"record_count": len(records), "stats": dict(stats)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
