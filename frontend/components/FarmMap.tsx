"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Map as LeafletMap, CircleMarker, MarkerClusterGroup } from "leaflet";
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
      `<div><span class="contact-key">Veeb</span> <a href="${escapeAttr(
        href
      )}" target="_blank" rel="noopener">${escapeHtml(
        farm.contact.website
      )}</a></div>`
    );
  }
  if (farm.contact.phone) {
    contactLines.push(
      `<div><span class="contact-key">Tel.</span> <a href="tel:${escapeAttr(
        farm.contact.phone
      )}">${escapeHtml(farm.contact.phone)}</a></div>`
    );
  }
  if (farm.contact.email) {
    contactLines.push(
      `<div><span class="contact-key">Kiri</span> <a href="mailto:${escapeAttr(
        farm.contact.email
      )}">${escapeHtml(farm.contact.email)}</a></div>`
    );
  }

  const dateLine = farm.date
    ? `<div class="meta-line"><span class="meta-key">Aeg</span> ${escapeHtml(
        farm.date
      )}${farm.date_end ? ` &mdash; ${escapeHtml(farm.date_end)}` : ""}</div>`
    : "";

  return `
    <div class="popup">
      <span class="kind-tag" style="background:${color}">${label}</span>
      ${isOrganic ? '<span class="cert-organic">MAHE</span>' : ""}
      <h3>${escapeHtml(farm.name)}</h3>
      ${
        location
          ? `<div class="meta-line"><span class="meta-key">Paik</span> ${escapeHtml(
              location
            )}</div>`
          : ""
      }
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
  const clusterRef = useRef<MarkerClusterGroup | null>(null);
  const leafletRef = useRef<typeof import("leaflet") | null>(null);

  const [dataset, setDataset] = useState<FarmDataset | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(() => {
    // Component is loaded with ssr: false, so window is always defined here.
    // On phones, start with the map visible — user opens filters via the
    // hamburger button.
    if (typeof window === "undefined") return true;
    return window.innerWidth > 720;
  });
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
      const Lmod = await import("leaflet");
      // Webpack's CJS->ESM interop wraps leaflet so the namespace's named
      // getters are baked at import time. The cluster plugin mutates the
      // underlying L (adds markerClusterGroup), but those mutations don't
      // appear on the frozen namespace. Use the .default unwrap so we read
      // the live object.
      const L = ((Lmod as unknown as { default?: typeof Lmod }).default ??
        Lmod) as typeof import("leaflet");
      // The plugin's factory references L as a free variable — it needs
      // window.L set before it loads, otherwise: "ReferenceError: L is not defined".
      (window as unknown as { L: typeof import("leaflet") }).L = L;
      await import("leaflet.markercluster");
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

      const cluster = L.markerClusterGroup({
        showCoverageOnHover: false,
        // For records stacked on identical county-centroid coords, the
        // plugin automatically spiderfies on click when zoom-to-bounds
        // would be a no-op (bounds collapse to a single point).
        spiderfyOnMaxZoom: true,
        spiderfyOnEveryZoom: true,
        zoomToBoundsOnClick: true,
        maxClusterRadius: 50,
        chunkedLoading: true,
        iconCreateFunction: (c) => {
          const count = c.getChildCount();
          const size = count < 10 ? 32 : count < 100 ? 38 : count < 1000 ? 46 : 54;
          const cls =
            count < 10
              ? "tg-cluster tg-cluster-sm"
              : count < 100
              ? "tg-cluster tg-cluster-md"
              : count < 1000
              ? "tg-cluster tg-cluster-lg"
              : "tg-cluster tg-cluster-xl";
          return L.divIcon({
            html: `<div class="tg-cluster-inner"><span>${count}</span></div>`,
            className: cls,
            iconSize: [size, size],
          });
        },
      });
      clusterRef.current = cluster;

      for (const farm of dataset.records) {
        const marker = L.circleMarker([farm.lat, farm.lng], {
          radius: 5,
          color: KIND_COLORS[farm.kind],
          fillColor: KIND_COLORS[farm.kind],
          fillOpacity: 0.75,
          weight: 1,
          opacity: 0.9,
        });

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
        cluster.addLayer(marker);
      }

      cluster.addTo(map);
    })();

    return () => {
      disposed = true;
      markersRef.current.clear();
      clusterRef.current = null;
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
    const cluster = clusterRef.current;
    if (!map || !L || !cluster || !dataset) return;

    const visible = new Set(filtered.map((f) => f.id));
    const filterActive =
      filters.kinds.size > 0 ||
      filters.county !== null ||
      filters.organicOnly ||
      filters.search.trim().length > 0 ||
      filters.productCategories.size > 0;

    const visibleLatLngs: [number, number][] = [];
    const toAdd: CircleMarker[] = [];
    const toRemove: CircleMarker[] = [];

    markersRef.current.forEach((marker, id) => {
      const isVisible = visible.has(id);
      const inCluster = cluster.hasLayer(marker);
      if (isVisible) {
        if (!inCluster) toAdd.push(marker);
        marker.setStyle({
          radius: filterActive ? 7 : 5,
          fillOpacity: filterActive ? 0.95 : 0.75,
        });
        const ll = marker.getLatLng();
        visibleLatLngs.push([ll.lat, ll.lng]);
      } else if (inCluster) {
        toRemove.push(marker);
      }
    });

    // Bulk add/remove is far cheaper than per-marker for clusters.
    if (toRemove.length > 0) cluster.removeLayers(toRemove);
    if (toAdd.length > 0) cluster.addLayers(toAdd);

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

  const stats = useMemo(() => {
    if (!dataset) return { total: 0, counties: 0, producers: 0, farms: 0 };
    return {
      total: dataset.records.length,
      counties: Object.keys(dataset.counts_by_county).filter((c) => c !== "NULL")
        .length,
      producers: dataset.counts_by_kind.producer ?? 0,
      farms: dataset.counts_by_kind.farm ?? 0,
    };
  }, [dataset]);

  const fmt = (n: number) => n.toLocaleString("et-EE").replace(/,/g, " ");

  return (
    <>
      <header className="app-header">
        <div className="brand">
          <h1 className="brand-mark">
            <span className="seal" aria-hidden />
            Talu<span className="gpt">GPT</span>
          </h1>
          <div className="brand-tagline">
            Eesti talud, turud ja toidukohad
          </div>
        </div>

        <div className="stats" aria-label="Andmestiku ülevaade">
          <div className="stat">
            <span className="stat-num">{fmt(stats.total)}</span>
            <span className="stat-label">paika</span>
          </div>
          <span className="stat-divider" aria-hidden>
            ·
          </span>
          <div className="stat">
            <span className="stat-num">{stats.counties}</span>
            <span className="stat-label">maakonda</span>
          </div>
          <span className="stat-divider" aria-hidden>
            ·
          </span>
          <div className="stat">
            <span className="stat-num">{fmt(stats.producers)}</span>
            <span className="stat-label">tootjat</span>
          </div>
        </div>

        <div className="edition" aria-hidden>
          <div className="edition-vol">Aprill 2026</div>
          <div className="edition-meta">
            <span>Tallinn</span>
          </div>
        </div>

        <button
          className="menu-btn"
          onClick={() => setSidebarOpen((s) => !s)}
          aria-label="Filtrid"
        >
          Filtrid
        </button>
      </header>

      <main className="app-main">
        <aside className={`sidebar${sidebarOpen ? "" : " hidden"}`}>
          <div className="sidebar-eyebrow">
            <span className="mark" aria-hidden>
              ✦
            </span>
            Filtrid
            <span className="mark" aria-hidden>
              ✦
            </span>
          </div>

          {!dataset && !error && (
            <div className="match-count">
              <span className="match-eyebrow">Laen andmeid</span>
              <strong>…</strong>
              <div className="match-flourish" aria-hidden />
            </div>
          )}
          {error && (
            <div className="match-count" style={{ color: "var(--clay-deep)" }}>
              <span className="match-eyebrow">Viga</span>
              <span className="of">{error}</span>
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

          <footer className="colophon">
            <div className="colophon-mark" aria-hidden>
              ✦ ✦ ✦
            </div>
            <p>
              Andmed: <strong>PTA mahepõllumajanduse register</strong>
              <br />
              ja teised avalikud allikad
            </p>
            <p>Aprill 2026 · Tallinn</p>
          </footer>
        </aside>

        <div
          className={`overlay${sidebarOpen ? " show" : ""}`}
          onClick={() => setSidebarOpen(false)}
        />

        <div id="map" ref={mapEl}>
          <div className="compass-rose" aria-hidden>
            <svg viewBox="0 0 100 100">
              <circle
                cx="50"
                cy="50"
                r="44"
                fill="none"
                stroke="currentColor"
                strokeWidth="0.6"
                opacity="0.45"
              />
              <circle
                cx="50"
                cy="50"
                r="35"
                fill="none"
                stroke="currentColor"
                strokeWidth="0.35"
                opacity="0.3"
              />
              <g
                fontFamily="var(--display)"
                fontSize="5.6"
                fontStyle="italic"
                fontWeight="500"
                fill="currentColor"
                textAnchor="middle"
                opacity="0.82"
                letterSpacing="0.06em"
              >
                <text x="50" y="9.5">
                  põhi
                </text>
                <text x="50" y="96.5">
                  lõuna
                </text>
                <text x="91.5" y="52.5">
                  ida
                </text>
                <text x="8.5" y="52.5">
                  lääne
                </text>
              </g>
              <polygon
                points="50,18 53,50 50,82 47,50"
                fill="currentColor"
                opacity="0.92"
              />
              <polygon
                points="18,50 50,53 82,50 50,47"
                fill="currentColor"
                opacity="0.55"
              />
              <polygon
                points="50,30 51.5,50 50,70 48.5,50"
                fill="#c89212"
                opacity="0.85"
              />
              <circle cx="50" cy="50" r="2.2" fill="currentColor" />
              <circle
                cx="50"
                cy="50"
                r="3.4"
                fill="none"
                stroke="currentColor"
                strokeWidth="0.5"
                opacity="0.5"
              />
            </svg>
          </div>
        </div>
      </main>
    </>
  );
}
