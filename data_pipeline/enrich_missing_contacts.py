"""Fill missing contacts from existing public source URLs.

This script fetches record-specific public source pages already listed in the
dataset and extracts clearly visible e-mail addresses, Estonian phone numbers,
and useful profile/website URLs. It skips registry/geocoder pages and avoids
adding source-site footer contacts as farm contacts.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data_pipeline" / "Full farm data.json"
CACHE_FILE = ROOT / "contact_page_cache.json"

USER_AGENT = "TaluGPT contact enrichment (+https://github.com/AARenor/talugpt)"
MAX_WORKERS = 10
TIMEOUT_SECONDS = 12

URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", re.IGNORECASE)
HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
PHONE_RE = re.compile(
    r"(?:(?:\+|00)?372[\s().-]*)?(?:\d[\s().-]*){7,8}",
    re.IGNORECASE,
)

SKIP_DOMAINS = {
    "ariregister.rik.ee",
    "nominatim.openstreetmap.org",
    "openstreetmap.org",
    "www.openstreetmap.org",
    "qdrant.tech",
}

AGGREGATOR_EMAIL_DOMAINS = {
    "avatudtalud.ee",
    "epkk.ee",
    "hiiumaa.ee",
    "laadakalender.ee",
    "maainfo.ee",
    "maaturism.ee",
    "kohaliktoit.maaturism.ee",
    "umamekk.ee",
}

PROFILE_DOMAINS = {
    "avatudtalud.ee",
    "www.avatudtalud.ee",
    "epkk.ee",
    "www.epkk.ee",
    "hiiumaa.ee",
    "www.hiiumaa.ee",
    "kohaliktoit.maaturism.ee",
    "laadakalender.ee",
    "www.laadakalender.ee",
    "maainfo.ee",
    "www.maainfo.ee",
    "umamekk.ee",
    "www.umamekk.ee",
}

BAD_LINK_HOST_PARTS = {
    "addtoany.com",
    "doubleclick.net",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "google.com",
    "google-analytics.com",
    "googletagmanager.com",
    "gravatar.com",
    "gstatic.com",
    "schema.org",
    "twitter.com/share",
    "vorumaa.ee",
    "wp.com",
}

SOCIAL_HOSTS = {"facebook.com", "www.facebook.com", "instagram.com", "www.instagram.com"}


def load_cache() -> dict[str, dict[str, Any]]:
    if not CACHE_FILE.exists():
        return {}
    return json.loads(CACHE_FILE.read_text(encoding="utf-8"))


def save_cache(cache: dict[str, dict[str, Any]]) -> None:
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def clean_url(raw: str, base: str | None = None) -> str | None:
    raw = html.unescape(raw).strip()
    if not raw or raw.startswith(("mailto:", "tel:", "javascript:", "#")):
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


def is_skipped_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    h = parsed.netloc.casefold().removeprefix("www.")
    if h in SKIP_DOMAINS:
        return True
    if parsed.path in {"", "/"} and h not in SOCIAL_HOSTS:
        return True
    return False


def source_urls(record: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for source in record.get("sources") or []:
        ref = str(source.get("ref") or "")
        for match in URL_RE.finditer(ref):
            url = clean_url(match.group(0))
            if url and not is_skipped_url(url):
                urls.append(url)
    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def cache_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]


def fetch_url(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            content_type = response.headers.get("content-type", "")
            body = response.read(1_500_000)
            charset = response.headers.get_content_charset() or "utf-8"
            text = body.decode(charset, errors="replace")
            return {
                "ok": True,
                "url": response.geturl(),
                "status": getattr(response, "status", 200),
                "content_type": content_type,
                "html": text,
                "elapsed_ms": int((time.time() - started) * 1000),
            }
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return {
            "ok": False,
            "url": url,
            "error": str(error),
            "elapsed_ms": int((time.time() - started) * 1000),
        }


def fetch_all(urls: list[str]) -> dict[str, dict[str, Any]]:
    cache = load_cache()
    missing = [url for url in urls if cache_key(url) not in cache]

    if missing:
        print(f"fetching {len(missing)} public source pages")
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        future_map = {pool.submit(fetch_url, url): url for url in missing}
        for i, future in enumerate(concurrent.futures.as_completed(future_map), start=1):
            url = future_map[future]
            cache[cache_key(url)] = future.result()
            if i % 50 == 0:
                print(f"  fetched {i}/{len(missing)}")
                save_cache(cache)

    save_cache(cache)
    return {url: cache[cache_key(url)] for url in urls}


def strip_html(raw: str) -> str:
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", raw)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p>|</li>|</div>|</tr>|</h[1-6]>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def normalize_email(email: str, source_url: str) -> str | None:
    clean = email.strip().strip(".,;:()[]{}<>").lower()
    if not EMAIL_RE.fullmatch(clean):
        return None
    domain = clean.split("@", 1)[1]
    source_host = host(source_url)
    if domain in AGGREGATOR_EMAIL_DOMAINS or domain == source_host:
        return None
    if clean.endswith((".png", ".jpg", ".jpeg", ".webp")):
        return None
    return clean


def extract_emails(raw: str, source_url: str) -> list[str]:
    emails: list[str] = []
    decoded = html.unescape(urllib.parse.unquote(raw))
    for href in HREF_RE.findall(decoded):
        if href.lower().startswith("mailto:"):
            candidate = href.split(":", 1)[1].split("?", 1)[0]
            email = normalize_email(candidate, source_url)
            if email:
                emails.append(email)
    for match in EMAIL_RE.finditer(decoded):
        email = normalize_email(match.group(0), source_url)
        if email:
            emails.append(email)
    return list(dict.fromkeys(emails))


def normalize_phone(raw: str, context: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("00372"):
        digits = digits[2:]
    if digits.startswith("372"):
        local = digits[3:]
    else:
        local = digits
        if not re.search(r"tel|telefon|phone|mobiil|helista|kontakt", context, re.IGNORECASE):
            return None
    if len(local) not in {7, 8}:
        return None
    if local.startswith(("000", "123", "202", "199", "201")):
        return None
    return f"+372 {local}"


def extract_phones(raw: str) -> list[str]:
    decoded = html.unescape(urllib.parse.unquote(raw))
    phones: list[str] = []
    for href in HREF_RE.findall(decoded):
        if href.lower().startswith("tel:"):
            phone = normalize_phone(href.split(":", 1)[1], "tel")
            if phone:
                phones.append(phone)
    text = strip_html(decoded)
    for match in PHONE_RE.finditer(text):
        start = max(0, match.start() - 40)
        end = min(len(text), match.end() + 40)
        phone = normalize_phone(match.group(0), text[start:end])
        if phone:
            phones.append(phone)
    return list(dict.fromkeys(phones))


def name_tokens(record: dict[str, Any]) -> set[str]:
    name = str(record.get("display_name") or record.get("name") or "")
    tokens = {
        token.casefold()
        for token in re.findall(r"[A-Za-zÕÄÖÜŠŽõäöüšž0-9]{4,}", name)
        if token.casefold() not in {"talu", "fie", "osaühing", "ou", "oü"}
    }
    return tokens


def extract_candidate_links(raw: str, source_url: str, record: dict[str, Any]) -> list[str]:
    source_host = host(source_url)
    tokens = name_tokens(record)
    scored: list[tuple[int, str]] = []
    for match in HREF_RE.finditer(raw):
        href = clean_url(match.group(1), source_url)
        if not href:
            continue
        h = host(href)
        if h == source_host:
            continue
        if any(part in href.casefold() for part in BAD_LINK_HOST_PARTS):
            continue
        parsed = urllib.parse.urlparse(href)
        if parsed.path.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".pdf")):
            continue
        if "sharer" in href.casefold() or "/share" in href.casefold():
            continue

        context = raw[max(0, match.start() - 120) : min(len(raw), match.end() + 120)]
        context_text = strip_html(context).casefold()
        score = 0
        if re.search(r"koduleht|veeb|website|homepage|facebook|instagram", context_text, re.I):
            score += 30
        if h not in SOCIAL_HOSTS:
            score += 5
        if tokens and any(token in href.casefold() for token in tokens):
            score += 25
        if h in SOCIAL_HOSTS:
            score += 8
        if score >= 25:
            scored.append((score, href))

    scored.sort(key=lambda item: (-item[0], item[1]))
    links: list[str] = []
    for _, link in scored:
        if link not in links:
            links.append(link)
    return links


def is_record_profile_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    h = parsed.netloc.casefold()
    if h not in PROFILE_DOMAINS:
        return False
    if parsed.path in {"", "/"}:
        return False
    if h.endswith("maainfo.ee") and "rid=" not in parsed.query:
        return False
    return True


def page_candidates(record: dict[str, Any], source_url: str, page: dict[str, Any]) -> dict[str, Any]:
    if not page.get("ok") or "html" not in page:
        return {}
    raw = str(page["html"])
    candidates: dict[str, Any] = {}

    emails = extract_emails(raw, source_url)
    phones = extract_phones(raw)
    links = extract_candidate_links(raw, source_url, record)

    if emails:
        candidates["email"] = emails[0]
    if phones:
        candidates["phone"] = phones[0]
    if links:
        candidates["website"] = links[0]
    elif is_record_profile_url(source_url):
        candidates["website"] = source_url

    return candidates


def merge_contact_candidates(
    records: list[dict[str, Any]], pages: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    raw_by_record: dict[str, dict[str, list[tuple[str, str]]]] = defaultdict(lambda: defaultdict(list))

    for record in records:
        contact = record.setdefault("contact", {"email": None, "phone": None, "website": None})
        if contact.get("email") and contact.get("phone") and contact.get("website"):
            continue
        for url in source_urls(record):
            candidates = page_candidates(record, url, pages[url])
            for field, value in candidates.items():
                if value and not contact.get(field):
                    raw_by_record[str(record["id"])][field].append((str(value), url))

    value_counts: dict[str, Counter[str]] = {
        "email": Counter(),
        "phone": Counter(),
        "website": Counter(),
    }
    for fields in raw_by_record.values():
        for field, values in fields.items():
            for value, _ in values[:1]:
                value_counts[field][value] += 1

    chosen: dict[str, dict[str, Any]] = {}
    for record_id, fields in raw_by_record.items():
        for field, values in fields.items():
            for value, url in values:
                max_shared = 8 if field != "website" else 20
                if value_counts[field][value] > max_shared:
                    continue
                chosen.setdefault(record_id, {})[field] = value
                chosen[record_id].setdefault("_source_url", url)
                break
    return chosen


def apply_contacts(records: list[dict[str, Any]], chosen: dict[str, dict[str, Any]]) -> int:
    changed = 0
    for record in records:
        fields = chosen.get(str(record.get("id")))
        if not fields:
            continue
        contact = record.setdefault("contact", {"email": None, "phone": None, "website": None})
        applied: list[str] = []
        for field in ("email", "phone", "website"):
            if fields.get(field) and not contact.get(field):
                contact[field] = fields[field]
                applied.append(field)
                changed += 1
        if applied:
            source_url = str(fields.get("_source_url") or "")
            record.setdefault("sources", []).append(
                {
                    "source_id": "contact-enrichment-2026-05",
                    "ref": source_url,
                    "verification_note": (
                        "Filled missing contact field(s) from a public source page: "
                        + ", ".join(applied)
                        + "."
                    ),
                }
            )
    return changed


def main() -> None:
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    records = data.get("records") or []

    urls: list[str] = []
    for record in records:
        contact = record.get("contact") or {}
        if contact.get("email") and contact.get("phone") and contact.get("website"):
            continue
        urls.extend(source_urls(record))
    urls = list(dict.fromkeys(urls))
    print(f"candidate source pages: {len(urls)}")

    pages = fetch_all(urls)
    ok_pages = sum(1 for page in pages.values() if page.get("ok"))
    print(f"available pages: {ok_pages}/{len(pages)}")

    chosen = merge_contact_candidates(records, pages)
    changed = apply_contacts(records, chosen)

    meta = data.setdefault("meta", {})
    meta.setdefault("enrichment_2026_05", {})
    meta["enrichment_2026_05"]["contact_enrichment"] = {
        "method": (
            "Fetched existing public source URLs and filled only missing contact "
            "fields when an e-mail, Estonian phone number, external site, or "
            "record-specific public profile URL was found."
        ),
        "candidate_source_pages": len(urls),
        "available_source_pages": ok_pages,
        "records_with_contact_additions": len(chosen),
        "contact_fields_added": changed,
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }

    DATASET.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    by_field = Counter()
    for fields in chosen.values():
        for field in ("email", "phone", "website"):
            if fields.get(field):
                by_field[field] += 1
    print(f"records with contact additions: {len(chosen)}")
    print(f"contact fields added: {changed}")
    print(f"by field: {dict(by_field)}")


if __name__ == "__main__":
    main()
