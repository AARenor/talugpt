# TaluGPT 🇪🇪

**Natural-language local-food discovery for Estonia.**

Ask in Estonian or English — *"Kus saab Viimsis toorpiima?"* or *"Where can I buy organic honey near Tartu?"* — and get a Claude-powered answer alongside a Leaflet map highlighting the relevant farms, markets, producers, shops, and food events.

> Live at **[talugpt.vercel.app](https://talugpt.vercel.app)**

![TaluGPT desktop](docs/screenshot.png)

---

## What it is

A web map of **2,272 deduplicated, geocoded** Estonian farms, producers, markets, shops, and food events, stitched together from the PTA organic farming registry, the Estonian Business Registry (e-Äriregister), avatudtalud.ee, kohaliktoit.maaturism.ee, EPKK, and laadakalender.ee.

Each pin carries the venue's kind, county, municipality, primary food category, products, certifications (e.g. *mahe*), contact info, tags, and source provenance. Filter chips on the side narrow the map by kind, county, food category, and organic certification. A floating chat widget answers free-form questions in Estonian or English by retrieving the most relevant venues from a vector database and letting Claude write the reply.

---

## What it's built on

| Layer | Tech |
|---|---|
| LLM | **Claude Opus 4.7** (`claude-opus-4-7`) — 1M context, prompt caching, streaming |
| Vector DB | **Qdrant** — collection `codex_drive_rag` |
| Embeddings | **Google `gemini-embedding-001`** — multilingual, called from n8n |
| Orchestration | **n8n** (self-hosted) — chat trigger → Qdrant retrieval tool → Claude, plus a Google-Drive-fed ingestion pipeline with delete-by-`file_id` deduping |
| Frontend | **Next.js 14** (App Router) · React 18 · Leaflet + leaflet.markercluster · `@n8n/chat` |
| Map tiles | OpenStreetMap |
| Geocoding | Nominatim (free, no key) |
| Type | Fraunces (display) + Alegreya Sans (body), via `next/font/google` |
| Hosting | Vercel — `talugpt.vercel.app`, auto-deploys from `main` |

The chat workflow ships in this repo as **[`talugpt rag.json`](talugpt%20rag.json)** (17 nodes, importable into any n8n instance). An optional `backend/` folder offers a self-hosted FastAPI alternative to n8n with the same `/ingest/file`, `/ingest/raw`, and `/chat` endpoints.

---

## Data sources

| Source | Type | License |
|---|---|---|
| **PTA Mahepõllumajanduse Register** | Estonian organic farming registry | CC-BY |
| **e-Äriregister** | Estonian Business Registry | CC-BY 4.0 |
| **avatudtalud.ee** | Open Farms Day catalogue | Public |
| **kohaliktoit.maaturism.ee** | "Local Food" network | Public |
| **EPKK** | Estonian Chamber of Agriculture and Commerce | Public |
| **laadakalender.ee** | Estonian fair / market calendar | Public |

Coordinates were geocoded with Nominatim / OpenStreetMap (ODbL). Map tiles © OpenStreetMap contributors.

---

## License

The application code is **MIT-licensed**. The dataset is redistributed under the licenses of its upstream sources — see the `sources` field on each record in `Full farm data.json` for provenance.
