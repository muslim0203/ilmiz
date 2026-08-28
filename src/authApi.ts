export type AuthUser = {
  id: number;
  provider: "orcid" | "google";
  isAdmin: boolean;
  displayName: string;
  email: string | null;
  orcid: string | null;
  affiliation: string | null;
  scholarUrl: string | null;
  createdAt: string;
  lastLoginAt: string | null;
};

export type ProfileDraft = {
  display_name?: string;
  affiliation?: string;
  scholar_url?: string;
};

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

export const PROVIDER_LABELS: Record<string, string> = {
  orcid: "ORCID bilan kirish",
  google: "Google bilan kirish",
};
