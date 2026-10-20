// Data view: the same information as the map, as tables people can filter,
// sort and download (for journalists, BPBD staff, researchers).
import { useEffect, useMemo, useState } from "react";
import type { Status } from "./api/events";
import { loadFireTable, loadRegions, type FireRow, type RegencyRow, type RegionRow, type Regions } from "./api/tables";
import { loadCompare, type Compare } from "./api/compare";
import { CompareTable } from "./Compare";
import { DesaTab } from "./Desa";
import { GunungTab } from "./Gunung";
import { downloadBlob, downloadCsv, downloadCsvColumns } from "./download";
import { fmtDate, fmtDay, fmtInt, fmtPct } from "./format";
import type { Lang, Strings } from "./i18n";
import { ALL_REGIONS, Pager, RegionFilter, SortHeader, usePaged, type Region } from "./TableControls";

// One hue for magnitude sparklines (same as the event charts).
const SPARK = "#d95926";

function Sparkline({ values, label }: { values: number[]; label: string }) {
  const w = 96;
  const h = 22;
  const max = Math.max(1, ...values);
  const pts = values.map((v, i) => `${(i / Math.max(1, values.length - 1)) * w},${h - 2 - (v / max) * (h - 4)}`).join(" ");
  return (
    <svg className="spark" width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-label={label}>
      <polyline points={pts} fill="none" stroke={SPARK} strokeWidth={1.5} strokeLinejoin="round" />
    </svg>
  );
}

export type Tab = "regions" | "fires" | "desa" | "gunung" | "compare";
type RegionSort = "d7" | "h24" | "active" | "season_hotspots" | "peat_share";
type FireSort = "last_seen" | "first_seen" | "hotspot_count" | "peak_frp";

const PAGE_SIZE = 100;
const STATUSES: Status[] = ["active", "cooling", "out"];
const FIRE_CSV = ["id", "name", "status", "provinsi", "kabupaten", "first_seen", "last_seen", "hotspot_count", "peak_frp", "on_peat", "near_static", "lon", "lat"] as const;
const REGION_CSV = ["provinsi", "kabupaten", "active", "h24", "d7", "season_hotspots", "season_fires", "peat_share"];

const regionCsvRow = (r: RegionRow, kabupaten: string | null) => [r.provinsi, kabupaten, r.active, r.h24, r.d7, r.season_hotspots, r.season_fires, r.peat_share];

function downloadFiresGeojson(filename: string, rows: FireRow[]) {
  const features = rows.map(({ lon, lat, ...p }) => ({ type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] }, properties: p }));
  downloadBlob(filename, new Blob([JSON.stringify({ type: "FeatureCollection", features })], { type: "application/geo+json" }));
}

