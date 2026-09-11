export const number = new Intl.NumberFormat("uz-UZ");

// `toLocaleDateString("uz-UZ", { month: "short" })` brauzerda "M08" beradi,
// shuning uchun oy nomlari qo'lda.
const MONTHS = ["yan", "fev", "mar", "apr", "may", "iyun", "iyul", "avg", "sen", "okt", "noy", "dek"];

export function shortDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return `${date.getDate()}-${MONTHS[date.getMonth()]}`;
}

/** Sana va soat (mahalliy vaqt): "11-sen 08:08". */
export function shortDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  const time = `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
  return `${shortDate(value)} ${time}`;
}

export function monogram(value: string): string {
  return value.slice(0, 2).toUpperCase();
}
