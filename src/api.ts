import type { Article, Journal } from "./types";

export type PlatformStats = {
  journals: number;
  articles: number;
  healthySources: number;
};

async function request<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${path}`);
  }
  return response.json() as Promise<T>;
}

export type FieldFacet = { name: string; journals: number; articles: number };
export type FieldGroup = { group: string; journals: number; articles: number; fields: FieldFacet[] };
export type CityFacet = { name: string; journals: number; articles: number };
export type Facets = { fieldGroups: FieldGroup[]; fieldCount: number; cities: CityFacet[] };

/** Soha va shahar filtrlarini bitta querystringga yig'adi. */
function filterParams(fields: string[], cities: string[], limit = 500): URLSearchParams {
  const params = new URLSearchParams({ limit: String(limit) });
  fields.forEach((item) => params.append("field", item));
  cities.forEach((item) => params.append("city", item));
  return params;
}

export async function loadCatalog(): Promise<{
  journals: Journal[];
  articles: Article[];
  stats: PlatformStats;
  facets: Facets;
}> {
  const [journals, articles, stats, facets] = await Promise.all([
    request<Journal[]>("/api/journals?limit=500"),
    request<Article[]>("/api/articles?limit=500"),
    request<PlatformStats>("/api/stats"),
    request<Facets>("/api/facets"),
  ]);
  return { journals, articles, stats, facets };
}

export async function searchJournals(query: string, fields: string[], cities: string[]): Promise<Journal[]> {
  const params = filterParams(fields, cities);
  if (query.trim()) params.set("q", query.trim());
  return request<Journal[]>(`/api/journals?${params.toString()}`);
}

export async function loadJournal(slug: string): Promise<Journal> {
  return request<Journal>(`/api/journals/${encodeURIComponent(slug)}`);
}

export async function searchArticles(query: string, fields: string[] = [], cities: string[] = []): Promise<Article[]> {
  const params = filterParams(fields, cities);
  if (query.trim()) params.set("q", query.trim());
  return request<Article[]>(`/api/articles?${params.toString()}`);
}
