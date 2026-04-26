# TaluGPT 🇪🇪

**Natural-language local-food discovery for Estonia.**
Ask in Estonian or English — *"Kus saab Viimsis toorpiima?"* — and get a Claude-powered answer alongside a Leaflet map highlighting the relevant farms, markets, producers, shops, and food events.

> **Live demo:** **[talugpt.vercel.app](https://talugpt.vercel.app)**
> `main` is the deploy branch — every merge to `main` auto-deploys to Vercel within ~30 s.

![TaluGPT desktop](docs/screenshot.png)

---

## Run it locally

```bash
git clone https://github.com/AARenor/talugpt.git
cd talugpt/frontend
npm install
npm run dev          # → http://localhost:3000
```

`npm run dev` first runs `scripts/copy-data.mjs`, which reads `data_pipeline/Full farm data.json`, slims it to the fields the map needs, and writes `frontend/public/farms.json`. The page then fetches that file and renders ~2,130 markers with clustering.

```bash
npm run build        # production static export → frontend/out/
npm run type-check   # tsc --noEmit
```

The build emits a fully static site to `frontend/out/` (`output: 'export'` in `next.config.js`), so any static host works.

---

## Deploy your own copy

### Option A — Vercel (recommended, what powers `talugpt.vercel.app`)

1. Fork this repo on GitHub.
2. On [vercel.com/new](https://vercel.com/new) → **Import Git Repository** → pick your fork.
3. **Root directory:** set to `frontend`.
4. **Framework preset:** Next.js (Vercel detects it automatically).
5. Click **Deploy**. Every push to `main` redeploys automatically.

No env vars are required for the frontend itself — the chat widget hits a public n8n webhook (see [Wire up the chat](#wire-up-the-chat) below to point it at your own n8n).

### Option B — Netlify (connected repo)

1. Fork the repo.
2. On Netlify: **Add new site → Import from Git → pick the fork**.
3. Settings auto-load from `netlify.toml`:

   ```toml
   [build]
     base    = "frontend"
     command = "npm install && npm run build"
     publish = "frontend/out"
   ```

4. Deploy. Auto-rebuilds on every push to `main`.

### Option C — Netlify drag-and-drop

```bash
cd frontend && npm install && npm run build
# then drag frontend/out/ onto https://app.netlify.com/drop
```

> **CORS reminder.** The chat widget POSTs directly to your n8n webhook. The Chat Trigger / Webhook node in n8n must list your deployed domain (e.g. `https://your-fork.vercel.app`) under **Allowed Origins (CORS)**, otherwise the browser blocks the request.

---

## Wire up the chat

The floating green chat button is the official `@n8n/chat` widget pointed at an n8n webhook. The chat backend ships in this repo as **[`talugpt rag.json`](talugpt%20rag.json)** — import it once into your n8n instance.

### 1. Import the workflow

In your n8n UI: **Workflows → Import from file → talugpt rag.json**. The file ships 17 nodes, split into two halves:

- **Ingestion**: 2× Google Drive folder triggers (file created + file updated) → Drive download → delete-old-vectors-by-`file_id` → Default Data Loader (auto-detects PDF / Docx / CSV / TXT / EPUB) with a 1000 / 200 recursive chunker → Gemini `gemini-embedding-001` → Qdrant insert → 3 s pacing wait. Retry-on-fail is set everywhere for Gemini's notorious 429s.
- **Chat**: Webhook → Set fields → AI Agent (Claude Opus 4.7) ← Qdrant retrieval tool (same `codex_drive_rag` collection, same Gemini model so query and document vectors match) ← Redis session memory → respond-to-webhook.

### 2. Re-attach credentials

Only credential **IDs** are exported, never the secrets. After import you'll need:

- **Google Drive OAuth2** (for the folder triggers + downloader)
- **Google Gemini / PaLM API** (for embeddings)
- **Qdrant API** (collection `codex_drive_rag`, vector size matching `gemini-embedding-001`)
- **Anthropic API** (for `claude-opus-4-7`)
- **Redis** (for chat history)

### 3. Point the frontend at your webhook

Edit `frontend/components/ChatWidget.tsx`:

```ts
const WEBHOOK_URL = "https://YOUR-N8N-DOMAIN/webhook/codex-qdrant-chat";
```

Push, redeploy, done.

### 4. Add a domain to CORS

In your n8n Chat Trigger / Webhook node → **Allowed Origins (CORS)** → add `https://your-deploy-domain` (and `http://localhost:3000` for dev).

---

## Embed the chat on another site

`frontend/embed/talugpt-chat-embed.html` is a self-contained drop-in. Two tags into any site's `<head>` puts the floating green TaluGPT bubble on every page:

```html
<link
  href="https://cdn.jsdelivr.net/npm/@n8n/chat/dist/style.css"
  rel="stylesheet" />
<script type="module">
  import { createChat } from "https://cdn.jsdelivr.net/npm/@n8n/chat/dist/chat.bundle.es.js";
  createChat({
    webhookUrl: "https://n8n.arleserver.cfd/webhook/codex-qdrant-chat",
    defaultLanguage: "et",
    initialMessages: ["Tere! 👋"],
  });
</script>
```

No build step, no npm install — the official `@n8n/chat` widget loads from jsDelivr at runtime.

---

## Update the dataset

The source of truth lives at `data_pipeline/Full farm data.json`. To replace or extend it:

1. Drop your new file at `data_pipeline/Full farm data.json` (same path, same name).
2. The `prebuild` script in `frontend/package.json` runs `scripts/copy-data.mjs` automatically before every `npm run dev` and `npm run build`, regenerating `frontend/public/farms.json`.
3. The committed `frontend/public/farms.json` is also kept up-to-date so deploys without access to `data_pipeline/` (drag-and-drop) still work — `copy-data.mjs` falls back to it.

The slim payload only carries the fields the map UI needs (id, kind, name, lat/lng, county, products, certifications, tags, contact). Everything else stays in the source file.

---

## Optional: FastAPI backend

If you don't want to run n8n, `backend/` is a self-contained FastAPI app that does the same ingestion + chat work in Python.

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example .env             # ANTHROPIC_API_KEY, QDRANT_URL, QDRANT_COLLECTION
uvicorn backend.main:app --reload --port 8000
```

| Endpoint | Purpose |
|---|---|
| `GET /health` | Readiness probe — verifies Qdrant connectivity |
| `POST /ingest/file` | Multipart upload — parses PDF / Docx / Xlsx / TXT, chunks, embeds, upserts to Qdrant. Deletes existing chunks for the same file id before inserting (idempotent) |
| `POST /ingest/raw` | Same flow for raw text |
| `POST /chat` | RAG round-trip — embed query, top-k Qdrant search, Claude Opus 4.7 with prompt caching, returns answer + cited record IDs |

Ships with a `Dockerfile`. Uses the same Qdrant collection (`codex_drive_rag`) as the n8n workflow, so you can mix and match: ingest with FastAPI, chat with n8n, or vice versa.

---

## Repo layout

```
talugpt/
├── frontend/                       Next.js 14 web map (the deployed app)
│   ├── app/                          page, layout, globals.css
│   ├── components/
│   │   ├── FarmMap.tsx               Leaflet map + clustering + popup builder
│   │   ├── FilterPanel.tsx           Sidebar filters
│   │   └── ChatWidget.tsx            @n8n/chat embed
│   ├── embed/                        Drop-in chat-widget for third-party sites
│   ├── lib/                          Types, taxonomy, filter logic
│   ├── scripts/copy-data.mjs         Slims the dataset at build time
│   └── public/farms.json             Generated, served to the browser
├── backend/                         Optional FastAPI service (Docker-ready)
├── data_pipeline/Full farm data.json  2,130 records · the unified dataset
├── talugpt rag.json                 Importable n8n workflow (chat + ingestion)
├── netlify.toml                     Netlify auto-deploy config
└── docs/                            Screenshots
```

---

## Tech stack

| Layer | Tech |
|---|---|
| LLM | **Claude Opus 4.7** (`claude-opus-4-7`) — 1M context, prompt caching, streaming |
| Vector DB | **Qdrant** — collection `codex_drive_rag` |
| Embeddings | **Google `gemini-embedding-001`** — called from n8n |
| Orchestration | **n8n** (self-hosted) — chat trigger → Qdrant tool → Claude |
| Frontend | **Next.js 14** (App Router) · React 18 · Leaflet + marker-cluster · `@n8n/chat` |
| Map tiles | OpenStreetMap |
| Geocoding | Nominatim (free, no key) |
| Type | Fraunces (display) + Alegreya Sans (body), via `next/font/google` |
| Hosting | Vercel (live: talugpt.vercel.app) — Netlify also supported via `netlify.toml` |

---

## License

The application code is **MIT-licensed**. The dataset is redistributed under the licenses of its upstream sources — see the `sources` field on each record in `Full farm data.json` for provenance (predominantly **CC-BY**). Map tiles © OpenStreetMap contributors (ODbL). Geocoding © Nominatim / OpenStreetMap.
