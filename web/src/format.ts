// Number and date formatting. Dates show in WIB, the timezone the pipeline
// uses for days.
import type { Lang } from "./i18n";

/** Locale for numbers (1.234 / 1,234). */
export const numLocale = (lang: Lang) => (lang === "id" ? "id-ID" : "en-US");
/** Locale for dates (day before month in English too). */
export const dateLocale = (lang: Lang) => (lang === "id" ? "id-ID" : "en-GB");

// toLocaleString builds a new Intl formatter on every call, which made
// re-rendering the dashboard slow; formatters are made once per option set.
const numFormats = new Map<string, Intl.NumberFormat>();
const dateFormats = new Map<string, Intl.DateTimeFormat>();

export function numFormat(locale: string, opts: Intl.NumberFormatOptions = {}): Intl.NumberFormat {
  const key = locale + JSON.stringify(opts);
  let f = numFormats.get(key);
  if (!f) numFormats.set(key, (f = new Intl.NumberFormat(locale, opts)));
  return f;
}

export function dateFormat(locale: string, opts: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = locale + JSON.stringify(opts);
  let f = dateFormats.get(key);
  if (!f) dateFormats.set(key, (f = new Intl.DateTimeFormat(locale, opts)));
  return f;
}

export function fmtInt(n: number, lang: Lang): string {
  return numFormat(numLocale(lang)).format(Math.round(n));
}

/** Up to `digits` decimals: 0,25 / 1,1. */
export function fmtNum(n: number, lang: Lang, digits: number): string {
  return numFormat(numLocale(lang), { maximumFractionDigits: digits }).format(n);
}

/** Share 0-1 as a whole percentage. */
export const fmtPct = (share: number) => `${Math.round(share * 100)}%`;

export function fmtHa(n: number, lang: Lang): string {
  if (n >= 10_000) return `${fmtShort(n, lang)} ha`;
  return `${fmtInt(n, lang)} ha`;
}

/** Compact large numbers: "370 rb" / "1,1 jt" (id), "370k" / "1.1M" (en). */
export function fmtShort(v: number, lang: Lang): string {
  if (v >= 1e6) return `${fmtNum(Math.round(v / 1e5) / 10, lang, 3)}${lang === "id" ? " jt" : "M"}`;
  return `${fmtInt(v / 1e3, lang)}${lang === "id" ? " rb" : "k"}`;
}

/** Two significant figures for estimates; millions as "1,1" (the unit is in words). */
export function fmtSig2(v: number, lang: Lang): string {
  if (v >= 1e6) return fmtNum(Math.round(v / 1e5) / 10, lang, 3);
  const p = 10 ** Math.max(0, Math.floor(Math.log10(Math.max(1, v))) - 1);
  return fmtInt(Math.round(v / p) * p, lang);
}

/** Rates per area: one decimal below 10. */
export const fmtRate = (v: number, lang: Lang) => fmtNum(v, lang, v < 10 ? 1 : 0);

/** "17 Okt 14.03": day and time of a timestamp, in WIB. */
export function fmtDate(iso: string, lang: Lang): string {
  return dateFormat(dateLocale(lang), {
    timeZone: "Asia/Jakarta",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

/** "14.03": time of day of a timestamp, in WIB. */
export function fmtClock(iso: string, lang: Lang): string {
  return dateFormat(dateLocale(lang), { timeZone: "Asia/Jakarta", hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
}

/** "17 Okt": a calendar date (YYYY-MM-DD) in WIB. */
export function fmtDay(date: string, lang: Lang): string {
  return dateFormat(dateLocale(lang), {
    timeZone: "Asia/Jakarta",
    day: "numeric",
    month: "short",
  }).format(new Date(`${date}T00:00:00+07:00`));
}

/** Calendar date (YYYY-MM-DD) of a UTC timestamp in Indonesia's western time (WIB). */
export const wibDate = (t: string) => new Date(Date.parse(t) + 7 * 3_600_000).toISOString().slice(0, 10);

/** Whole days from today (WIB) to a YYYY-MM-DD date: 0 today, 1 tomorrow, -4 four days ago. */
export const daysFromToday = (date: string) =>
  Math.round((Date.parse(`${date}T00:00:00Z`) - Date.parse(`${wibDate(new Date().toISOString())}T00:00:00Z`)) / 86_400_000);
