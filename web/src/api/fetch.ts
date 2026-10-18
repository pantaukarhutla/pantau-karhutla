// The one way the app reads the pipeline's static files.

export const DATA_URL = (import.meta.env.VITE_DATA_URL as string | undefined) ?? "/data";

/** Absolute URL of a published file (links people open or subscribe to). */
export const dataUrl = (path: string) => new URL(`${DATA_URL}/${path}`, window.location.href).href;

export async function fetchJson<T>(path: string): Promise<T> {
  const r = await fetch(`${DATA_URL}/${path}`);
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json() as Promise<T>;
}

/** For optional files: null when missing or unreadable. */
export const tryJson = <T>(path: string): Promise<T | null> => fetchJson<T>(path).catch(() => null);

/** Columnar file: one list of column names, rows as arrays (3-5x smaller than objects). */
export interface Table {
  columns: string[];
  rows: unknown[][];
}

/** Rows as objects keyed by column. The row type is the file's contract. */
export function decodeTable<T>(t: Table): T[] {
  return t.rows.map((r) => Object.fromEntries(t.columns.map((c, i) => [c, r[i]])) as T);
}
