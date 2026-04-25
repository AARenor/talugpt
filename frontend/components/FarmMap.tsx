"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Map as LeafletMap, CircleMarker } from "leaflet";
import { applyFilters } from "@/lib/farmFilter";
import {
  ALL_KINDS,
  KIND_COLORS,
  KIND_LABELS,
  type Farm,
  type FarmDataset,
  type FilterState,
} from "@/lib/types";
import { getRecordCategories } from "@/lib/products";
import FilterPanel from "./FilterPanel";

const ESTONIA_CENTER: [number, number] = [58.7, 25.5];
const DEFAULT_ZOOM = 7;

// Categories that are network/membership / programme labels (not agricultural
// taxonomy). When a record has no source-provided description, we surface
// these so the user gets something more than the kind/county tags.
const MEMBERSHIP_CATEGORIES = new Set(
  [
    "Kohalik toit",
    "Uma Mekk",
    "Viru Toit",
    "Seto Köök",
    "Saaremaa Ehtne",
    "Põlvamaa Rohelisem märk",
    "EPKK",
    "Organic Estonia",
    "Avatud talude päev 2023",
    "Avatud talude päev 2026",
    "talupood või-turg",
    "OTT,kaubaring vms",
    "OTT, mis tegutseb vaid FBs",
  ].map((s) => s.toLowerCase())
);

function buildDescription(farm: Farm): string {
  const desc = (farm.description || "").trim();
  if (desc) return desc;

  const memberships = farm.categories.filter((c) =>
    MEMBERSHIP_CATEGORIES.has(c.toLowerCase())
  );
  if (memberships.length > 0) {
    return `Kuulub: ${memberships.join(", ")}.`;
  }
  return "";
}

