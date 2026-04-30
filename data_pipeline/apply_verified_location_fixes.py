"""Apply manually verified location fixes to the farm map datasets."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

DATASETS = [
    ROOT / "data_pipeline" / "Full farm data.json",
    ROOT / "frontend" / "public" / "farms.json",
    ROOT / "frontend" / "out" / "farms.json",
]

FIXES: dict[str, dict[str, Any]] = {
    # Official Estonian address geocoder, based on e-Ariregister address:
    # Laane maakond, Laane-Nigula vald, Jalukse kula, Saareagro.
    "dde13707a54a": {
        "county": "L\u00e4\u00e4nemaa",
        "municipality": "L\u00e4\u00e4ne-Nigula vald",
        "lat": 59.021432,
        "lng": 23.794452,
    },
    # Official Estonian address geocoder:
    # Parnu maakond, Laaneranna vald, Kanamardi kula, Mulgu.
    "2e0cd184f91c": {
        "county": "P\u00e4rnumaa",
        "municipality": "L\u00e4\u00e4neranna vald",
        "lat": 58.46428,
        "lng": 23.962047,
    },
    # Official Estonian address geocoder:
    # Harju maakond, Tallinn, Nomme linnaosa, Kalmistu tee 8a.
    "bc102ae66ec1": {
        "county": "Harjumaa",
        "municipality": "Tallinn",
        "lat": 59.389571,
        "lng": 24.726837,
    },
    # Maainfo ATP lists Rikets aiand in Raplamaa, Kohila; e-Ariregister
    # address for RIKETS TOOTMINE OU resolves to Vana-Aespa, Kohila vald.
    "7248d29eea7b": {
        "county": "Raplamaa",
        "municipality": "Kohila vald",
        "lat": 59.20029,
        "lng": 24.663542,
    },
    # Official Estonian address geocoder:
    # Valga maakond, Valga vald, Rebasemoisa kula, Roomu.
    "ab225acce285": {
        "county": "Valgamaa",
        "municipality": "Valga vald",
        "lat": 57.711493,
        "lng": 26.457676,
    },
    "c5ca4082a060": {
        "county": "Valgamaa",
        "municipality": "Valga vald",
        "lat": 57.711493,
        "lng": 26.457676,
    },
    # Official Estonian address geocoder:
    # Jogeva maakond, Mustvee vald, Maetsma kula, Kaalumaja.
    "88564f9d6e11": {
        "county": "J\u00f5gevamaa",
        "municipality": "Mustvee vald",
        "lat": 58.995261,
        "lng": 26.892899,
        "description_replace": (
            "Ida-Virumaa / Mustvee vald piirkonnas",
            "J\u00f5gevamaa / Mustvee vald piirkonnas",
        ),
    },
}


def recompute_counties(records: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(r.get("county") for r in records if r.get("county"))
    return dict(sorted(counts.items()))


def apply_fixes(path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = 0

    for record in data["records"]:
        fix = FIXES.get(record.get("id"))
        if not fix:
            continue

        for key in ("county", "municipality", "lat", "lng"):
            if record.get(key) != fix[key]:
                record[key] = fix[key]
                changed += 1

        replace = fix.get("description_replace")
        if replace and isinstance(record.get("description"), str):
            before, after = replace
            description = record["description"]
            if before in description:
                record["description"] = description.replace(before, after)
                changed += 1

    if changed:
        data["counts_by_county"] = recompute_counties(data["records"])
        path.write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

    return changed


def main() -> None:
    for dataset in DATASETS:
        if not dataset.exists():
            print(f"skip missing {dataset}")
            continue
        changed = apply_fixes(dataset)
        print(f"{dataset.relative_to(ROOT)}: {changed} field updates")


if __name__ == "__main__":
    main()
