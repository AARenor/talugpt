export type FarmKind = "farm" | "event" | "market" | "producer" | "shop";

export interface FarmContact {
  email: string | null;
  phone: string | null;
  website: string | null;
}

export interface Farm {
  id: string;
  kind: FarmKind;
  name: string;
  description: string;
  county: string | null;
  municipality: string | null;
  lat: number;
  lng: number;
  products: string[];
  certifications: string[];
  categories: string[];
  tags: string[];
  food_categories: string[];
  primary_food_category: string | null;
  contact: FarmContact;
  date: string | null;
  date_end: string | null;
}

export interface FarmDataset {
  generated_at: string;
  record_count: number;
  counts_by_kind: Record<string, number>;
  counts_by_county: Record<string, number>;
  counts_by_primary_food_category: Record<string, number>;
  records: Farm[];
}

import type { ProductCategoryId } from "./products";

export interface FilterState {
  kinds: Set<FarmKind>;
  county: string | null;
  organicOnly: boolean;
  search: string;
  productCategories: Set<ProductCategoryId>;
}

export const KIND_LABELS: Record<FarmKind, string> = {
  farm: "Talu",
  event: "Sündmus",
  market: "Turg",
  producer: "Tootja",
  shop: "Pood",
};

export const KIND_COLORS: Record<FarmKind, string> = {
  farm: "#1f4424",
  event: "#b4543a",
  market: "#c89212",
  producer: "#6b3a6b",
  shop: "#2a4a66",
};

export const ALL_KINDS: FarmKind[] = ["farm", "event", "market", "producer", "shop"];
