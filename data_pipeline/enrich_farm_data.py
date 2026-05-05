"""Enrich TaluGPT farm records with safer descriptions and search tags.

The enrichment is deterministic: it only uses fields already present in the
dataset plus project-level public-source research notes. It does not invent
record-level products, hours, prices, or contacts.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FULL_DATASET = ROOT / "data_pipeline" / "Full farm data.json"

CATEGORY_LABELS: dict[str, str] = {
    "beverages": "joogid ja kohalikud joogid",
    "cosmetics_crafts": "käsitöö ja talukaup",
    "dairy": "piim ja piimatooted",
    "eggs": "munad",
    "event": "toidu- või maaelusündmus",
    "fish": "kala ja kalatooted",
    "fruit_berries": "marjad ja puuviljad",
    "grain_bakery": "teravili ja pagaritooted",
    "herbs_spices": "maitsetaimed ja ravimtaimed",
    "honey": "mesi ja mesindus",
    "market": "turg või laat",
    "meat": "liha ja loomakasvatus",
    "mixed_farm": "mitmekesine talutoodang",
    "mushrooms": "seened",
    "other": "muu kohalik toit",
    "restaurant_cafe": "kohvik, restoran või toitlustus",
    "shop": "talupood või müügikoht",
    "vegetables": "köögiviljad ja aiandussaadused",
}

KIND_LABELS: dict[str, str] = {
    "event": "sündmus",
    "farm": "talu või põllumajandustootja",
    "market": "turg või laat",
    "producer": "väiketootja",
    "shop": "pood või müügikoht",
}

SOURCE_LABELS: list[tuple[str, str]] = [
    ("pta", "PTA mahepõllumajanduse register"),
    ("arireg", "e-äriregister"),
    ("atp", "Avatud Talude Päev"),
    ("avatudtalud", "Avatud Talude Päev"),
    ("kohaliktoit", "Kohalik Toit võrgustik"),
    ("maaturism", "Kohalik Toit võrgustik"),
    ("laadakalender", "Laadakalender"),
    ("epkk", "EPKK"),
    ("umamekk", "Uma Mekk"),
    ("virutoit", "Viru Toit"),
    ("maainfo", "Maainfo"),
    ("nominatim", "Nominatim geokodeerimine"),
]

WEB_RESEARCH_SOURCES: list[dict[str, str]] = [
    {
        "name": "PTA / Regionaal- ja Põllumajandusministeerium mahepõllumajanduse info",
        "url": "https://www.agri.ee/maaelu-pollumajandus-toiduturg/pollumajandus-ja-toiduturg/mahepollumajandus",
        "use": "mahe, sertifikaadi ja registripõhise märgistuse sõnavara",
    },
    {
        "name": "Kohalik Toit / Eesti Maaturism tootjate andmebaas",
        "url": "https://kohaliktoit.maaturism.ee/et/tootjate-andmebaas",
        "use": "tarbijale suunatud kohaliku toidu, tootjate ja talupoodide sõnavara",
    },
    {
        "name": "Avatud Talude Päev",
        "url": "https://avatudtalud.ee/",
        "use": "külastus-, talutuuri-, kodukohviku- ja sündmusesõnavara",
    },
    {
        "name": "Maainfo piirkondlik toit ja toiduvõrgustikud",
        "url": "https://www.maainfo.ee/",
        "use": "piirkondliku toidu ja võrgustike üldsõnavara",
    },
]

LOW_SIGNAL_TERMS = {
    "karjatamine väljaspool põllumajandusmaad",
    "liblikõieliste ja kõrreliste segu",
    "muu heintaimede segu",
    "kõrreliste rohumaa",
    "lühiajaline rohumaa",
    "püsirohumaa",
    "rohttaimed",
    "punane ristik",
}

FALSE_DAIRY_TAGS = {
    "piim",
    "piima",
    "piimatooted",
    "piimatoode",
    "meierei",
    "talumeierei",
    "lüpsilehm",
    "lüpsilehmad",
}

COFFEE_TAGS = {"kohv", "kohvik", "kohvikud", "kohalik kohvik"}

CATEGORY_EVIDENCE: dict[str, re.Pattern[str]] = {
    "dairy": re.compile(
        r"\b(toorpiim|piim|piima|piimatood|piimatoode|lüpsi|lüpsilehm|"
        r"lehmapiim|kitsepiim|lambapiim|juust|jogurt|kohupiim|jäätis|koor)\b",
        re.IGNORECASE,
    ),
    "eggs": re.compile(
        r"\b(muna|munad|munakana|munakanad|kanamuna|vutimuna|kodulinnud)\b",
        re.IGNORECASE,
    ),
    "honey": re.compile(
        r"\b(mesi|mee|mesila|mesindus|mesilaspere|mesilased|mesindussaadus)\b",
        re.IGNORECASE,
    ),
    "meat": re.compile(
        r"\b(liha|lihatoot|lihaveis|veised|veis|lambad|lammas|kitsed|kits|"
        r"sead|siga|küülik|uluk|lihaveisekasvatus|lambakasvatus)\b",
        re.IGNORECASE,
    ),
    "vegetables": re.compile(
        r"\b(kartul|köögivili|aedvili|juurvili|kapsas|küüslauk|sibul|"
        r"porgand|peet|kurk|tomat|kõrvits|salat|avamaa köögivili)\b",
        re.IGNORECASE,
    ),
    "fruit_berries": re.compile(
        r"\b(marja|marjad|maasik|vaarik|mustik|astelpaju|õun|õunapuu|"
        r"pirn|ploom|kirss|sõstar|aroonia|puuvilj|viljapuu)\b",
        re.IGNORECASE,
    ),
    "grain_bakery": re.compile(
        r"\b(teravili|kaer|nisu|rukis|oder|tatar|spelta|leib|sai|pagar|"
        r"pagaritoode|jahu|helbed|kondiitri)\b",
        re.IGNORECASE,
    ),
    "herbs_spices": re.compile(
        r"\b(maitsetaim|ravimtaim|ürd|ürdid|taimetee|teeürdid)\b",
        re.IGNORECASE,
    ),
    "beverages": re.compile(
        r"\b(siider|mahl|vein|õlu|joogid|jook|limonaad|kohv|tee|kakao|"
        r"käsitöösiider|koduvein)\b",
        re.IGNORECASE,
    ),
    "fish": re.compile(r"\b(kala|kalatoot|forell|angerjas|tuulekala|lõhe)\b", re.IGNORECASE),
    "mushrooms": re.compile(r"\b(seen|seened|seenefarm|austerservik|shiitake)\b", re.IGNORECASE),
    "restaurant_cafe": re.compile(
        r"\b(kohvik|kodukohvik|restoran|toitlustus|tänavatoit|foodtruck|"
        r"toidutänav|maitsete)\b",
        re.IGNORECASE,
    ),
    "market": re.compile(r"\b(turg|laat|taluturg|müügipäev|turupäev)\b", re.IGNORECASE),
    "event": re.compile(r"\b(sündmus|festival|avatud talude päev|programm)\b", re.IGNORECASE),
    "shop": re.compile(r"\b(talupood|pood|kauplus|müügikoht|toidupood)\b", re.IGNORECASE),
    "cosmetics_crafts": re.compile(r"\b(käsitöö|kosmeetika|seep|vill|küünal)\b", re.IGNORECASE),
}

TAG_RULES: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"\btoorpiim\b", re.IGNORECASE), ["toorpiim", "värske piim", "piim otse tootjalt"]),
    (re.compile(r"\bkitsepiim|kitsejuust|kitsed?\b", re.IGNORECASE), ["kitsed", "kitsekasvatus"]),
    (re.compile(r"\blambad?|lambaliha\b", re.IGNORECASE), ["lambad", "lambakasvatus"]),
    (re.compile(r"\bveised?|lihaveis|ammlehm|noorveis\b", re.IGNORECASE), ["veised", "veisekasvatus"]),
    (re.compile(r"\bmunakana|kanamuna|vutimuna|munad?\b", re.IGNORECASE), ["munad", "munakanad"]),
    (re.compile(r"\bmesilaspere|mesila|mesi|mesindus\b", re.IGNORECASE), ["mesi", "mesindus", "mesila"]),
    (re.compile(r"\bkartul\b", re.IGNORECASE), ["kartul", "köögivili", "juurvili"]),
    (re.compile(r"\bküüslauk\b", re.IGNORECASE), ["küüslauk", "köögivili", "maitsevili"]),
    (re.compile(r"\bmaasik", re.IGNORECASE), ["maasikad", "marjad"]),
    (re.compile(r"\bmustik", re.IGNORECASE), ["mustikad", "marjad"]),
    (re.compile(r"\bvaarik", re.IGNORECASE), ["vaarikad", "marjad"]),
    (re.compile(r"\bastelpaju\b", re.IGNORECASE), ["astelpaju", "marjad"]),
    (re.compile(r"\bõun|õunapuu\b", re.IGNORECASE), ["õunad", "puuviljad"]),
    (re.compile(r"\bkaer\b", re.IGNORECASE), ["kaer", "teravili"]),
    (re.compile(r"\bnisu|suvinisu|talinisu\b", re.IGNORECASE), ["nisu", "teravili"]),
    (re.compile(r"\brukis|talirukis\b", re.IGNORECASE), ["rukis", "teravili"]),
    (re.compile(r"\btatar\b", re.IGNORECASE), ["tatar", "teravili"]),
    (re.compile(r"\bmaitsetaim|ravimtaim|ürd", re.IGNORECASE), ["maitsetaimed", "ürdid", "ravimtaimed"]),
    (re.compile(r"\bseen|seened|seenefarm\b", re.IGNORECASE), ["seened", "seenefarm"]),
    (re.compile(r"\bkala|forell|angerjas|tuulekala\b", re.IGNORECASE), ["kala", "kalatooted"]),
    (re.compile(r"\bsiider|mahl|vein|õlu|limonaad\b", re.IGNORECASE), ["joogid", "kohalikud joogid"]),
    (re.compile(r"\bkohvik|kodukohvik|restoran|toitlustus\b", re.IGNORECASE), ["kohvik", "toitlustus"]),
    (re.compile(r"\bavatud talude päev|talutuur|ekskursioon\b", re.IGNORECASE), ["avatud talude päev", "külastus", "talutuur"]),
    (re.compile(r"\blasteala|lastele|ponisõit|loomad|miniloomaaed\b", re.IGNORECASE), ["lastega külastus", "taluloomad"]),
]

TAG_PRIORITY = [
    "toorpiim",
    "värske piim",
    "piim otse tootjalt",
    "talupood",
    "müügikoht",
    "turg",
    "laat",
    "avatud talude päev",
    "külastus",
    "talutuur",
    "piim",
    "piimatooted",
    "liha",
    "lihatooted",
    "munad",
    "mesi",
    "köögivili",
    "marjad",
    "puuviljad",
    "teravili",
    "pagaritooted",
    "maitsetaimed",
    "kala",
    "seened",
    "joogid",
    "kohvik",
    "toitlustus",
    "mahe",
    "mahesertifikaat",
    "mahetootja",
    "otse talust",
    "otse müük",
    "kontakt olemas",
    "veebileht",
]


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if value is None or value == "":
        return []
    return [str(value).strip()]


def text_blob(record: dict[str, Any], include_name: bool = False) -> str:
    parts: list[str] = []
    if include_name:
        parts.extend([str(record.get("display_name") or ""), str(record.get("name") or "")])
    parts.extend(as_list(record.get("products")))
    parts.extend(as_list(record.get("categories")))
    parts.append(str(record.get("description") or ""))
    return normalize_space(" ".join(parts))


def category_evidence_text(record: dict[str, Any]) -> str:
    parts: list[str] = []
    parts.extend(as_list(record.get("products")))
    parts.extend(as_list(record.get("categories")))
    description = str(record.get("description") or "")
    if description and not is_generic_description(description):
        parts.append(description)
    return normalize_space(" ".join(parts))


def source_ids(record: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for source in record.get("sources") or []:
        if isinstance(source, dict):
            ids.append(str(source.get("source_id") or ""))
            ids.append(str(source.get("ref") or ""))
    return ids


def add_unique(tags: list[str], new_tags: list[str]) -> list[str]:
    seen = {t.casefold() for t in tags}
    for tag in new_tags:
        clean = normalize_space(tag)
        if not clean:
            continue
        key = clean.casefold()
        if key not in seen:
            tags.append(clean)
            seen.add(key)
    return tags


def remove_tag(tags: list[str], bad_tags: set[str]) -> list[str]:
    bad = {t.casefold() for t in bad_tags}
    return [tag for tag in tags if tag.casefold() not in bad]


def category_tags(food_categories: list[str]) -> list[str]:
    tags: list[str] = []
    for category in food_categories:
        label = CATEGORY_LABELS.get(category)
        if not label:
            continue
        if category == "dairy":
            tags.extend(["piim", "piimatooted"])
        elif category == "meat":
            tags.extend(["liha", "lihatooted", "loomakasvatus"])
        elif category == "eggs":
            tags.extend(["munad"])
        elif category == "honey":
            tags.extend(["mesi", "mesindus"])
        elif category == "vegetables":
            tags.extend(["köögivili", "aedviljad"])
        elif category == "fruit_berries":
            tags.extend(["marjad", "puuviljad"])
        elif category == "grain_bakery":
            tags.extend(["teravili", "pagaritooted"])
        elif category == "herbs_spices":
            tags.extend(["maitsetaimed", "ürdid", "ravimtaimed"])
        elif category == "beverages":
            tags.extend(["joogid", "kohalikud joogid"])
        elif category == "fish":
            tags.extend(["kala", "kalatooted"])
        elif category == "mushrooms":
            tags.extend(["seened"])
        elif category == "restaurant_cafe":
            tags.extend(["kohvik", "toitlustus"])
        elif category == "shop":
            tags.extend(["talupood", "müügikoht"])
        elif category in {"market", "event"}:
            tags.extend(["turg" if category == "market" else "sündmus", "laat"])
    return tags


def infer_categories(record: dict[str, Any]) -> list[str]:
    existing = as_list(record.get("food_categories"))
    text = category_evidence_text(record)
    inferred = [cat for cat, pattern in CATEGORY_EVIDENCE.items() if pattern.search(text)]
    merged = add_unique(existing[:], inferred)

    if "dairy" in merged and not CATEGORY_EVIDENCE["dairy"].search(text):
        merged = [cat for cat in merged if cat != "dairy"]

    if record.get("kind") == "shop":
        merged = add_unique(merged, ["shop"])
    if record.get("kind") == "market":
        merged = add_unique(merged, ["market"])
    if record.get("kind") == "event":
        merged = add_unique(merged, ["event"])

    if not merged:
        merged = ["other"]

    return merged


def choose_primary(food_categories: list[str]) -> str:
    priority = [
        "dairy",
        "meat",
        "eggs",
        "honey",
        "vegetables",
        "fruit_berries",
        "grain_bakery",
        "herbs_spices",
        "fish",
        "mushrooms",
        "beverages",
        "restaurant_cafe",
        "shop",
        "market",
        "event",
        "mixed_farm",
        "cosmetics_crafts",
        "other",
    ]
    for category in priority:
        if category in food_categories:
            return category
    return "other"


def source_labels(record: dict[str, Any], limit: int = 3) -> list[str]:
    labels: list[str] = []
    text = " ".join(source_ids(record)).casefold()
    for needle, label in SOURCE_LABELS:
        if needle in text:
            labels = add_unique(labels, [label])
    return labels[:limit]


def useful_terms(record: dict[str, Any], limit: int = 7) -> list[str]:
    terms: list[str] = []
    for term in as_list(record.get("products")) + as_list(record.get("categories")):
        clean = normalize_space(term)
        if not clean:
            continue
        if clean.casefold() in LOW_SIGNAL_TERMS:
            continue
        if re.search(r"^(ammlehmad|noorveised|vasikad|tõupullid|lambad|kitsed|munakanad)", clean, re.I):
            terms = add_unique(terms, [clean])
        elif len(clean) <= 38 and not re.search(r"\d", clean):
            terms = add_unique(terms, [clean])
    return terms[:limit]


def contact_labels(record: dict[str, Any]) -> list[str]:
    contact = record.get("contact") if isinstance(record.get("contact"), dict) else {}
    labels: list[str] = []
    if contact.get("website"):
        labels.append("veebileht")
    if contact.get("phone"):
        labels.append("telefon")
    if contact.get("email"):
        labels.append("e-post")
    return labels


def is_generic_description(description: str) -> bool:
    generic_markers = [
        "Andmestikus on selle kirje juures esile toodud",
        "Kirje on märgitud",
        "piirkonnas tegutsev",
        "Sertifikaadid/märked",
    ]
    return any(marker in description for marker in generic_markers)


def sentence_trim(text: str, limit: int) -> str:
    text = normalize_space(text)
    if len(text) <= limit:
        return text

    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept: list[str] = []
    total = 0
    for sentence in sentences:
        if not sentence:
            continue
        projected = total + len(sentence) + (1 if kept else 0)
        if kept and projected > limit:
            break
        kept.append(sentence)
        total = projected

    if kept:
        return normalize_space(" ".join(kept))

    cut = text[:limit].rsplit(" ", 1)[0]
    return normalize_space(cut.rstrip(".,;:") + ".")


def build_description(record: dict[str, Any]) -> str:
    name = str(record.get("display_name") or record.get("name") or "Kirje").strip()
    kind = KIND_LABELS.get(str(record.get("kind") or ""), "kohaliku toidu kirje")
    county = record.get("county")
    municipality = record.get("municipality")
    location = " / ".join(str(v) for v in [county, municipality] if v)
    if not location:
        location = "Eesti"

    food_categories = as_list(record.get("food_categories"))
    focus = ", ".join(CATEGORY_LABELS.get(cat, cat) for cat in food_categories[:4])
    terms = useful_terms(record)
    sources = source_labels(record)
    contacts = contact_labels(record)
    certifications = as_list(record.get("certifications"))

    existing = normalize_space(str(record.get("description") or ""))
    if existing and not is_generic_description(existing):
        overview = sentence_trim(existing, 430)
        if not overview.lower().startswith("ülevaade:"):
            overview = f"Ülevaade: {overview}"
    else:
        focus_phrase = focus or CATEGORY_LABELS.get(str(record.get("primary_food_category") or ""), "kohalik toit")
        overview = f"Ülevaade: {name} on {location} piirkonnaga seotud {kind}; fookuses on {focus_phrase}."

    sections = [overview]
    if focus and "Fookus:" not in overview:
        sections.append(f"Fookus: {focus}.")
    if terms:
        sections.append(f"Andmestikus mainitud: {', '.join(terms)}.")
    if certifications:
        sections.append(f"Sertifikaadid/märked: {', '.join(certifications)}.")
    if sources:
        sections.append(f"Allikad: {', '.join(sources)}.")
    if contacts:
        sections.append(f"Kontakt: olemas {', '.join(contacts)}.")

    description = normalize_space(" ".join(sections))
    return sentence_trim(description, 860)


def tag_sort_key(tag: str) -> tuple[int, int, str]:
    low = tag.casefold()
    try:
        priority = TAG_PRIORITY.index(low)
    except ValueError:
        priority = len(TAG_PRIORITY)
    # Keep precise product tags before broad county/sales tags.
    length_bonus = 0 if priority < len(TAG_PRIORITY) else min(len(low), 50)
    return (priority, length_bonus, low)


def enrich_record(record: dict[str, Any]) -> tuple[int, bool, bool]:
    original_tags = as_list(record.get("tags"))
    original_categories = as_list(record.get("food_categories"))
    original_description = str(record.get("description") or "")

    evidence_text = text_blob(record, include_name=False)
    evidence_with_name = text_blob(record, include_name=True)

    food_categories = infer_categories(record)
    if food_categories != original_categories:
        record["food_categories"] = food_categories
        if record.get("primary_food_category") not in food_categories:
            record["primary_food_category"] = choose_primary(food_categories)

    tags = original_tags[:]
    if "dairy" not in food_categories:
        tags = remove_tag(tags, FALSE_DAIRY_TAGS)
    if not re.search(r"\b(kohv|kohvik|kodukohvik|coffee)\b", evidence_text, re.IGNORECASE):
        tags = remove_tag(tags, COFFEE_TAGS)

    new_tags: list[str] = []
    new_tags.extend(category_tags(food_categories))
    if record.get("kind") == "farm":
        new_tags.extend(["talu", "kohalik tootja"])
    elif record.get("kind") == "producer":
        new_tags.extend(["tootja", "väiketootja"])
    elif record.get("kind") == "shop":
        new_tags.extend(["talupood", "müügikoht"])
    elif record.get("kind") == "market":
        new_tags.extend(["turg", "laat", "otse müük"])
    elif record.get("kind") == "event":
        new_tags.extend(["sündmus", "laat", "hooajaline"])

    if any(c.casefold() in {"mahe", "organic"} for c in as_list(record.get("certifications"))):
        new_tags.extend(["mahe", "mahetootja", "mahesertifikaat"])

    if record.get("consumer_relevance") in {"direct_sale", "likely_direct"}:
        new_tags.extend(["otse talust", "otse müük"])

    if contact_labels(record):
        new_tags.append("kontakt olemas")
    if record.get("county"):
        new_tags.append(str(record["county"]))
    if record.get("municipality"):
        new_tags.append(str(record["municipality"]))

    source_text = " ".join(source_ids(record)).casefold()
    if "atp" in source_text or "avatudtalud" in source_text:
        new_tags.extend(["avatud talude päev", "külastus"])
    if "kohaliktoit" in source_text or "maaturism" in source_text:
        new_tags.extend(["kohalik toit", "toiduvõrgustik"])
    if "laadakalender" in source_text:
        new_tags.extend(["laat", "sündmus"])

    for pattern, pattern_tags in TAG_RULES:
        if pattern.search(evidence_with_name if "avatud talude päev" in pattern.pattern else evidence_text):
            new_tags.extend(pattern_tags)

    tags = add_unique(tags, new_tags)
    tags = sorted(tags, key=tag_sort_key)
    record["tags"] = tags

    record["description"] = build_description(record)

    tags_added = max(0, len(tags) - len(original_tags))
    tags_changed = tags != original_tags
    description_changed = record["description"] != original_description
    categories_changed = food_categories != original_categories
    return tags_added, description_changed, tags_changed or categories_changed


def recompute_counts(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts = Counter(str(record[key]) for record in records if record.get(key))
    return dict(sorted(counts.items()))


def recompute_primary_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(record.get("primary_food_category") or "other") for record in records)
    return dict(sorted(counts.items()))


def main() -> None:
    data = json.loads(FULL_DATASET.read_text(encoding="utf-8"))
    records = data.get("records") or []

    total_tags_added = 0
    descriptions_changed = 0
    tag_or_category_changed = 0

    for record in records:
        tags_added, description_changed, search_changed = enrich_record(record)
        total_tags_added += tags_added
        if description_changed:
            descriptions_changed += 1
        if search_changed:
            tag_or_category_changed += 1

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    meta = data.setdefault("meta", {})
    meta["generated_at"] = now
    meta["record_count"] = len(records)
    meta["description"] = (
        "Consumer-ready map of Estonian farms, producers, markets, shops, "
        "and food events with source-aware descriptions and Estonian search tags."
    )
    meta["fields_added_in_v3"] = [
        "source-aware structured descriptions",
        "expanded Estonian search tags",
        "cleaned false-positive dairy and coffee tags",
        "web-researched enrichment notes",
    ]
    enrichment_meta = meta.setdefault("enrichment_2026_05", {})
    contact_enrichment = enrichment_meta.get("contact_enrichment")
    enrichment_meta.update(
        {
        "method": (
            "Deterministic enrichment from existing record fields plus native web "
            "research on public source vocabularies; no invented record-level facts."
        ),
        "records_processed": len(records),
        "descriptions_changed": descriptions_changed,
        "records_with_search_tags_or_categories_changed": tag_or_category_changed,
        "approx_tags_added": total_tags_added,
        "web_research_sources": WEB_RESEARCH_SOURCES,
        }
    )
    if contact_enrichment:
        enrichment_meta["contact_enrichment"] = contact_enrichment

    data["counts_by_kind"] = recompute_counts(records, "kind")
    data["counts_by_county"] = recompute_counts(records, "county")
    data["counts_by_primary_food_category"] = recompute_primary_counts(records)

    FULL_DATASET.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    print(f"records processed: {len(records)}")
    print(f"descriptions changed: {descriptions_changed}")
    print(f"records with tags/categories changed: {tag_or_category_changed}")
    print(f"approx tags added: {total_tags_added}")


if __name__ == "__main__":
    main()
