// Desa waspada (tables/desa.json): desa burning this week, and desa not yet
// burning that burned in many past years, with the next days' danger.
import { useEffect, useMemo, useState } from "react";
import { loadDesa, type DesaLists } from "./api/tables";
import { downloadCsvColumns } from "./download";
import { fmtDate, fmtDay, fmtInt, fmtPct } from "./format";
import type { Lang, Strings } from "./i18n";
import { MethodLink } from "./Methodology";
import { RISK_COLORS, riskClassOf } from "./palette";
import { Pager, RegionFilter, usePaged, type Region } from "./TableControls";

type List = "fire_now" | "watch";

const DESA_CSV = ["pcode", "desa", "kecamatan", "kabupaten", "provinsi", "hotspots_7d", "hotspots_24h", "last_seen", "fire_years", "peat_share", "danger_pct", "danger_pct_2", "danger_pct_3", "lon", "lat"] as const;

export function DesaTab({
  provinces,
  region,
  setRegion,
  lang,
  s,
  onOpenPlace,
}: {
  provinces: string[];
  /** shared with the other data tabs, so a chosen province stays chosen */
  region: Region;
  setRegion: (r: Region) => void;
  lang: Lang;
  s: Strings;
  onOpenPlace: (lon: number, lat: number, label: string) => void;
}) {
  const [data, setData] = useState<DesaLists | null>(null);
  const [list, setList] = useState<List>("fire_now");
  const [query, setQuery] = useState("");
  useEffect(() => {
    loadDesa().then(setData);
  }, []);
  const { provinsi: prov, kabupaten: kab } = region;
  const rows = useMemo(() => data?.[list] ?? [], [data, list]);
  const kabs = useMemo(() => [...new Set(rows.filter((r) => r.provinsi === prov).map((r) => r.kabupaten))].sort(), [rows, prov]);
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows.filter(
      (r) =>
        (!prov || r.provinsi === prov) &&
        (!kab || r.kabupaten === kab) &&
        (!q || `${r.desa} ${r.kecamatan} ${r.kabupaten}`.toLowerCase().includes(q)),
    );
  }, [rows, prov, kab, query]);
  const paged = usePaged(shown, 100);
  if (!data) return <p className="muted">{s.loading}</p>;
  const h = data.hindcast;
  return (
    <div className="table-wrap">
      <div className="filters">
        <div className="seg-row wrap">
          <button className={list === "fire_now" ? "seg on" : "seg"} onClick={() => setList("fire_now")}>
            {s.desaFireNow(fmtInt(data.fire_now.length, lang))}
          </button>
          <button className={list === "watch" ? "seg on" : "seg"} onClick={() => setList("watch")}>
            {s.desaWatch(data.watch_min_years, fmtInt(data.watch_total, lang))}
          </button>
        </div>
        <RegionFilter value={region} onChange={setRegion} provinces={provinces} regencies={kabs} s={s} />
        <input type="search" placeholder={s.desaSearch} value={query} onChange={(e) => setQuery(e.target.value)} aria-label={s.desaSearch} />
        <span className="spacer" />
        <button className="seg" onClick={() => downloadCsvColumns(`desa-waspada-${list === "fire_now" ? "api" : "pantau"}.csv`, DESA_CSV, shown, s)}>
          ⬇ CSV
        </button>
      </div>
      <p className="desa-lead">
        {list === "fire_now"
          ? s.desaLeadNow(fmtPct(h.fire_now_next_week), fmtPct(h.base_next_week), h.season)
          : s.desaLeadWatch(data.watch_min_years, data.history_years, fmtPct(h.watch_next_week), fmtPct(h.base_next_week), h.season)}{" "}
        <MethodLink id="desa" s={s} />
      </p>
      <p className="muted small">
        {s.desaCount(fmtInt(shown.length, lang))}
        {list === "watch" && data.watch_total > rows.length ? ` ${s.desaWatchCap(fmtInt(data.watch_cap_per_provinsi ?? rows.length, lang))}` : ""}
      </p>
      <table className="table data">
        <thead>
          <tr>
            <th>{s.desaName}</th>
            <th className="num">{s.data7d}</th>
            <th className="num hide-sm">{s.data24h}</th>
            <th className="num">{s.desaDanger(data.danger_date ? fmtDay(data.danger_date, lang) : "—")}</th>
            <th className="num hide-sm">{s.desaYears(data.history_years)}</th>
            <th className="num hide-sm">{s.dataPeat}</th>
          </tr>
        </thead>
        <tbody>
          {paged.rows.map((r) => (
            <tr key={r.pcode} className="clickable" onClick={() => onOpenPlace(r.lon, r.lat, `${s.desaPrefix} ${r.desa}, ${r.kecamatan}`)}>
              <td>
                {r.desa}
                <div className="muted small">
                  {r.kecamatan} · {r.kabupaten} · {r.provinsi}
                </div>
              </td>
              <td className="num">{fmtInt(r.hotspots_7d, lang)}</td>
              <td className="num hide-sm">{r.hotspots_24h ? fmtInt(r.hotspots_24h, lang) : "—"}</td>
              <td className="num">
                {r.danger_pct == null ? (
                  "—"
                ) : (
                  <>
                    <span className="swatch" style={{ background: RISK_COLORS[riskClassOf(r.danger_pct)] }} />
                    {s.riskClasses[riskClassOf(r.danger_pct)]} · {r.danger_pct}%
                  </>
                )}
                {/* The next days as small marks, for planning patrols. */}
                {(r.danger_pct_2 != null || r.danger_pct_3 != null) && (
                  <div className="risk-days" title={s.desaNextDays}>
                    {[r.danger_pct_2, r.danger_pct_3].map((v, i) =>
                      v == null ? null : (
                        <span key={i} className="swatch" style={{ background: RISK_COLORS[riskClassOf(v)] }} title={`${s.riskClasses[riskClassOf(v)]} · ${v}%`} />
                      ),
                    )}
                    <span className="muted small">{s.desaNextDays}</span>
                  </div>
                )}
              </td>
              <td className="num hide-sm">{r.fire_years || "—"}</td>
              <td className="num hide-sm">{r.peat_share ? fmtPct(r.peat_share) : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <Pager paged={paged} />
      <p className="note">
        {s.desaNote(fmtPct(h.desa_correct), fmtPct(h.kecamatan_correct))} {s.updated} {fmtDate(data.generated_at, lang)} WIB.
      </p>
    </div>
  );
}
