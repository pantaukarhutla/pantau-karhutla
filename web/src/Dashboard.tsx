import { useMemo } from "react";
import { Card, More } from "./Card";
import { MethodLink } from "./Methodology";
import type { AreaEstimate, Dashboard as DashboardData } from "./api/events";
import { LineChart, type Series } from "./charts";
import { dateFormat, dateLocale, fmtDate, fmtDay, fmtInt, fmtShort, fmtSig2 } from "./format";
import type { Lang, Strings } from "./i18n";
import { REPO_URL } from "./links";

// Season comparison: categorical slots (dark steps of the validated reference
// palette) in fixed order, assigned chronologically so a season keeps its
// colour as years are added. The current season is emphasised by weight and
// a bold direct label, not by colour.
const SLOTS = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"];

const doy = (mmdd: string) => {
  const d = new Date(`2001-${mmdd}T00:00:00Z`);
  return Math.round((d.getTime() - Date.UTC(2001, 0, 1)) / 86_400_000);
};

function cumulative(points: [string, number][]): [number, number][] {
  let sum = 0;
  return points.map(([mmdd, n]) => [doy(mmdd), (sum += n)]);
}

interface Props {
  data: DashboardData;
  /** burned-area estimate, when published */
  area: AreaEstimate | null;
  lang: Lang;
  s: Strings;
  onSelect: (id: string) => void;
}

/** The pipeline runs every 2 h; a VIIRS pass is due about every 12 h. */
const RUN_LATE_H = 5;
const PASS_LATE_H = 16;

/** Top of the sidebar: how fresh the data is and how many fires burn now. */
export function Dashboard({ data, lang, s }: Pick<Props, "data" | "lang" | "s">) {
  // Ages from the browser clock, so a stopped pipeline shows as stale. VIIRS
  // passes come about 12 h apart, so a quiet morning is normal: warn only when
  // the pipeline itself is late or a pass is clearly overdue.
  const hoursSince = (iso: string) => (Date.now() - Date.parse(iso)) / 3_600_000;
  const latest = data.latest_viirs ?? data.latest_detection;
  const passLag = hoursSince(latest);
  const runLag = hoursSince(data.generated_at);
  const warning = runLag > RUN_LATE_H ? s.staleRun(runLag.toFixed(0)) : passLag > PASS_LATE_H ? s.stalePass : null;
  const c = data.counts;
  return (
    <div className="dashboard">
      <div className={warning ? "freshness stale" : "freshness"} role="status" title={s.passSchedule}>
        <span className="dot" />
        {s.latest}: {fmtDate(latest, lang)} WIB · {s.hoursAgo(passLag)}
        {warning && <div className="stale-note">{warning}</div>}
      </div>

      {/* One headline number; the rest of the counts one tap away. */}
      <div className="hero">
        <span className="hero-number">{fmtInt(c.active_multi, lang)}</span>
        <span className="hero-label">
          {s.heroLabel} <MethodLink id="events" s={s} />
        </span>
      </div>
      <p className="hero-sub">{s.heroSub(fmtInt(c.new_24h_multi, lang), fmtInt(c.cooling_multi, lang))}</p>
      <More s={s}>
        <p className="note">
          {s.singleNote(fmtInt(c.active - c.active_multi, lang))}. {s.kpiNote}
        </p>
      </More>
    </div>
  );
}

