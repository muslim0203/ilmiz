/** Server bergan birinchi sahifa ma'lumotlari.
 *
 * Server har URL uchun `#root` ichiga tayyor HTML va (maqola sahifasida)
 * `<script id="ilmiz-data">` JSON qo'yadi. Ilgari React o'sha HTML'ni o'chirib,
 * `/api/seo` yoki `/api/articles/{id}` ni qayta so'rardi: foydalanuvchi uchun
 * miltillash, Googlebot uchun esa har sahifaga ikkinchi so'rov (crawl
 * byudjetining yarmi). Bu modul React mount bo'lishidan OLDIN o'sha
 * ma'lumotni saqlab qoladi va bir marta beradi.
 */
import type { Article } from "@/types";

type ArticleData = { kind: "article"; article: Article; related?: Article[] };
type ServerData = ArticleData | { kind: string };

const route = document.querySelector('meta[name="ilmiz-route"]')?.getAttribute("content") ?? null;

function captureShell(): string | null {
  const shell = document.querySelector("#root .seo-shell");
  if (!shell) return null;
  // Server qobig'idagi umumiy navigatsiya `ArchivePage` da kerak emas —
  // u `/api/seo` javobidagi `body` bilan bir xil bo'lishi kerak.
  const html = shell.innerHTML;
  return html.replace(/^<nav aria-label="Asosiy navigatsiya">[\s\S]*?<\/nav>/, "");
}

function captureData(): ServerData | null {
  const node = document.getElementById("ilmiz-data");
  if (!node?.textContent) return null;
  try {
    return JSON.parse(node.textContent) as ServerData;
  } catch {
    return null;
  }
}

let shell = captureShell();
let data = captureData();

/** Joriy manzil uchun server render qilgan arxiv HTML'i (bir marta). */
export function initialShell(path: string): string | null {
  if (!shell || route !== path) return null;
  const value = shell;
  shell = null;
  return value;
}

/** Server joylagan maqola va qo'shnilari, agar u shu `id` uchun bo'lsa (bir marta). */
export function initialArticle(id: string): { article: Article; related: Article[] } | null {
  if (!data || data.kind !== "article") return null;
  const payload = data as ArticleData;
  if (String(payload.article.id) !== id) return null;
  data = null;
  return { article: payload.article, related: payload.related ?? [] };
}
