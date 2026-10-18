// Table downloads: the browser saves a file built here, nothing is uploaded.

/** UTC minute stamps ("2026-10-17T12:25Z") as WIB clock time, as in the app. */
const UTC_MINUTE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z$/;
const toWib = (iso: string) => `${new Date(Date.parse(iso) + 7 * 3_600_000).toISOString().slice(0, 16).replace("T", " ")} WIB`;

function csvCell(v: unknown): string {
  if (v === null || v === undefined) return "";
  const t = typeof v === "string" && UTC_MINUTE.test(v) ? toWib(v) : String(v);
  return /[",\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t;
}

export function downloadBlob(filename: string, blob: Blob) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

/** The app strings a CSV needs (Strings has them): column names by key, and
 * event status values, in the reader's language. */
interface CsvStrings {
  csvHeaders: Readonly<Record<string, string>>;
  status: Readonly<Record<string, string>>;
}

export function downloadCsv(filename: string, header: readonly string[], rows: readonly unknown[][], s: CsvStrings) {
  const head = header.map((h) => s.csvHeaders[h] ?? h);
  const statusAt = header.indexOf("status");
  const body = rows.map((r) => r.map((v, i) => (i === statusAt && typeof v === "string" ? (s.status[v] ?? v) : v)));
  const lines = [head.map(csvCell).join(","), ...body.map((r) => r.map(csvCell).join(","))];
  // A byte-order mark so Excel opens the UTF-8 file with the right letters.
  downloadBlob(filename, new Blob(["\ufeff" + lines.join("\n")], { type: "text/csv;charset=utf-8" }));
}

/** CSV of the named columns of each row object. */
export function downloadCsvColumns<T>(filename: string, columns: readonly (keyof T & string)[], rows: readonly T[], s: CsvStrings) {
  downloadCsv(
    filename,
    columns,
    rows.map((r) => columns.map((c) => r[c])),
    s,
  );
}