export function DataView({
  season,
  tab,
  setTab,
  lang,
  s,
  onOpenFire,
  onOpenPlace,
}: {
  season: number;
  /** in App, so #/gunung can open on its tab */
  tab: Tab;
  setTab: (t: Tab) => void;
  lang: Lang;
  s: Strings;
  onOpenFire: (id: string) => void;
  onOpenPlace: (lon: number, lat: number, label: string) => void;
}) {
  const [regions, setRegions] = useState<Regions | null>(null);
  const [fires, setFires] = useState<FireRow[] | null>(null);
  const [region, setRegion] = useState<Region>(ALL_REGIONS);
  const [status, setStatus] = useState<"" | Status>("");
  const [peatOnly, setPeatOnly] = useState(false);
  const [query, setQuery] = useState("");
  const [rSort, setRSort] = useState<RegionSort>("d7");
  const [fSort, setFSort] = useState<FireSort>("last_seen");
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    loadRegions().then(setRegions);
  }, []);
  useEffect(() => {
    if (tab !== "fires" || fires) return;
    loadFireTable(season).then(setFires);
  }, [tab, fires, season]);

  const { provinsi: prov, kabupaten: kab } = region;
  const provinces = useMemo(() => (regions ? regions.provinsi.map((p) => p.provinsi).sort() : []), [regions]);
  const kabs = useMemo(
    () => (regions && prov ? regions.kabupaten.filter((k) => k.provinsi === prov).map((k) => k.kabupaten).sort() : []),
    [regions, prov],
  );

  const filteredFires = useMemo(() => {
    if (!fires) return [];
    const q = query.trim().toLowerCase();
    const out = fires.filter(
      (f) =>
        (!prov || f.provinsi === prov) &&
        (!kab || f.kabupaten === kab) &&
        (!status || f.status === status) &&
        (!peatOnly || f.on_peat) &&
        (!q || `${f.name} ${f.kabupaten ?? ""} ${f.id}`.toLowerCase().includes(q)),
    );
    out.sort((a, b) => {
      const va = a[fSort] ?? 0;
      const vb = b[fSort] ?? 0;
      return va < vb ? 1 : va > vb ? -1 : 0;
    });
    return out;
  }, [fires, prov, kab, status, peatOnly, query, fSort]);
  const firePage = usePaged(filteredFires, PAGE_SIZE);

  const regionRows = useMemo(() => {
    if (!regions) return [];
    const rows = prov ? regions.provinsi.filter((p) => p.provinsi === prov) : [...regions.provinsi];
    return rows.sort((a, b) => b[rSort] - a[rSort]);
  }, [regions, prov, rSort]);

  const downloadRegions = () => {
    if (!regions) return;
    const rows = [...regions.provinsi.map((r) => regionCsvRow(r, null)), ...regions.kabupaten.map((r) => regionCsvRow(r, r.kabupaten))];
    downloadCsv(`wilayah-${season}.csv`, REGION_CSV, rows, s);
  };

  const tabButton = (t: Tab, label: string) => (
    <button role="tab" aria-selected={tab === t} className={tab === t ? "seg on" : "seg"} onClick={() => setTab(t)}>
      {label}
    </button>
  );

  return (
    <div className="data-view">
      <div className="data-head">
        <div className="seg-row wrap" role="tablist">
          {tabButton("regions", s.dataRegions)}
          {tabButton("fires", s.dataFires)}
          {tabButton("desa", s.desaTab)}
          {tabButton("gunung", s.gunungTab)}
          {tabButton("compare", s.dataCompare)}
        </div>
        {tab === "regions" && (
          <div className="filters">
            <RegionFilter value={region} onChange={setRegion} provinces={provinces} regencies={null} s={s} />
            <span className="spacer" />
            <button className="seg" onClick={downloadRegions}>
              ⬇ CSV
            </button>
          </div>
        )}
        {tab === "fires" && (
          <div className="filters">
            <RegionFilter value={region} onChange={setRegion} provinces={provinces} regencies={kabs} s={s} />
            <select value={status} onChange={(e) => setStatus(e.target.value as "" | Status)} aria-label={s.dataStatus}>
              <option value="">{s.dataAllStatus}</option>
              {STATUSES.map((st) => (
                <option key={st} value={st}>
                  {s.status[st]}
                </option>
              ))}
            </select>
            <label className="check">
              <input type="checkbox" checked={peatOnly} onChange={(e) => setPeatOnly(e.target.checked)} /> {s.dataPeatOnly}
            </label>
            <input type="search" placeholder={s.dataSearch} value={query} onChange={(e) => setQuery(e.target.value)} aria-label={s.dataSearch} />
            <span className="spacer" />
            <button className="seg" onClick={() => downloadCsvColumns(`kebakaran-${season}.csv`, FIRE_CSV, filteredFires, s)}>
              ⬇ CSV
            </button>
            <button className="seg" onClick={() => downloadFiresGeojson(`kebakaran-${season}.geojson`, filteredFires)}>
              ⬇ GeoJSON
            </button>
          </div>
        )}
      </div>

      {tab === "desa" && <DesaTab provinces={provinces} region={region} setRegion={setRegion} lang={lang} s={s} onOpenPlace={onOpenPlace} />}
      {tab === "gunung" && <GunungTab lang={lang} s={s} onOpenPlace={onOpenPlace} />}
      {tab === "compare" && <CompareTab lang={lang} s={s} />}

      {tab === "regions" && regions && (
        <div className="table-wrap">
          <table className="table data">
            <thead>
              <tr>
                <th>{s.dataRegion}</th>
                <SortHeader column="active" label={s.dataActive} sort={rSort} setSort={setRSort} />
                <SortHeader column="h24" label={s.data24h} sort={rSort} setSort={setRSort} className="hide-sm" />
                <SortHeader column="d7" label={s.data7d} sort={rSort} setSort={setRSort} />
                <SortHeader column="season_hotspots" label={s.dataSeason} sort={rSort} setSort={setRSort} className="hide-sm" />
                <SortHeader column="peat_share" label={s.dataPeat} sort={rSort} setSort={setRSort} className="hide-sm" />
                <th>
                  {s.data30d} <span className="muted small">({fmtDay(regions.days[0], lang)}–{fmtDay(regions.days[regions.days.length - 1], lang)})</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {regionRows.map((p) => (
                <RegionRows
                  key={p.provinsi}
                  p={p}
                  kabs={regions.kabupaten.filter((k) => k.provinsi === p.provinsi).sort((a, b) => b[rSort] - a[rSort])}
                  open={open === p.provinsi || !!prov}
                  toggle={() => setOpen(open === p.provinsi ? null : p.provinsi)}
                  lang={lang}
                  s={s}
                />
              ))}
            </tbody>
          </table>
          <p className="note">
            {s.dataRegionsNote} {s.updated} {fmtDate(regions.generated_at, lang)} WIB.
          </p>
        </div>
      )}

      {tab === "fires" && (
        <div className="table-wrap">
          {!fires ? (
            <p className="muted">{s.loading}</p>
          ) : (
            <>
              <p className="muted small">{s.dataCount(fmtInt(filteredFires.length, lang))}</p>
              <table className="table data">
                <thead>
                  <tr>
                    <th>{s.dataFire}</th>
                    <th>{s.dataStatus}</th>
                    <SortHeader column="first_seen" label={s.firstSeen} sort={fSort} setSort={setFSort} className="hide-sm" />
                    <SortHeader column="last_seen" label={s.lastSeen} sort={fSort} setSort={setFSort} />
                    <SortHeader column="hotspot_count" label={s.hotspots} sort={fSort} setSort={setFSort} />
                    <SortHeader column="peak_frp" label={s.peakFrp} sort={fSort} setSort={setFSort} className="hide-sm" />
                    <th className="hide-sm">{s.dataPeat}</th>
                  </tr>
                </thead>
                <tbody>
                  {firePage.rows.map((f) => (
                    <tr key={f.id} className="clickable" onClick={() => onOpenFire(f.id)}>
                      <td>
                        {f.name}
                        <div className="muted small">
                          {f.kabupaten} · {f.provinsi}
                          {f.near_static ? ` · ${s.dataNearIndustry}` : ""}
                        </div>
                      </td>
                      <td>
                        <span className={`status-dot ${f.status}`} /> {s.status[f.status]}
                      </td>
                      <td className="num hide-sm">{fmtDate(f.first_seen, lang)}</td>
                      <td className="num">{fmtDate(f.last_seen, lang)}</td>
                      <td className="num">{fmtInt(f.hotspot_count, lang)}</td>
                      <td className="num hide-sm">{f.peak_frp != null ? `${fmtInt(f.peak_frp, lang)} MW` : "—"}</td>
                      <td className="hide-sm">{f.on_peat ? s.yes : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Pager paged={firePage} />
              <p className="note">{s.dataFiresNote}</p>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function RegionRows({
  p,
  kabs,
  open,
  toggle,
  lang,
  s,
}: {
  p: RegionRow;
  kabs: RegencyRow[];
  open: boolean;
  toggle: () => void;
  lang: Lang;
  s: Strings;
}) {
  const cells = (r: RegionRow) => (
    <>
      <td className="num">{fmtInt(r.active, lang)}</td>
      <td className="num hide-sm">{fmtInt(r.h24, lang)}</td>
      <td className="num">{fmtInt(r.d7, lang)}</td>
      <td className="num hide-sm">{fmtInt(r.season_hotspots, lang)}</td>
      <td className="num hide-sm">{fmtPct(r.peat_share)}</td>
      <td>
        <Sparkline values={r.daily} label={s.data30d} />
      </td>
    </>
  );
  return (
    <>
      <tr className="clickable prov" onClick={toggle} aria-expanded={open}>
        <td>
          <span className="caret">{open ? "▾" : "▸"}</span> {p.provinsi}
        </td>
        {cells(p)}
      </tr>
      {open &&
        kabs.map((k) => (
          <tr key={k.kabupaten} className="kab">
            <td>{k.kabupaten}</td>
            {cells(k)}
          </tr>
        ))}
    </>
  );
}

function CompareTab({ lang, s }: { lang: Lang; s: Strings }) {
  const [data, setData] = useState<Compare | null | undefined>(undefined);
  useEffect(() => {
    loadCompare().then(setData);
  }, []);
  if (data === undefined) return <p className="muted">{s.loading}</p>;
  if (data === null) return <p className="muted">{s.cmpNone}</p>;
  return <CompareTable data={data} lang={lang} s={s} />;
}
