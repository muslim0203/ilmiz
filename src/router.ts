/** Yengil URL router.
 *
 * Ilgari butun sayt bitta manzilda yashardi: 467 jurnal va 104 809 maqolaning
 * birortasiga ham havola berib bo'lmasdi, qidiruv tizimlari esa indekslashga
 * biror URL topmasdi. Bu modul sahifa holatini manzil bilan bog'laydi.
 *
 * Kutubxona olinmadi — kerakli marshrutlar oltita, react-router esa bundle'ga
 * ~20 KB qo'shadi va bu sahifa tezligiga (ya'ni reytingga) urardi.
 */
import { useEffect, useState } from "react";

export type Route =
  | { kind: "home" }
  | { kind: "journals"; page: number }
  | { kind: "journal"; slug: string; year: number | null; page: number }
  | { kind: "articles"; page: number }
  | { kind: "recent"; page: number }
  | { kind: "article"; id: string }
  | { kind: "fields" }
  | { kind: "field"; slug: string; page: number }
  | { kind: "cities" }
  | { kind: "city"; slug: string; page: number }
  | { kind: "about" }
  | { kind: "search"; query: string }
  | { kind: "notFound"; path: string };

const ARTICLE = /^\/maqola\/(\d+)(?:-[^/]*)?$/;
const JOURNAL = /^\/jurnal\/([^/]+)(?:\/(\d{4}))?$/;
const FIELD = /^\/soha\/([^/]+)$/;
const CITY = /^\/shahar\/([^/]+)$/;

function pageOf(params: URLSearchParams): number {
  const value = Number(params.get("sahifa") ?? params.get("page") ?? "1");
  return Number.isInteger(value) && value > 0 ? Math.min(value, 5000) : 1;
}

export function parseRoute(pathname: string, search: string): Route {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : "/";
  const params = new URLSearchParams(search);

  if (path === "/") return { kind: "home" };
  if (path === "/jurnallar") return { kind: "journals", page: pageOf(params) };
  if (path === "/maqolalar") return { kind: "articles", page: pageOf(params) };
  if (path === "/yangi-maqolalar") return { kind: "recent", page: pageOf(params) };
  if (path === "/sohalar") return { kind: "fields" };
  if (path === "/shaharlar") return { kind: "cities" };
  if (path === "/loyiha") return { kind: "about" };
  if (path === "/qidiruv") return { kind: "search", query: params.get("q") ?? "" };

  const article = ARTICLE.exec(path);
  if (article) return { kind: "article", id: article[1] };

  const journal = JOURNAL.exec(path);
  if (journal) {
    return { kind: "journal", slug: journal[1], year: journal[2] ? Number(journal[2]) : null, page: pageOf(params) };
  }

  const field = FIELD.exec(path);
  if (field) return { kind: "field", slug: field[1], page: pageOf(params) };

  const city = CITY.exec(path);
  if (city) return { kind: "city", slug: city[1], page: pageOf(params) };

  return { kind: "notFound", path };
}

function currentRoute(): Route {
  return parseRoute(window.location.pathname, window.location.search);
}

const listeners = new Set<() => void>();

function announce() {
  listeners.forEach((listener) => listener());
}

export function navigate(href: string, options: { replace?: boolean } = {}) {
  const target = new URL(href, window.location.origin);
  const same =
    target.pathname === window.location.pathname && target.search === window.location.search;
  if (same) return;
  if (options.replace) {
    window.history.replaceState(null, "", target);
  } else {
    window.history.pushState(null, "", target);
    // Yangi sahifa har doim tepadan boshlansin — brauzer SPA'da o'zi
    // qaytarmaydi va foydalanuvchi ro'yxatning o'rtasiga tushib qolardi.
    window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
  }
  announce();
}

/** Joriy manzilni kuzatadigan hook. */
export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(currentRoute);

  useEffect(() => {
    const update = () => setRoute(currentRoute());
    listeners.add(update);
    window.addEventListener("popstate", update);
    return () => {
      listeners.delete(update);
      window.removeEventListener("popstate", update);
    };
  }, []);

  return route;
}

/** `<a href>` ni saqlab qolgan holda SPA ichida o'tish.
 *
 * Havola haqiqiy bo'lishi shart: robot `href` ni o'qiydi, foydalanuvchi esa
 * "yangi oynada ochish" va holat qatoridagi manzilni yo'qotmaydi.
 */
export function linkHandler(href: string) {
  return (event: React.MouseEvent<HTMLAnchorElement>) => {
    if (event.defaultPrevented) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (event.button !== 0) return;
    event.preventDefault();
    navigate(href);
  };
}
