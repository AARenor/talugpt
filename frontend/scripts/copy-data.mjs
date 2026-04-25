import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(__dirname, "../../data_pipeline/Full farm data.json");
const DST = resolve(__dirname, "../public/farms.json");

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
  `wrote ${slim.records.length} records to public/farms.json (${sizeKb} KB)`
);
