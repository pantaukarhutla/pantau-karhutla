// Indonesia against its Southeast Asian neighbours: a sidebar card (bars)
// and a data-view table. Same satellite, same filters for every country.
import { useMemo, useState } from "react";
import type { Compare, CountryRow } from "./api/compare";
import { dateFormat, fmtDay, fmtInt, fmtPct, fmtRate, numLocale } from "./format";
import type { Lang, Strings } from "./i18n";
import { downloadCsv } from "./download";
import { Card } from "./Card";

type Period = "week" | "year";
type Metric = "total" | "area";

const monthName = (m: number, lang: Lang) => dateFormat(numLocale(lang), { month: "short", timeZone: "UTC" }).format(new Date(Date.UTC(2026, m - 1, 1)));
const name = (c: CountryRow, lang: Lang) => (lang === "id" ? c.name_id : c.name_en);

/** Detections for the chosen period: the last 7 days, one archive year, or the mean. */
function count(c: CountryRow, period: Period, year: string): number | null {
  if (period === "week") return c.last7d;
  return year === "mean" ? c.fires_mean : (c.annual[year]?.fires ?? null);
}

/** Indonesia's 2026 so far against the largest full year any other SEA country had. */
function seasonVsRecords(data: Compare) {
  const idn = data.countries.find((c) => c.iso3 === "IDN");
  if (!idn?.season_to_date || !data.season.as_of) return null;
  let top = { n: 0, who: "", year: "" };
  for (const c of data.countries) {
    if (c.iso3 === "IDN" || c.neighbour) continue;
    for (const [y, a] of Object.entries(c.annual)) if (a && a.fires > top.n) top = { n: a.fires, who: c.iso3, year: y };
  }
  return idn.season_to_date > top.n ? { n: idn.season_to_date, asOf: data.season.as_of, top } : null;
}

