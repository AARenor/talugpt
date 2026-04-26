import { readFile, writeFile, mkdir, stat } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

// Look for the source dataset in several plausible locations so this script
// works whether the build runs from a connected-repo deploy (Netlify checks
// out the whole repo, data is one level up), a drag-and-drop deploy of just
// `frontend/` (data was bundled inside the frontend), or a local dev session.
const CANDIDATES = [
  resolve(__dirname, "../../data_pipeline/Full farm data.json"),
  resolve(__dirname, "../data_pipeline/Full farm data.json"),
  resolve(__dirname, "../data/Full farm data.json"),
  resolve(__dirname, "../public/data/Full farm data.json"),
];

const DST = resolve(__dirname, "../public/farms.json");

async function exists(p) {
  try {
    await stat(p);
    return true;
  } catch {
    return false;
  }
}

let SRC = null;
for (const c of CANDIDATES) {
  if (await exists(c)) {
    SRC = c;
    break;
  }
}

if (!SRC) {
  if (await exists(DST)) {
    console.warn(
      `[copy-data] source dataset not found in any of: \n  ${CANDIDATES.join(
        "\n  "
      )}\n[copy-data] but ${DST} already exists — skipping regeneration.`
    );
    process.exit(0);
  }
  console.error(
    `[copy-data] source dataset not found and ${DST} is missing.`
  );
  console.error(
    `[copy-data] tried:\n  ${CANDIDATES.join("\n  ")}`
  );
  process.exit(1);
}

console.log(`[copy-data] reading from ${SRC}`);

const raw = await readFile(SRC, "utf8");
const data = JSON.parse(raw);

const slim = {
  generated_at: data.meta?.generated_at ?? new Date().toISOString(),
  record_count: data.meta?.record_count ?? data.records.length,
  counts_by_kind: data.counts_by_kind ?? {},
  counts_by_county: data.counts_by_county ?? {},
  counts_by_primary_food_category: data.counts_by_primary_food_category ?? {},
  records: data.records
    .filter((r) => typeof r.lat === "number" && typeof r.lng === "number")
    .map((r) => ({
      id: r.id,
      kind: r.kind,
      name: r.display_name ?? r.name,
      county: r.county ?? null,
      municipality: r.municipality ?? null,
      lat: r.lat,
      lng: r.lng,
      description: r.description ?? "",
      products: r.products ?? [],
      certifications: r.certifications ?? [],
      categories: r.categories ?? [],
      tags: r.tags ?? [],
      food_categories: r.food_categories ?? [],
      primary_food_category: r.primary_food_category ?? null,
      contact: {
        email: r.contact?.email ?? null,
        phone: r.contact?.phone ?? null,
        website: r.contact?.website ?? null,
      },
      date: r.date ?? null,
      date_end: r.date_end ?? null,
    })),
};

await mkdir(dirname(DST), { recursive: true });
await writeFile(DST, JSON.stringify(slim));

const sizeKb = Math.round(Buffer.byteLength(JSON.stringify(slim)) / 1024);
console.log(
  `[copy-data] wrote ${slim.records.length} records to public/farms.json (${sizeKb} KB)`
);
