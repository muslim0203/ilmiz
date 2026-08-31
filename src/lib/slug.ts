/** URL slug'lari. Backend'dagi `services/seo.py:slugify` bilan aynan bir xil
 * natija berishi shart — aks holda mijoz yasagan havola serverdagi kanonik
 * URL'ga tushmaydi va har o'tishda 301 bo'lardi. */

const CYRILLIC: Record<string, string> = {
  а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "yo", ж: "j",
  з: "z", и: "i", й: "y", к: "k", л: "l", м: "m", н: "n", о: "o",
  п: "p", р: "r", с: "s", т: "t", у: "u", ф: "f", х: "x", ц: "ts",
  ч: "ch", ш: "sh", щ: "sh", ъ: "", ы: "i", ь: "", э: "e", ю: "yu",
  я: "ya", ғ: "g", қ: "q", ҳ: "h", ў: "o",
};

const APOSTROPHES = /[ʻʼ'‘’`]/g;

/** Kichik harf + kirilldan lotinga + apostroflarni olib tashlash. */
export function normalize(value: string | null | undefined): string {
  if (!value) return "";
  let text = value.toLowerCase().replace(APOSTROPHES, "");
  text = [...text].map((char) => CYRILLIC[char] ?? char).join("");
  return text.replace(/\s+/g, " ").trim();
}

export function slugify(value: string | null | undefined, limit = 90): string {
  const text = normalize(value)
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  if (text.length <= limit) return text;
  const cut = text.slice(0, limit);
  return cut.includes("-") ? cut.slice(0, cut.lastIndexOf("-")) : cut;
}

export const journalPath = (slug: string) => `/jurnal/${slug}`;
export const journalYearPath = (slug: string, year: number) => `/jurnal/${slug}/${year}`;
export const fieldPath = (name: string) => `/soha/${slugify(name)}`;
export const cityPath = (name: string) => `/shahar/${slugify(name)}`;

export function articlePath(id: string | number, title?: string | null): string {
  const tail = slugify(title, 80);
  return tail ? `/maqola/${id}-${tail}` : `/maqola/${id}`;
}