function buildPopupHtml(farm: Farm): string {
  const color = KIND_COLORS[farm.kind];
  const label = KIND_LABELS[farm.kind];
  const isOrganic = farm.certifications.some(
    (c) => c.toLowerCase() === "mahe" || c.toLowerCase() === "organic"
  );

  const location = [farm.municipality, farm.county].filter(Boolean).join(", ");
  const description = buildDescription(farm);
  const categories = getRecordCategories(farm.food_categories);
  const categoryBadges = categories
    .map(
      (c) =>
        `<span class="cat-badge">${c.emoji} ${escapeHtml(c.label)}</span>`
    )
    .join("");

  // Show up to 6 tags — Estonian keyword vocabulary from the dataset
  const tagPills = farm.tags
    .slice(0, 6)
    .map((t) => `<span class="tag-pill">${escapeHtml(t)}</span>`)
    .join("");

  const contactLines: string[] = [];
  if (farm.contact.website) {
    const href = farm.contact.website.startsWith("http")
      ? farm.contact.website
      : `https://${farm.contact.website}`;
    contactLines.push(
      `<div>🌐 <a href="${escapeAttr(href)}" target="_blank" rel="noopener">${escapeHtml(
        farm.contact.website
      )}</a></div>`
    );
  }
  if (farm.contact.phone) {
    contactLines.push(
      `<div>📞 <a href="tel:${escapeAttr(farm.contact.phone)}">${escapeHtml(
        farm.contact.phone
      )}</a></div>`
    );
  }
  if (farm.contact.email) {
    contactLines.push(
      `<div>✉ <a href="mailto:${escapeAttr(farm.contact.email)}">${escapeHtml(
        farm.contact.email
      )}</a></div>`
    );
  }

  const dateLine = farm.date
    ? `<div class="meta-line">📅 ${escapeHtml(farm.date)}${
        farm.date_end ? ` – ${escapeHtml(farm.date_end)}` : ""
      }</div>`
    : "";

  return `
    <div class="popup">
      <span class="kind-tag" style="background:${color}">${label}</span>
      ${isOrganic ? '<span class="cert-organic">MAHE</span>' : ""}
      <h3>${escapeHtml(farm.name)}</h3>
      ${location ? `<div class="meta-line">📍 ${escapeHtml(location)}</div>` : ""}
      ${dateLine}
      ${description ? `<div class="description">${escapeHtml(description)}</div>` : ""}
      ${categoryBadges ? `<div class="cat-badges">${categoryBadges}</div>` : ""}
      ${tagPills ? `<div class="tag-pills">${tagPills}</div>` : ""}
      ${contactLines.length > 0 ? `<div class="contact">${contactLines.join("")}</div>` : ""}
    </div>
  `;
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeAttr(s: string): string {
  return escapeHtml(s);
}

export default function FarmMap() {
  const mapEl = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const markersRef = useRef<Map<string, CircleMarker>>(new Map());
  const leafletRef = useRef<typeof import("leaflet") | null>(null);

  const [dataset, setDataset] = useState<FarmDataset | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [filters, setFilters] = useState<FilterState>({
    kinds: new Set(),
    county: null,
    organicOnly: false,
    search: "",
    productCategories: new Set(),
  });

  // Load dataset
  useEffect(() => {
    let cancelled = false;
    fetch("/farms.json")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d: FarmDataset) => {
        if (!cancelled) setDataset(d);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Tundmatu viga");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Initialise Leaflet map after data load
  useEffect(() => {
    if (!dataset || !mapEl.current || mapRef.current) return;

    let disposed = false;

    (async () => {
      const L = await import("leaflet");
      if (disposed || !mapEl.current) return;
      leafletRef.current = L;

      const map = L.map(mapEl.current, {
        preferCanvas: true,
        zoomControl: true,
      }).setView(ESTONIA_CENTER, DEFAULT_ZOOM);

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap",
        maxZoom: 19,
      }).addTo(map);

      mapRef.current = map;

      for (const farm of dataset.records) {
        const marker = L.circleMarker([farm.lat, farm.lng], {
          radius: 4,
          color: KIND_COLORS[farm.kind],
          fillColor: KIND_COLORS[farm.kind],
          fillOpacity: 0.7,
          weight: 1,
          opacity: 0.9,
        }).addTo(map);

        marker.on("click", () => {
          if (!marker.getPopup()) {
            marker.bindPopup(buildPopupHtml(farm), {
              maxWidth: 300,
              autoPan: true,
            });
          }
          marker.openPopup();
        });

        markersRef.current.set(farm.id, marker);
      }
    })();

    return () => {
      disposed = true;
      markersRef.current.clear();
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, [dataset]);

  const filtered: Farm[] = useMemo(() => {
    if (!dataset) return [];
    return applyFilters(dataset.records, filters);
  }, [dataset, filters]);

  // Apply filter visibility & re-fit bounds
  useEffect(() => {
    const map = mapRef.current;
    const L = leafletRef.current;
    if (!map || !L || !dataset) return;

    const visible = new Set(filtered.map((f) => f.id));
    const filterActive =
      filters.kinds.size > 0 ||
      filters.county !== null ||
      filters.organicOnly ||
      filters.search.trim().length > 0 ||
      filters.productCategories.size > 0;

    const visibleLatLngs: [number, number][] = [];

    markersRef.current.forEach((marker, id) => {
      const isVisible = visible.has(id);
      if (isVisible) {
        if (!map.hasLayer(marker)) marker.addTo(map);
        marker.setStyle({
          radius: filterActive ? 6 : 4,
          fillOpacity: filterActive ? 0.9 : 0.7,
        });
        const ll = marker.getLatLng();
        visibleLatLngs.push([ll.lat, ll.lng]);
      } else {
        if (map.hasLayer(marker)) map.removeLayer(marker);
      }
    });

    if (filterActive && visibleLatLngs.length > 0) {
      map.fitBounds(L.latLngBounds(visibleLatLngs).pad(0.15), {
        animate: true,
        maxZoom: 13,
      });
    }
  }, [filtered, filters, dataset]);

  const countiesByCount = useMemo(() => {
    if (!dataset) return [];
    return Object.entries(dataset.counts_by_county)
      .filter(([county]) => county !== "NULL")
      .map(([county, count]) => ({ county, count }))
      .sort((a, b) => a.county.localeCompare(b.county, "et"));
  }, [dataset]);

  return (
    <>
      <header className="app-header">
        <div className="brand">
          <h1 className="brand-mark">
            <span className="seal" aria-hidden />
            Talu<span className="gpt">GPT</span>
          </h1>
          <div className="brand-sub">
            Eesti talud, turud &amp; kohalik toit
          </div>
        </div>
        <div className="dateline">
          <span>Aprill MMXXVI</span>
          <span className="sep" />
          <span>No. 01</span>
          <span className="sep" />
          <span>{dataset?.records.length.toLocaleString("et-EE") ?? "—"} kohta</span>
        </div>
        <div className="legend" aria-label="Tüüpide legend">
          {ALL_KINDS.map((k) => (
            <span key={k} className="chip">
              <span className="dot" style={{ backgroundColor: KIND_COLORS[k] }} />
              {KIND_LABELS[k]}
            </span>
          ))}
        </div>
        <button
          className="menu-btn"
          onClick={() => setSidebarOpen((s) => !s)}
          aria-label="Filtrid"
        >
          ☰ Filtrid
        </button>
      </header>

      <main className="app-main">
        <aside className={`sidebar${sidebarOpen ? "" : " hidden"}`}>
          {!dataset && !error && (
            <div className="match-count">Laadin andmeid…</div>
          )}
          {error && (
            <div className="match-count" style={{ color: "#c62828" }}>
              Andmete laadimine ebaõnnestus: {error}
            </div>
          )}
          {dataset && (
            <FilterPanel
              state={filters}
              onChange={setFilters}
              countiesByCount={countiesByCount}
              totalShown={filtered.length}
              totalRecords={dataset.records.length}
            />
          )}
        </aside>

        <div
          className={`overlay${sidebarOpen ? " show" : ""}`}
          onClick={() => setSidebarOpen(false)}
        />

        <div id="map" ref={mapEl} />
      </main>
    </>
  );
}
