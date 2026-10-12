export type ImportRun = {
  id: number;
  status: string;
  sourceUrl: string;
  startedAt: string;
  finishedAt?: string | null;
  recordsSeen: number;
  registryCreated: number;
  journalsCreated: number;
  journalsUpdated: number;
  error?: string | null;
};

export type AuditJob = {
  id: number;
  journal: string;
  journalSlug: string;
  website: string;
  status: string;
  attempts: number;
  discoveredBaseUrl?: string | null;
  lastError?: string | null;
  createdAt: string;
  finishedAt?: string | null;
};

export type AdminDashboardData = {
  journals: number;
  activeJournals: number;
  removedJournals: number;
  articles: number;
  registryEntries: number;
  registryPublications: number;
  profiles: { collected: number; averageCompleteness: number };
  sources: Record<string, number>;
  auditQueue: Record<string, number>;
  profileQueue: Record<string, number>;
  latestImport: ImportRun | null;
};

export type ProfileJob = {
  id: number;
  journal: string;
  journalSlug: string;
  website: string;
  status: string;
  attempts: number;
  completenessScore?: number | null;
  lastError?: string | null;
  createdAt: string;
  finishedAt?: string | null;
};

const TOKEN_KEY = "ilmiz.adminToken";

export class AdminAuthError extends Error {
  constructor(message: string, readonly configured: boolean) {
    super(message);
    this.name = "AdminAuthError";
  }
}

export function getAdminToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    // Private rejim yoki bloklangan storage — token faqat shu sessiya uchun yo‘qoladi.
    return "";
  }
}

