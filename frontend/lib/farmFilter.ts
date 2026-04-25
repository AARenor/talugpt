import { recordMatchesAnyCategory } from "./products";
import type { Farm, FilterState } from "./types";

export function applyFilters(records: Farm[], state: FilterState): Farm[] {
  const search = state.search.trim().toLowerCase();
  return records.filter((r) => {
    if (state.kinds.size > 0 && !state.kinds.has(r.kind)) return false;
    if (state.county && r.county !== state.county) return false;
    if (state.organicOnly) {
      const hasOrganic = r.certifications.some(
        (c) => c.toLowerCase() === "mahe" || c.toLowerCase() === "organic"
      );
      if (!hasOrganic) return false;
    }
    if (
      state.productCategories.size > 0 &&
      !recordMatchesAnyCategory(r.food_categories, state.productCategories)
    ) {
      return false;
    }
    if (search) {
      const haystack = [
        r.name,
        r.municipality ?? "",
        r.county ?? "",
        r.tags.join(" "),
        r.products.join(" "),
        r.categories.join(" "),
        r.description,
      ]
        .join(" ")
        .toLowerCase();
      if (!haystack.includes(search)) return false;
    }
    return true;
  });
}
