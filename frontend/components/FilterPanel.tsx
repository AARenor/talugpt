"use client";

import { ALL_KINDS, KIND_COLORS, KIND_LABELS, type FarmKind, type FilterState } from "@/lib/types";
import { PRODUCT_CATEGORIES, type ProductCategoryId } from "@/lib/products";

interface Props {
  state: FilterState;
  onChange: (next: FilterState) => void;
  countiesByCount: { county: string; count: number }[];
  totalShown: number;
  totalRecords: number;
}

export default function FilterPanel({
  state,
  onChange,
  countiesByCount,
  totalShown,
  totalRecords,
}: Props) {
  const toggleKind = (kind: FarmKind) => {
    const next = new Set(state.kinds);
    if (next.has(kind)) next.delete(kind);
    else next.add(kind);
    onChange({ ...state, kinds: next });
  };

  const toggleProduct = (id: ProductCategoryId) => {
    const next = new Set(state.productCategories);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange({ ...state, productCategories: next });
  };

  return (
    <>
      <div className="match-count">
        <strong>{totalShown.toLocaleString("et-EE")}</strong>
        <span className="of">
          / {totalRecords.toLocaleString("et-EE")} kohta nähtaval
        </span>
      </div>

      <div className="filter-section">
        <h2>Tüüp</h2>
        <div className="filter-grid">
          {ALL_KINDS.map((k) => {
            const active = state.kinds.has(k);
            return (
              <button
                key={k}
                onClick={() => toggleKind(k)}
                className={active ? "active" : ""}
                style={
                  active
                    ? { backgroundColor: KIND_COLORS[k], borderColor: KIND_COLORS[k] }
                    : undefined
                }
                aria-pressed={active}
              >
                <span
                  className="dot"
                  style={{ backgroundColor: active ? "#fff" : KIND_COLORS[k] }}
                />
                {KIND_LABELS[k]}
              </button>
            );
          })}
        </div>
      </div>

      <div className="filter-section">
        <h2>Maakond</h2>
        <select
          className="county-select"
          value={state.county ?? ""}
          onChange={(e) => onChange({ ...state, county: e.target.value || null })}
        >
          <option value="">Kõik maakonnad</option>
          {countiesByCount.map(({ county, count }) => (
            <option key={county} value={county}>
              {county} ({count})
            </option>
          ))}
        </select>
      </div>

      <div className="filter-section">
        <h2>Tooted</h2>
        <div className="filter-grid">
          {PRODUCT_CATEGORIES.map((c) => {
            const active = state.productCategories.has(c.id);
            return (
              <button
                key={c.id}
                onClick={() => toggleProduct(c.id)}
                className={active ? "active" : ""}
                aria-pressed={active}
              >
                <span aria-hidden>{c.emoji}</span> {c.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="filter-section">
        <h2>Sertifikaat</h2>
        <div className="filter-grid">
          <button
            onClick={() => onChange({ ...state, organicOnly: !state.organicOnly })}
            className={state.organicOnly ? "active" : ""}
            aria-pressed={state.organicOnly}
          >
            🌱 Mahe
          </button>
        </div>
      </div>

      <div className="filter-section">
        <h2>Otsi nime järgi</h2>
        <input
          className="search-input"
          type="search"
          placeholder="nt. Kase talu, mesi…"
          value={state.search}
          onChange={(e) => onChange({ ...state, search: e.target.value })}
        />
      </div>
    </>
  );
}
