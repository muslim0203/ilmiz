export const number = new Intl.NumberFormat("uz-UZ");

// `toLocaleDateString("uz-UZ", { month: "short" })` brauzerda "M08" beradi,
// shuning uchun oy nomlari qo'lda.
const MONTHS = ["yan", "fev", "mar", "apr", "may", "iyun", "iyul", "avg", "sen", "okt", "noy", "dek"];

export function shortDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return `${date.getDate()}-${MONTHS[date.getMonth()]}`;
}

export function monogram(value: string): string {
  return value.slice(0, 2).toUpperCase();
}