/** The season in numbers: burned area, the season curve, growing fires, provinces. */
export function FireStats({ data, area, lang, s, onSelect }: Props) {
  const series = useMemo<Series[]>(() => {
    const past = Object.entries(data.baselines)
      .sort(([a], [b]) => Number(a) - Number(b))
      .map(([year, pts]) => ({ key: year, label: year, points: cumulative(pts) }));
    const current = {
      key: String(data.season),
      label: String(data.season),
      points: cumulative(data.daily.map(([d, , , snpp]) => [d.slice(5), snpp] as [string, number])),
      emphasis: true,
    };
    return [...past, current].map((x, i) => ({ ...x, color: SLOTS[i] }));
  }, [data]);

  const months = [0, 3, 6, 9].map((m) => doy(`${String(m + 1).padStart(2, "0")}-01`));
  const monthFmt = (x: number) => dateFormat(dateLocale(lang), { month: "short", timeZone: "UTC" }).format(new Date(Date.UTC(2001, 0, 1 + x)));
  const dayFmt = (x: number) =>
    dateFormat(dateLocale(lang), { day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(Date.UTC(2001, 0, 1 + x)));
  const kFmt = (y: number) => (y >= 1000 ? fmtShort(y, lang) : String(Math.round(y)));
  const short = (v: number) => fmtShort(v, lang);
  const sig2 = (v: number) => fmtSig2(v, lang);

  const growthRow = (e: DashboardData["top_growth"][number]) => (
    <li key={e.id}>
      <button onClick={() => onSelect(e.id)}>
        <span className={`status-dot ${e.status}`} aria-label={s.status[e.status]} />
        <span className="list-name">
          {e.name}
          <small>
            {e.provinsi} · {fmtDay(String(e.date).slice(0, 10), lang)}
          </small>
        </span>
        <span className="list-value">{s.newHa(fmtInt(e.growth_ha, lang))}</span>
      </button>
    </li>
  );
  const provRows = (rows: DashboardData["by_provinsi"]) => (
    <table className="table prov-table">
      <thead>
        <tr>
          <th />
          <th className="num">{s.hotspots7d}</th>
          <th className="num">{s.provAreaHead}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((p) => {
          const a = area?.by_provinsi.find((x) => x.provinsi === p.provinsi);
          return (
            <tr key={p.provinsi}>
              <td>{p.provinsi}</td>
              <td className="num">{fmtInt(p.hotspots_7d, lang)}</td>
              <td className="num muted">{a ? s.areaRange(sig2(a.low_ha), sig2(a.high_ha)) : null}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );

  return (
    <>
      <Card title={s.topGrowth} s={s} more={data.top_growth.length > 4 && <ol className="list">{data.top_growth.slice(4, 8).map(growthRow)}</ol>}>
        <ol className="list">{data.top_growth.slice(0, 4).map(growthRow)}</ol>
      </Card>

      {area && area.national.high_ha > 0 && (
        <Card
          title={s.areaTitle}
          method="area"
          s={s}
          more={
            <>
              {area.validation?.map((v) => (
                <p key={v.provinsi} className="small validation">
                  {s.areaValidation(v.provinsi, short(v.area_ha), short(v.ci95[0]), short(v.ci95[1]), fmtInt(v.official_ha, lang))}
                </p>
              ))}
              <p className="note">{s.areaNote}</p>
            </>
          }
        >
          <div className="area-range">
            {area.national.low_ha >= 1e6
              ? s.areaRangeM(sig2(area.national.low_ha), sig2(area.national.high_ha))
              : s.areaRange(sig2(area.national.low_ha), sig2(area.national.high_ha))}
          </div>
          {area.national.official_ha != null && <p className="small">{s.areaOfficial(fmtInt(area.national.official_ha, lang))}</p>}
        </Card>
      )}

      <Card title={s.season} method="hotspots" s={s} more={<p className="note">{s.seasonNote}</p>}>
        <LineChart series={series} xFormat={monthFmt} yFormat={kFmt} xTicks={months} xTooltipFormat={dayFmt} ariaLabel={s.season} />
      </Card>

      <Card title={s.byProvinsi} s={s} more={data.by_provinsi.length > 5 && provRows(data.by_provinsi.slice(5))}>
        {provRows(data.by_provinsi.slice(0, 5))}
      </Card>

      <Card title={s.h24Title} method="counts" s={s} folded>
        <dl className="facts">
          <dt>{s.h24Public}</dt>
          <dd>{fmtInt(data.hotspots_24h.public, lang)}</dd>
          <dt>{s.h24Sipongi}</dt>
          <dd>{fmtInt(data.hotspots_24h.sipongi_like, lang)}</dd>
          <dt>{s.h24High}</dt>
          <dd>{fmtInt(data.hotspots_24h.high, lang)}</dd>
        </dl>
        {data.latest_modis && (
          <p className="note">
            MODIS {fmtDate(data.latest_modis, lang)} WIB
          </p>
        )}
      </Card>
    </>
  );
}

/** Where the numbers come from, and what this site is not. */
export function Sources({ s }: { s: Strings }) {
  return (
    <Card title={s.sourcesTitle} s={s} folded>
      <p className="note source">{s.source}</p>
      <p className="note source">
        {s.openSourceNote}{" "}
        <a href={REPO_URL} target="_blank" rel="noopener">
          GitHub
        </a>
      </p>
      <p className="note disclaimer">{s.disclaimer}</p>
    </Card>
  );
}
