// Product/food category IDs match the dataset's `food_categories` vocabulary
// exactly. The dataset (Full farm data.json) does the categorization upstream
// using rich Estonian keyword tagging — no stem matching needed in the client.
//
// We expose the user-facing food categories. Kind-overlap categories
// (`event`, `market`, `shop`) are intentionally omitted because those map to
// the Tüüp filter instead. `mixed_farm`, `other`, and `cosmetics_crafts` are
// also dropped to keep the filter list focused on edible-product browsing.

export type ProductCategoryId =
  | "dairy"
  | "meat"
  | "eggs"
  | "honey"
  | "vegetables"
  | "fruit_berries"
  | "grain_bakery"
  | "herbs_spices"
  | "beverages"
  | "fish"
  | "mushrooms"
  | "restaurant_cafe";

export interface ProductCategory {
  id: ProductCategoryId;
  label: string;
  emoji: string;
}

export const PRODUCT_CATEGORIES: ProductCategory[] = [
  { id: "dairy",          label: "Piim",            emoji: "🥛" },
  { id: "meat",           label: "Liha",            emoji: "🥩" },
  { id: "eggs",           label: "Munad",           emoji: "🥚" },
  { id: "honey",          label: "Mesi",            emoji: "🍯" },
  { id: "vegetables",     label: "Köögivili",       emoji: "🥕" },
  { id: "fruit_berries",  label: "Marjad & puuviljad", emoji: "🍓" },
  { id: "grain_bakery",   label: "Teravili & pagar", emoji: "🌾" },
  { id: "herbs_spices",   label: "Maitsetaimed",    emoji: "🌱" },
  { id: "beverages",      label: "Joogid",          emoji: "🍷" },
  { id: "fish",           label: "Kala",            emoji: "🐟" },
  { id: "mushrooms",      label: "Seened",          emoji: "🍄" },
  { id: "restaurant_cafe", label: "Restoran/kohvik", emoji: "🍽" },
];

const CATEGORY_BY_ID: Record<string, ProductCategory> = Object.fromEntries(
  PRODUCT_CATEGORIES.map((c) => [c.id, c])
);

export function recordMatchesAnyCategory(
  foodCategories: string[],
  selected: Set<ProductCategoryId>
): boolean {
  if (selected.size === 0) return true;
  if (foodCategories.length === 0) return false;
  for (const id of selected) {
    if (foodCategories.includes(id)) return true;
  }
  return false;
}

export function getRecordCategories(foodCategories: string[]): ProductCategory[] {
  if (foodCategories.length === 0) return [];
  return foodCategories
    .map((fc) => CATEGORY_BY_ID[fc])
    .filter((c): c is ProductCategory => Boolean(c));
}