export function CompareCard({ data, lang, s }: { data: Compare; lang: Lang; s: Strings }) {
  const [period, setPeriod] = useState<Period>(data.recent.available ? "week" : "year");
  const [metric, setMetric] = useState<Metric>("total");
  const [year, setYear] = useState("mean");
  const sea = data.countries.filter((c) => !c.neighbour);
  const idn = data.countries.find((c) => c.iso3 === "IDN");
  const total7 = sea.reduce((t, c) => t + (c.last7d ?? 0), 0);
  const record = seasonVsRecords(data);
  const rank1 = idn ? Object.entries(idn.rank_fires_by_year).filter(([, r]) => r === 1).map(([y]) => y) : [];

  const rows = useMemo(
    () =>
      data.countries
        .map((c) => {
          const n = count(c, period, year);
          return { c, value: n === null ? null : metric === "area" ? (n / c.land_km2) * 1000 : n };
        })
        .filter((r): r is { c: CountryRow; value: number } => r.value !== null)
        .sort((a, b) => b.value - a.value),
    [data, period, metric, year],
  );
  const max = Math.max(1, ...rows.map((r) => r.value));
  const recordOwner = record && data.countries.find((c) => c.iso3 === record.top.who);

  return (
    <Card
      title={s.cmpTitle}
      method="compare"
      className="compare"
      s={s}
      folded
      lead={
        idn &&
        idn.last7d !== null &&
        total7 > 0 && (
          <p className="compare-head">
            <b>{fmtPct(idn.last7d / total7)}</b> {s.cmpShare}
          </p>
        )
      }
    >
      {idn && idn.last7d !== null && total7 > 0 && (
        <>
          <p className="compare-sub">
            {s.cmpIdn7(fmtInt(idn.last7d, lang), fmtRate(idn.per1000km2_last7d ?? 0, lang), idn.rank_last7d ?? 0, sea.length)}
          </p>
        </>
      )}
      {record && recordOwner && (
        <p className="compare-sub">
          {s.cmpSeason(fmtInt(record.n, lang), fmtDay(record.asOf, lang), `${name(recordOwner, lang)} ${record.top.year}, ${fmtInt(record.top.n, lang)}`)}
        </p>
      )}
      <div className="seg-row wrap compare-controls">
        <div className="seg-group" role="group">
          {data.recent.available && (
            <button className={period === "week" ? "seg on" : "seg"} onClick={() => setPeriod("week")}>
              {s.cmpWeek}
            </button>
          )}
          <button className={period === "year" ? "seg on" : "seg"} onClick={() => setPeriod("year")}>
            {s.cmpYear}
          </button>
        </div>
        <div className="seg-group" role="group">
          <button className={metric === "total" ? "seg on" : "seg"} onClick={() => setMetric("total")}>
            {s.cmpTotal}
          </button>
          <button className={metric === "area" ? "seg on" : "seg"} onClick={() => setMetric("area")}>
            {s.cmpPerArea}
          </button>
        </div>
        {period === "year" && (
          <select value={year} onChange={(e) => setYear(e.target.value)} aria-label={s.cmpYear}>
            <option value="mean">{s.cmpMean(data.years[0], data.last_year)}</option>
            {[...data.years].reverse().map((y) => (
              <option key={y} value={String(y)}>
                {y}
              </option>
            ))}
          </select>
        )}
      </div>
      <table className="table compare-table">
        <tbody>
          {rows.map(({ c, value }) => (
            <tr key={c.iso3} className={c.iso3 === "IDN" ? "idn" : c.neighbour ? "neighbour" : ""}>
              <td>
                {name(c, lang)}
                {c.neighbour && <span className="muted"> ({s.cmpNeighbour})</span>}
              </td>
              <td className="bar-cell" title={c.peak_month ? s.cmpPeak(monthName(c.peak_month, lang)) : undefined}>
                <span className="bar-track">
                  <span className="bar" style={{ width: `${(value / max) * 100}%` }} />
                </span>
              </td>
              <td className="num">{metric === "area" ? fmtRate(value, lang) : fmtInt(value, lang)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="note">
        {rank1.length > 0 && `${s.cmpRankYears(rank1.join(", "))} `}
        {s.cmpNote}
      </p>
    </Card>
  );
}

/** Every country and year as a table, with CSV download. */
export function CompareTable({ data, lang, s }: { data: Compare; lang: Lang; s: Strings }) {
  const years = [...data.years].reverse();
  const rows = [...data.countries].sort((a, b) => (b.last7d ?? 0) - (a.last7d ?? 0));
  const download = () => {
    const head = ["iso3", "country", "land_km2", "last7d", "per1000km2_last7d", "season_to_date", "fires_mean", "per1000km2_mean", "peak_month", ...years.map(String)];
    const body = rows.map((c) => [
      c.iso3,
      c.name_en,
      c.land_km2,
      c.last7d,
      c.per1000km2_last7d,
      c.season_to_date,
      c.fires_mean,
      c.per1000km2_mean,
      c.peak_month,
      ...years.map((y) => c.annual[y]?.fires),
    ]);
    downloadCsv("asia-tenggara-titik-panas.csv", head, body, s);
  };
  return (
    <div className="table-wrap">
      <div className="filters">
        <span className="spacer" />
        <button className="seg" onClick={download}>
          ⬇ CSV
        </button>
      </div>
      <p className="desa-lead">{s.cmpNote}</p>
      <div className="table-scroll">
        <table className="table data compare-data">
          <thead>
            <tr className="group-head">
              <th rowSpan={2}>{s.cmpCountry}</th>
              <th colSpan={2} className="num">
                {s.cmpWeek}
              </th>
              <th colSpan={2} className="num">
                {s.cmpMean(data.years[0], data.last_year)}
              </th>
              <th colSpan={years.length} className="num hide-sm">
                {s.cmpYear}
              </th>
            </tr>
            <tr>
              <th className="num">{s.cmpTotal}</th>
              <th className="num">{s.cmpPerArea}</th>
              <th className="num">{s.cmpTotal}</th>
              <th className="num">{s.cmpPerArea}</th>
              {years.map((y) => (
                <th key={y} className="num hide-sm">
                  {y}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.iso3} className={c.iso3 === "IDN" ? "idn" : ""}>
                <td>
                  {name(c, lang)}
                  {c.neighbour && <span className="muted"> ({s.cmpNeighbour})</span>}
                </td>
                <td className="num">{c.last7d === null ? "–" : fmtInt(c.last7d, lang)}</td>
                <td className="num">{c.per1000km2_last7d === null ? "–" : fmtRate(c.per1000km2_last7d, lang)}</td>
                <td className="num">{c.fires_mean === null ? "–" : fmtInt(c.fires_mean, lang)}</td>
                <td className="num hide-sm">{c.per1000km2_mean === null ? "–" : fmtRate(c.per1000km2_mean, lang)}</td>
                {years.map((y) => {
                  const a = c.annual[y];
                  return (
                    <td key={y} className="num hide-sm">
                      {a ? fmtInt(a.fires, lang) : "–"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