export function setAdminToken(token: string): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage yo‘q bo‘lsa ham so‘rovlar ishlashi kerak */
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getAdminToken();
  const response = await fetch(path, {
    ...init,
    // Admin huquqi endi sessiya cookie'si orqali ham tekshiriladi.
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(token ? { "X-Admin-Token": token } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    if (response.status === 401 || response.status === 503) {
      throw new AdminAuthError(
        payload?.detail || "Admin tokeni kerak.",
        response.status === 401,
      );
    }
    throw new Error(payload?.detail || `API ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function loadAdminData() {
  const [dashboard, jobs, profileJobs, runs] = await Promise.all([
    request<AdminDashboardData>("/api/admin/dashboard"),
    request<AuditJob[]>("/api/admin/audit/jobs?limit=20"),
    request<ProfileJob[]>("/api/admin/profile/jobs?limit=20"),
    request<ImportRun[]>("/api/admin/oak/runs?limit=5"),
  ]);
  return { dashboard, jobs, profileJobs, runs };
}

export function queueAuditJobs(limit?: number) {
  return request<{ queued: number }>("/api/admin/audit/queue", {
    method: "POST",
    body: JSON.stringify({ limit: limit ?? null }),
  });
}

export function queueProfileJobs(limit?: number, refresh = false) {
  return request<{ queued: number }>("/api/admin/profiles/queue", {
    method: "POST",
    body: JSON.stringify({ limit: limit ?? null, refresh }),
  });
}

export type JournalSummary = {
  slug: string;
  name: string;
  publisher: string;
  issn: string | null;
  city: string;
  manualFields: string[];
};

export type JournalEditValues = {
  name: string;
  short_name: string;
  publisher: string;
  city: string;
  fields: string[];
  issn: string | null;
  eissn: string | null;
  languages: string[];
  oak_status: string;
  access: string;
  founded: number | null;
  website: string | null;
  description: string | null;
  /** `journal_profiles` da turadi — to'liqlik bali aynan shularni sanaydi. */
  summary: string | null;
  address: string | null;
  latest_issue: string | null;
  publication_frequency: string | null;
  /** Jurnal sahifasining tahririyat bloklari — faqat qo'lda yoziladi. */
  about: string | null;
  chief_editor: string | null;
  submission_info: string | null;
  deadlines: string | null;
  fees: string | null;
  indexing: string[];
};

/** Rasmiy saytdan boshqa hostdan yig'ilgan yozuvlar (xato biriktirilgan sayt izi). */
export type ForeignData = {
  site: string | null;
  total: number;
  byTable: Record<string, number>;
  hosts: string[];
};

export type ContactKind = "address" | "email" | "phone";

export type JournalContact = {
  id?: number;
  kind: ContactKind;
  label: string | null;
  value: string;
  sourceUrl?: string;
  /** Qo'lda kiritilgan yoki tuzatilgan yozuv. */
  isManual?: boolean;
};

export type JournalEditRecord = {
  slug: string;
  values: JournalEditValues;
  /** Qo'lda tahrirlangan maydonlar — importlar bularga tegmaydi. */
  manualFields: string[];
  updatedAt: string | null;
  choices: { oakStatus: string[]; access: string[]; indexing: string[] };
  contacts: JournalContact[];
  foreignData: ForeignData;
  /** Ball 10 ta belgining nechtasi to'ldirilganini o'lchaydi. */
  completeness: { score: number | null; missing: string[] };
};

export type JournalEditResult = JournalEditRecord & {
  applied: string[];
  /** Bloklamaydigan ogohlantirishlar, masalan ISSN takrorlanishi. */
  warnings: string[];
};

export function searchJournals(q: string) {
  return request<{ journals: JournalSummary[] }>(
    `/api/admin/journals?q=${encodeURIComponent(q)}&limit=30`,
  );
}

export function loadJournalForEdit(slug: string) {
  return request<JournalEditRecord>(`/api/admin/journals/${encodeURIComponent(slug)}`);
}

export function saveJournal(slug: string, changes: Partial<JournalEditValues>) {
  return request<JournalEditResult>(`/api/admin/journals/${encodeURIComponent(slug)}`, {
    method: "PATCH",
    body: JSON.stringify(changes),
  });
}

export function saveContacts(slug: string, contacts: JournalContact[]) {
  return request<{ contacts: JournalContact[]; warnings: string[] }>(
    `/api/admin/journals/${encodeURIComponent(slug)}/contacts`,
    {
      method: "PUT",
      body: JSON.stringify({
        contacts: contacts.map(({ kind, value, label }) => ({ kind, value, label })),
      }),
    },
  );
}

export type AdminArticle = {
  id: number;
  title: string;
  journalName: string | null;
  journalSlug: string | null;
  journalFields: string[];
  fields: string[];
  /** Admin qo'ygan — harvest va qayta tasniflash tegmaydi. */
  fieldsManual: boolean;
  keywords: string[];
};

export function loadUnclassifiedArticles(offset = 0, journal?: string) {
  const params = new URLSearchParams({ limit: "20", offset: String(offset) });
  if (journal) params.set("journal", journal);
  return request<{ total: number; articles: AdminArticle[]; allFields: string[] }>(
    `/api/admin/articles/unclassified?${params.toString()}`,
  );
}

export function loadArticleForEdit(id: number) {
  return request<AdminArticle & { allFields: string[] }>(`/api/admin/articles/${id}`);
}

/** `fields: null` — qo'lda qo'yilganini bekor qilib, avtomatik tasnifga qaytaradi. */
export function saveArticleFields(id: number, fields: string[] | null) {
  return request<AdminArticle & { allFields: string[] }>(`/api/admin/articles/${id}/fields`, {
    method: "PUT",
    body: JSON.stringify({ fields }),
  });
}

export type SiteCheckRow = {
  slug: string;
  name: string;
  website: string | null;
  problems: string[];
  /** Sayt manzili admin tomonidan tasdiqlangan. */
  manual: boolean;
};

export function loadSiteCheck() {
  return request<{ total: number; journals: SiteCheckRow[] }>("/api/admin/journals/site-check");
}

/** Sayt tuzatilgach — eski (begona) saytdan yig'ilgan aloqa/havola/tahririyatni o'chiradi. */
export function purgeForeignData(slug: string) {
  return request<JournalEditRecord & { removed: ForeignData }>(
    `/api/admin/journals/${encodeURIComponent(slug)}/foreign-data`,
    { method: "DELETE" },
  );
}

/** «Jurnal haqida» tavsifi yo'q jurnallar CSV'ini yuklab beradi. */
export async function downloadMissingAboutCsv(): Promise<void> {
  const token = getAdminToken();
  const response = await fetch("/api/admin/journals/missing-about.csv", {
    credentials: "same-origin",
    headers: token ? { "X-Admin-Token": token } : {},
  });
  if (!response.ok) throw new Error(`API ${response.status}`);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = "jurnallar-tavsifsiz.csv";
  link.click();
  URL.revokeObjectURL(url);
}

export type AdminGuide = {
  id: number;
  slug: string;
  title: string;
  summary: string | null;
  body: string;
  isPublished: boolean;
  words: number;
  updatedAt: string | null;
};

export type GuideInput = Pick<AdminGuide, "slug" | "title" | "summary" | "body" | "isPublished">;

export function loadGuides() {
  return request<{ guides: AdminGuide[] }>("/api/admin/guides");
}

export function saveGuide(id: number | null, values: GuideInput) {
  return request<AdminGuide>(id === null ? "/api/admin/guides" : `/api/admin/guides/${id}`, {
    method: id === null ? "POST" : "PUT",
    body: JSON.stringify(values),
  });
}

export function deleteGuide(id: number) {
  return request<{ deleted: number }>(`/api/admin/guides/${id}`, { method: "DELETE" });
}
