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

/** Bir sahifa va filtrga mos umumiy son. */
export type Page<T> = { items: T[]; total: number };

async function requestPage<T>(path: string): Promise<Page<T>> {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${path}`);
  }
  const items = (await response.json()) as T[];
  const header = response.headers.get("X-Total-Count");
  // Header yo'q bo'lsa (eski backend yoki proxy uni yutib yuborsa) hech
  // bo'lmasa shu sahifaning uzunligini qaytaramiz.
  return { items, total: header === null ? items.length : Number(header) };
}

export const PAGE_SIZE = 50;

export type FieldFacet = { name: string; journals: number; articles: number };
export type FieldGroup = { group: string; journals: number; articles: number; fields: FieldFacet[] };
export type CityFacet = { name: string; journals: number; articles: number };
export type Facets = { fieldGroups: FieldGroup[]; fieldCount: number; cities: CityFacet[] };

/** Soha, shahar va sahifa parametrlarini bitta querystringga yig'adi. */
function filterParams(fields: string[], cities: string[], offset = 0, limit = PAGE_SIZE): URLSearchParams {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  fields.forEach((item) => params.append("field", item));
  cities.forEach((item) => params.append("city", item));
  return params;
}

export async function loadCatalog(): Promise<{
  journals: Page<Journal>;
  articles: Page<Article>;
  stats: PlatformStats;
  facets: Facets;
}> {
  const [journals, articles, stats, facets] = await Promise.all([
    requestPage<Journal>(`/api/journals?limit=${PAGE_SIZE}&offset=0`),
    requestPage<Article>(`/api/articles?limit=${PAGE_SIZE}&offset=0`),
    request<PlatformStats>("/api/stats"),
    request<Facets>("/api/facets"),
  ]);
  return { journals, articles, stats, facets };
}

export async function searchJournals(
  query: string,
  fields: string[],
  cities: string[],
  offset = 0,
  oaiOnly = false,
): Promise<Page<Journal>> {
  const params = filterParams(fields, cities, offset);
  if (query.trim()) params.set("q", query.trim());
  if (oaiOnly) params.set("oai_only", "true");
  return requestPage<Journal>(`/api/journals?${params.toString()}`);
}

/** Bitta jurnalning so'nggi maqolalari (drawer uchun). */
export async function loadJournalArticles(slug: string, limit = 12): Promise<Article[]> {
  const params = new URLSearchParams({ journal_slug: slug, limit: String(limit) });
  return request<Article[]>(`/api/articles?${params.toString()}`);
}

/** Maqola kartasi va drawer uchun jurnallarning to'liq ro'yxati (493 ta). */
export async function loadJournalIndex(): Promise<Journal[]> {
  return request<Journal[]>("/api/journals?limit=500");
}

export async function loadJournal(slug: string): Promise<Journal> {
  return request<Journal>(`/api/journals/${encodeURIComponent(slug)}`);
}

export async function searchArticles(
  query: string,
  fields: string[] = [],
  cities: string[] = [],
  offset = 0,
): Promise<Page<Article>> {
  const params = filterParams(fields, cities, offset);
  if (query.trim()) params.set("q", query.trim());
  return requestPage<Article>(`/api/articles?${params.toString()}`);
}

/** Bitta maqola — `/maqola/{id}` manzili to'g'ridan-to'g'ri ochilganda. */
export async function loadArticle(id: string): Promise<Article> {
  return request<Article>(`/api/articles/${encodeURIComponent(id)}`);
}
