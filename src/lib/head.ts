/** SPA ichida o'tganda `<head>` ni yangilash.
 *
 * Birinchi yuklashda meta'larni server qo'yadi. Keyingi o'tishlar mijozda
 * bo'lgani uchun sarlavha va kanonik havola eskisi bo'lib qolardi — bu ham
 * ulashishda (Telegram, Facebook), ham Googlebot'ning ikkinchi to'lqinida
 * noto'g'ri ma'lumot berardi.
 */

export type SeoPage = { head: string; body: string; status: number; path: string };
const locationKey = () => window.location.pathname + window.location.search;
let installed = document.head.querySelector('meta[name="ilmiz-route"]') ? locationKey() : "";
let pending = "";
const requests = new Map<string, Promise<SeoPage>>();
const owned = [
  'title', 'link[rel="canonical"]', 'link[hreflang]',
  'meta[name="description"]', 'meta[name="robots"]', 'meta[name="ilmiz-route"]',
  'meta[property^="og:"]', 'meta[property^="article:"]', 'meta[name^="twitter:"]',
  'meta[name^="citation_"]', 'meta[name^="DC."]', 'script[type="application/ld+json"]',
  'meta[name="google-site-verification"]', 'meta[name="yandex-verification"]',
  'meta[name="msvalidate.01"]', 'style[data-ilmiz-critical]',
].join(',');

export function loadSeoPage(path: string): Promise<SeoPage> {
  const existing = requests.get(path);
  if (existing) return existing;
  if (requests.size > 20) requests.clear();
  const request = fetch(`/api/seo?path=${encodeURIComponent(path)}`, {
    headers: { Accept: 'application/json' },
  }).then(async response => {
    if (!response.ok) throw new Error(`SEO ${response.status}`);
    return response.json() as Promise<SeoPage>;
  }).catch(error => { requests.delete(path); throw error; });
  requests.set(path, request);
  return request;
}

export type HeadInput = {
  title: string;
  description?: string;
  /** Sayt ildizidan boshlangan yo'l; berilmasa joriy manzil olinadi. */
  path?: string;
  noindex?: boolean;
};

export async function syncHead(): Promise<void> {
  const key = locationKey();
  if (key === installed || key === pending) return;
  installed = '';
  pending = key;
  document.head.querySelectorAll(owned).forEach(element => element.remove());
  document.title = 'IlmIz';
  const robots = document.createElement('meta');
  robots.name = 'robots';
  robots.content = 'noindex, follow';
  document.head.append(robots);
  try {
    const page = await loadSeoPage(key);
    if (locationKey() !== key) return;
    const parsed = new DOMParser().parseFromString(page.head, 'text/html');
    document.head.querySelectorAll(owned).forEach(element => element.remove());
    parsed.head.querySelectorAll(owned).forEach(element => {
      document.head.append(document.importNode(element, true));
    });
    installed = key;
  } catch {
    // Keep noindex on failure, never another article's metadata.
  } finally {
    if (pending === key) pending = '';
  }
}

/** Components may request a refresh but cannot override authoritative server SEO. */
export function setHead(_input: HeadInput) { void syncHead(); }

/** Uzun matnni snippet uzunligiga sig'diradi. */
export function clip(value: string | null | undefined, limit = 158): string {
  const text = (value ?? "").replace(/\s+/g, " ").trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, limit).replace(/[\s,.;:—-]+$/, "")}…`;
}
