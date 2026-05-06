"""Add source-backed 2026 farm events and raw milk pickup points.

This is a targeted enrichment pass. It turns existing Avatud Talude Päev 2026
participant farm records into event pins and adds/updates raw milk shop records
only where public source pages identify the location.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data_pipeline" / "Full farm data.json"
USER_AGENT = "TaluGPT event/raw milk enrichment (+https://github.com/AARenor/talugpt)"

ATP_EVENT_SOURCE_ID = "atp-2026-event-2026-05"
RAW_MILK_SOURCE_ID = "raw-milk-public-2026-05"


def clean_text(text: Any) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(text))).strip()


def strip_html(raw: str) -> str:
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", raw)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p>|</div>|</li>|</tr>|</h[1-6]>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    return clean_text(text)


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=18) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read(1_500_000).decode(charset, errors="replace")
    except (TimeoutError, OSError, urllib.error.URLError):
        return ""


def stable_id(seed: str) -> str:
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def slugify(text: str, suffix: str) -> str:
    slug = text.casefold()
    slug = (
        slug.replace("õ", "o")
        .replace("ä", "a")
        .replace("ö", "o")
        .replace("ü", "u")
        .replace("š", "s")
        .replace("ž", "z")
    )
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return f"{slug[:72].strip('-')}-{suffix[:6]}"


def source_ref(record: dict[str, Any], source_id: str) -> str | None:
    for source in record.get("sources") or []:
        if source.get("source_id") == source_id:
            return str(source.get("ref") or "").split()[0]
    return None


def has_source(record: dict[str, Any], source_id: str, ref: str | None = None) -> bool:
    for source in record.get("sources") or []:
        if source.get("source_id") != source_id:
            continue
        if ref is None or source.get("ref") == ref:
            return True
    return False


def unique_extend(values: list[str], additions: list[str]) -> int:
    changed = 0
    seen = {str(value).casefold() for value in values}
    for value in additions:
        value = clean_text(value)
        if not value or value.casefold() in seen:
            continue
        values.append(value)
        seen.add(value.casefold())
        changed += 1
    return changed


def parse_atp_page(url: str) -> dict[str, Any]:
    raw = fetch_text(url)
    text = strip_html(raw)
    lat = lng = None
    coord_match = re.search(r"GPS-koordinaadid\s+([0-9.]+),\s*([0-9.]+)", text)
    if coord_match:
        lat = float(coord_match.group(1))
        lng = float(coord_match.group(2))

    open_text = ""
    open_match = re.search(r"Avatud\s+(.*?)(?:Programm|Keeleoskus|Kontakt|Asukoht kaardil)", text)
    if open_match:
        open_text = clean_text(open_match.group(1))

    activity = ""
    activity_match = re.search(r"Tegevusala\s+(.*?)(?:Täpsem tegevusala|Avatud|Programm)", text)
    if activity_match:
        activity = clean_text(activity_match.group(1))

    detail_activity = ""
    detail_match = re.search(r"Täpsem tegevusala\s+(.*?)(?:Avatud|Programm|Keeleoskus|Kontakt)", text)
    if detail_match:
        detail_activity = clean_text(detail_match.group(1))

    if "pühapäeval" in open_text.casefold() and "laupäeval" not in open_text.casefold():
        date = "2026-07-26"
        date_end = None
    elif "25.-26.07" in open_text or "laupäeval ja pühapäeval" in open_text.casefold():
        date = "2026-07-25"
        date_end = "2026-07-26"
    else:
        date = "2026-07-25"
        date_end = None

    return {
        "text": text,
        "lat": lat,
        "lng": lng,
        "open_text": open_text,
        "activity": activity,
        "detail_activity": detail_activity,
        "date": date,
        "date_end": date_end,
    }


def event_products(record: dict[str, Any], page: dict[str, Any]) -> list[str]:
    products: list[str] = []
    activity_blob = clean_text(f"{page.get('activity') or ''} {page.get('detail_activity') or ''}")
    for label in [
        "Köögiviljakasvatus",
        "Puuvilja- ja/või marjakasvatus",
        "Ravim- ja maitsetaimede kasvatus",
        "Teraviljakasvatus",
        "Väiketööstus",
        "Meierei",
        "Mesindus",
        "Loomakasvatus",
        "Linnukasvatus",
        "Kalandus",
        "Käsitöö",
        "Maaturism",
        "Iluaiandus",
        "Seened",
        "Veinitalu",
        "Jäätis",
    ]:
        if label.casefold() in activity_blob.casefold():
            products.append(label)
    detail = clean_text(page.get("detail_activity") or "")
    for label in ["Pagarikoda", "Moosid", "Siider", "Õlu"]:
        if label.casefold() in detail.casefold():
            products.append(label)
    if detail and len(detail) <= 90:
        products.append(detail)
    products.extend(str(product) for product in (record.get("products") or [])[:4])
    cleaned = list(dict.fromkeys(clean_text(product) for product in products if clean_text(product)))[:10]
    return cleaned or ["Taluüritus"]


def event_tags(record: dict[str, Any], page: dict[str, Any]) -> list[str]:
    tags = [
        "avatud talude päev",
        "Avatud Talude Päev 2026",
        "sündmus",
        "talukülastus",
        "talutuur",
        "pereüritus",
        "kohalik toit",
        str(record.get("county") or ""),
        str(record.get("municipality") or ""),
    ]
    blob = f"{page.get('activity') or ''} {page.get('detail_activity') or ''}".casefold()
    for needle, tag in [
        ("meierei", "meierei"),
        ("mesindus", "mesi"),
        ("ravim", "ravimtaimed"),
        ("maitsetaim", "maitsetaimed"),
        ("marja", "marjad"),
        ("puuvil", "puuviljad"),
        ("köögivil", "köögiviljad"),
        ("pagar", "pagaritooted"),
        ("siider", "siider"),
        ("vein", "veinitalu"),
        ("kala", "kala"),
        ("seene", "seened"),
        ("jäätis", "jäätis"),
    ]:
        if needle in blob:
            tags.append(tag)
    return [tag for tag in dict.fromkeys(clean_text(tag) for tag in tags) if tag]


def build_atp_event(record: dict[str, Any], url: str) -> dict[str, Any]:
    page = parse_atp_page(url)
    event_id = stable_id(f"{ATP_EVENT_SOURCE_ID}|{url}")
    farm_name = str(record.get("display_name") or record.get("name") or "talu")
    title = f"Avatud talude päev 2026: {farm_name}"
    products = event_products(record, page)
    open_text = page.get("open_text") or "Avatud Talude Päeva ajal"
    activity = page.get("detail_activity") or page.get("activity") or "talu programm"
    description = (
        f"Ülevaade: {farm_name} osaleb Avatud Talude Päeval 2026. "
        f"Avatud: {open_text}. Tegevus: {activity}. "
        "Soovitus: kontrolli enne minekut allikalehelt programmi ja kellaaegu."
    )
    contact = {
        "email": (record.get("contact") or {}).get("email"),
        "phone": (record.get("contact") or {}).get("phone"),
        "website": url,
    }
    event: dict[str, Any] = {
        "id": event_id,
        "slug": slugify(title, event_id),
        "name": title,
        "display_name": title,
        "kind": "event",
        "kind_label_et": "Sündmus",
        "lat": page.get("lat") or record.get("lat"),
        "lng": page.get("lng") or record.get("lng"),
        "coord_precision": "source_gps" if page.get("lat") and page.get("lng") else record.get("coord_precision", "address"),
        "county": record.get("county"),
        "municipality": record.get("municipality"),
        "food_categories": list(dict.fromkeys(["event", *(record.get("food_categories") or [])]))[:5],
        "primary_food_category": "event",
        "tags": event_tags(record, page),
        "consumer_relevance": "direct_sale",
        "description": description,
        "products": products,
        "categories": ["Avatud Talude Päev 2026", "Taluüritus"],
        "contact": contact,
        "date": page["date"],
        "data_quality_score": 88,
        "related_farm_id": record.get("id"),
        "sources": [
            {
                "source_id": ATP_EVENT_SOURCE_ID,
                "ref": url,
                "verification_note": "Created an event pin from the official Avatud Talude Päev 2026 participant profile.",
            }
        ],
    }
    if page.get("date_end"):
        event["date_end"] = page["date_end"]
    return event


RAW_MILK_PRODUCTS = [
    "Toorpiim (raw cow milk)",
    "Pastöriseerimata lehmapiim",
    "Töötlemata piim",
]

RAW_MILK_TAGS = [
    "toorpiim",
    "raw milk",
    "pastöriseerimata piim",
    "töötlemata piim",
    "värske piim",
    "piim otse tootjalt",
    "müügikoht",
    "kohalik toit",
]


RAW_MILK_UPDATES = [
    {
        "name": "Väike-Järve Taluturg",
        "ref": "https://getrawmilk.com/map/vaike-jarve-taluturg-tallinn",
        "note": "GetRawMilk listing identifies Väike-Järve Taluturg as a Tallinn raw cow milk delivery/pickup location.",
        "contact": {"phone": "+372 58302700", "website": "https://taluturg.ee/"},
    },
    {
        "name": "Pärnu Keskuse Taluturg",
        "ref": "https://getrawmilk.com/map/parnu-keskuse-taluturg-parnu",
        "note": "GetRawMilk listing identifies Pärnu Keskuse Taluturg as a raw cow milk delivery/pickup location.",
        "contact": {"phone": "+372 58171504", "website": "https://taluturg.ee/"},
        "products": ["Mätiku talu toorpiim 1L"],
    },
    {
        "name": "Tartu Kaubamaja Taluturg",
        "ref": "https://taluturg.ee/product-tag/toorpiim/",
        "note": "Taluturg toorpiim product tag and product pages list raw milk products with Tartu availability.",
        "contact": {"website": "https://taluturg.ee/"},
        "products": ["Pajumäe mahe-toorpiim", "Nopri toorpiim 1L"],
    },
    {
        "name": "Põlva Maksimarket",
        "ref": "https://getrawmilk.com/map/polva-maksimarket-polva",
        "note": "GetRawMilk listing identifies Põlva Maksimarket as a raw cow milk pickup location.",
        "contact": {"phone": "+372 7999088", "website": "https://www.coop.ee/polva-maksimarket"},
    },
]


RAW_MILK_NEW_RECORDS = [
    {
        "name": "Solaris Keskuse Taluturg (toorpiima müügipunkt)",
        "lat": 59.4333055,
        "lng": 24.7514511,
        "county": "Harjumaa",
        "municipality": "Tallinn",
        "registry_address": "Estonia pst 9, Tallinn",
        "ref": "https://getrawmilk.com/search/Tallinn",
        "note": "GetRawMilk search result lists Taluturg Delivery Location at Estonia pst 9, Tallinn as a raw cow milk source; Taluturg product catalog lists toorpiim products.",
        "contact": {"website": "https://taluturg.ee/"},
    }
]


def apply_raw_milk(record: dict[str, Any], update: dict[str, Any]) -> Counter:
    stats: Counter = Counter()
    stats["products_added"] += unique_extend(record.setdefault("products", []), [*RAW_MILK_PRODUCTS, *update.get("products", [])])
    stats["tags_added"] += unique_extend(record.setdefault("tags", []), RAW_MILK_TAGS)
    stats["categories_added"] += unique_extend(record.setdefault("categories", []), ["Toorpiima müügikoht"])
    record["consumer_relevance"] = "direct_sale"
    if "shop" not in record.get("food_categories", []):
        record.setdefault("food_categories", []).append("shop")
    if "dairy" not in record.get("food_categories", []):
        record.setdefault("food_categories", []).insert(0, "dairy")
    record["primary_food_category"] = "dairy"
    contact = record.setdefault("contact", {"email": None, "phone": None, "website": None})
    for field, value in (update.get("contact") or {}).items():
        if value and not contact.get(field):
            contact[field] = value
            stats[f"{field}_added"] += 1
    desc = str(record.get("description") or "")
    sentence = "Avalik toorpiima allikas märgib selle asukoha toorpiima müügikohana."
    if sentence not in desc:
        record["description"] = clean_text(f"{desc} {sentence}")
        stats["description_updated"] += 1
    if not has_source(record, RAW_MILK_SOURCE_ID, update["ref"]):
        record.setdefault("sources", []).append(
            {
                "source_id": RAW_MILK_SOURCE_ID,
                "ref": update["ref"],
                "verification_note": update["note"],
            }
        )
        stats["sources_added"] += 1
    return stats


def make_raw_milk_record(seed: dict[str, Any]) -> dict[str, Any]:
    record_id = stable_id(f"{RAW_MILK_SOURCE_ID}|{seed['name']}")
    return {
        "id": record_id,
        "slug": slugify(seed["name"], record_id),
        "name": seed["name"],
        "display_name": seed["name"],
        "kind": "shop",
        "kind_label_et": "Pood või müügikoht",
        "lat": seed["lat"],
        "lng": seed["lng"],
        "coord_precision": "address",
        "county": seed["county"],
        "municipality": seed["municipality"],
        "registry_address": seed["registry_address"],
        "food_categories": ["dairy", "shop"],
        "primary_food_category": "dairy",
        "tags": RAW_MILK_TAGS + ["Tallinn", "Taluturg"],
        "consumer_relevance": "direct_sale",
        "description": (
            f"Ülevaade: {seed['name']} on Taluturu müügikoht, mida avalik toorpiima allikas "
            "märgib toorpiima ostukohana. Soovitus: kontrolli saadavust enne minekut."
        ),
        "products": RAW_MILK_PRODUCTS,
        "categories": ["Toorpiima müügikoht", "Taluturg"],
        "contact": seed.get("contact") or {"email": None, "phone": None, "website": "https://taluturg.ee/"},
        "data_quality_score": 82,
        "sources": [
            {
                "source_id": RAW_MILK_SOURCE_ID,
                "ref": seed["ref"],
                "verification_note": seed["note"],
            },
            {
                "source_id": RAW_MILK_SOURCE_ID,
                "ref": "https://taluturg.ee/product-tag/toorpiim/",
                "verification_note": "Taluturg product catalog lists toorpiim products.",
            },
        ],
    }


def refresh_counts(data: dict[str, Any]) -> None:
    records = data.get("records") or []
    data["counts_by_kind"] = dict(Counter(record.get("kind") or "unknown" for record in records))
    data["counts_by_county"] = dict(Counter(record.get("county") or "unknown" for record in records))
    data["counts_by_primary_food_category"] = dict(
        Counter(record.get("primary_food_category") or "other" for record in records)
    )
    meta = data.setdefault("meta", {})
    meta["record_count"] = len(records)
    meta["generated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main() -> None:
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    records = data.get("records") or []
    existing_ids = {record.get("id") for record in records}
    existing_names = {str(record.get("display_name") or record.get("name") or "").casefold() for record in records}

    stats: Counter = Counter()

    atp_records = [record for record in records if source_ref(record, "atp-2026")]
    for record in atp_records:
        url = source_ref(record, "atp-2026")
        if not url:
            continue
        event = build_atp_event(record, url)
        if event["id"] in existing_ids:
            continue
        records.append(event)
        existing_ids.add(event["id"])
        stats["events_added"] += 1

    records_by_name = {
        str(record.get("display_name") or record.get("name") or "").casefold(): record
        for record in records
    }
    for update in RAW_MILK_UPDATES:
        record = records_by_name.get(update["name"].casefold())
        if not record:
            continue
        changed = apply_raw_milk(record, update)
        stats.update({f"raw_{key}": value for key, value in changed.items()})
        stats["raw_locations_updated"] += 1

    for seed in RAW_MILK_NEW_RECORDS:
        if seed["name"].casefold() in existing_names:
            continue
        record = make_raw_milk_record(seed)
        records.append(record)
        existing_names.add(seed["name"].casefold())
        stats["raw_locations_added"] += 1

    refresh_counts(data)
    data.setdefault("meta", {}).setdefault("enrichment_2026_05", {})["events_and_raw_milk"] = {
        "method": (
            "Added event records from official Avatud Talude Päev 2026 participant pages and "
            "added/updated raw milk pickup points from GetRawMilk and Taluturg public pages."
        ),
        "atp_participant_records_seen": len(atp_records),
        "fields_changed": dict(stats),
        "sources": [
            "https://avatudtalud.ee/et/",
            "https://avatudtalud.ee/et/kulastajale/",
            "https://getrawmilk.com/map/vaike-jarve-taluturg-tallinn",
            "https://getrawmilk.com/map/parnu-keskuse-taluturg-parnu",
            "https://getrawmilk.com/map/polva-maksimarket-polva",
            "https://getrawmilk.com/search/Tallinn",
            "https://taluturg.ee/product-tag/toorpiim/",
        ],
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }

    DATASET.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"record_count": len(records), "stats": dict(stats)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
