import type { Article } from "@/types";

export type AuthUser = {
  id: number;
  provider: "orcid" | "google";
  /** Profilga ulangan barcha kirish usullari. */
  providers: string[];
  isAdmin: boolean;
  displayName: string;
  email: string | null;
  orcid: string | null;
  affiliation: string | null;
  affiliationRor: string | null;
  /** `orcid` — kirishda ORCID yozuvidan olingan; `manual` — foydalanuvchi o'zi kiritgan. */
  affiliationSource: "orcid" | "manual" | null;
  scholarUrl: string | null;
  createdAt: string;
  lastLoginAt: string | null;
};

export type ProfileDraft = {
  display_name?: string;
  affiliation?: string;
  /** Bo'sh satr — ROR bog'lanishini olib tashlaydi. */
  affiliation_ror?: string;
  scholar_url?: string;
};

export type RorOrganization = {
  id: string;
  name: string;
  localName: string | null;
  acronym: string | null;
  city: string | null;
  country: string | null;
  countryCode: string | null;
};

export async function searchRor(query: string, signal?: AbortSignal): Promise<RorOrganization[]> {
  const body = await request<{ items: RorOrganization[] }>(
    `/api/auth/ror/search?q=${encodeURIComponent(query)}`,
    { signal },
  );
  return body.items;
}

/** Sessiya cookie'da bo'lgani uchun barcha so'rovlarda `credentials` kerak. */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", Accept: "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail || `API ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function loadProviders(): Promise<string[]> {
  const body = await request<{ providers: string[] }>("/api/auth/providers");
  return body.providers;
}

export async function loadCurrentUser(): Promise<AuthUser | null> {
  const body = await request<{ user: AuthUser | null }>("/api/auth/me");
  return body.user;
}

export async function updateProfile(draft: ProfileDraft): Promise<AuthUser> {
  const body = await request<{ user: AuthUser }>("/api/auth/me", {
    method: "PATCH",
    body: JSON.stringify(draft),
  });
  return body.user;
}

export async function logout(): Promise<void> {
  await request<{ status: string }>("/api/auth/logout", { method: "POST" });
}

/** Brauzerni provayder sahifasiga yuboradi — OAuth oqimi shu yerdan boshlanadi. */
export function startLogin(provider: string): void {
  const redirect = encodeURIComponent(window.location.href);
  window.location.href = `/api/auth/${provider}/start?redirect_to=${redirect}`;
}

/** Kirgan profilga yana bir kirish usulini ulash; natija `?hisob=` bilan qaytadi. */
export function startLink(provider: string): void {
  const redirect = encodeURIComponent(window.location.href);
  window.location.href = `/api/auth/${provider}/link?redirect_to=${redirect}`;
}

export const PROVIDER_LABELS: Record<string, string> = {
  orcid: "ORCID bilan kirish",
  google: "Google bilan kirish",
};

export const PROVIDER_NAMES: Record<string, string> = {
  orcid: "ORCID",
  google: "Google",
};

export type AuthorshipStats = {
  articles: number;
  journals: number;
  firstYear: number | null;
  lastYear: number | null;
};

/** Nomzod maqola — `confidence` qanchalik ishonchli mos kelganini bildiradi.
 *
 * `exact` — ism va familiya to'liq mos keldi.
 * `partial` — jurnal faqat bosh harfni yozgan ("Karimov A."), shuning uchun
 * bu boshqa odam ham bo'lishi mumkin. */
export type ArticleSuggestion = Article & {
  confidence: "exact" | "partial";
  matchedAuthor: string;
};

export async function loadMyArticles(): Promise<{ articles: Article[]; stats: AuthorshipStats }> {
  return request<{ articles: Article[]; stats: AuthorshipStats }>("/api/auth/me/articles");
}

export async function loadArticleSuggestions(): Promise<{
  suggestions: ArticleSuggestion[];
  needsFullName: boolean;
}> {
  return request<{ suggestions: ArticleSuggestion[]; needsFullName: boolean }>(
    "/api/auth/me/article-suggestions",
  );
}

export async function claimArticle(articleId: string): Promise<AuthorshipStats> {
  const body = await request<{ stats: AuthorshipStats }>("/api/auth/me/articles", {
    method: "POST",
    body: JSON.stringify({ article_id: Number(articleId) }),
  });
  return body.stats;
}

export async function unclaimArticle(articleId: string): Promise<AuthorshipStats> {
  const body = await request<{ stats: AuthorshipStats }>(`/api/auth/me/articles/${articleId}`, {
    method: "DELETE",
  });
  return body.stats;
}
