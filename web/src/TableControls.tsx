// Shared pieces of the data-view tables: paging, sortable headers and the
// province / regency filter.
import { useEffect, useState } from "react";
import type { Strings } from "./i18n";

export interface Paged<T> {
  /** rows on the current page */
  rows: T[];
  page: number;
  pages: number;
  setPage: (p: number) => void;
}

/** Split `rows` into pages; back to the first page whenever the rows change (a new filter or sort). */
export function usePaged<T>(rows: T[], pageSize: number): Paged<T> {
  const [page, setPage] = useState(0);
  useEffect(() => setPage(0), [rows]);
  return {
    rows: rows.slice(page * pageSize, (page + 1) * pageSize),
    page,
    pages: Math.ceil(rows.length / pageSize),
    setPage,
  };
}

/** ← 2 / 7 → (nothing when everything fits on one page). */
export function Pager({ paged }: { paged: Paged<unknown> }) {
  const { page, pages, setPage } = paged;
  if (pages <= 1) return null;
  return (
    <div className="pager">
      <button className="seg" disabled={page === 0} onClick={() => setPage(page - 1)}>
        ←
      </button>
      <span className="muted small">
        {page + 1} / {pages}
      </span>
      <button className="seg" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>
        →
      </button>
    </div>
  );
}

/** Numeric column header that sorts the table (largest first) by `column`. */
export function SortHeader<K extends string>({
  column,
  label,
  sort,
  setSort,
  className = "",
}: {
  column: K;
  label: string;
  sort: K;
  setSort: (k: K) => void;
  className?: string;
}) {
  const on = sort === column;
  return (
    <th className={`num ${className}`}>
      <button className={`sort ${on ? "on" : ""}`} onClick={() => setSort(column)} aria-pressed={on}>
        {label}
        {on ? " ↓" : ""}
      </button>
    </th>
  );
}

export interface Region {
  provinsi: string;
  kabupaten: string;
}
export const ALL_REGIONS: Region = { provinsi: "", kabupaten: "" };

/** Province select, plus a regency select within it when `regencies` is given. */
export function RegionFilter({
  value,
  onChange,
  provinces,
  regencies,
  s,
}: {
  value: Region;
  onChange: (r: Region) => void;
  provinces: string[];
  /** regencies of the chosen province; null: no regency select */
  regencies: string[] | null;
  s: Strings;
}) {
  return (
    <>
      <select value={value.provinsi} onChange={(e) => onChange({ provinsi: e.target.value, kabupaten: "" })} aria-label={s.dataProvince}>
        <option value="">{s.dataAllProvinces}</option>
        {provinces.map((p) => (
          <option key={p}>{p}</option>
        ))}
      </select>
      {regencies && (
        <select
          value={value.kabupaten}
          onChange={(e) => onChange({ ...value, kabupaten: e.target.value })}
          disabled={!value.provinsi}
          aria-label={s.dataRegency}
        >
          <option value="">{s.dataAllRegencies}</option>
          {regencies.map((k) => (
            <option key={k}>{k}</option>
          ))}
        </select>
      )}
    </>
  );
}
