import { useEffect, useRef, useState } from "react";
import type { Playback } from "./hooks/usePlayback";
import { PlaybackSlider } from "./PlaybackSlider";
import { Card } from "./Card";
import type { Focus, LayerToggles } from "./MapView";
import { dataUrl } from "./api/fetch";
import type { CityOutlook, ForecastCheck, Stations, Transboundary } from "./api/air";
import type { Alert, Alerts, Danger, FireHistory, Outlook, ProvinceDanger } from "./api/fire";
import { ispuOf } from "./ispu";
import { HISTORY_COLORS, RISK_COLORS } from "./palette";
import { dateFormat, dateLocale, daysFromToday, fmtDate, fmtDay, fmtInt, fmtNum, fmtPct, wibDate } from "./format";
import type { HealthLevel, Lang, Strings } from "./i18n";

// Haze time slider: -72 h .. +72 h in 3-hour steps; it opens at now.
export function ForecastBar({ times, p, nowIndex, lang, s }: { times: string[]; p: Playback; nowIndex: number; lang: Lang; s: Strings }) {
  if (!times.length) return null;
  const t = times[p.index];
  const now = p.index === nowIndex;
  // "Besok, 14.00 WIB" reads better than "+27 jam".
  const dayWord = relativeDay(wibDate(t), lang, s);
  const clock = new Date(t).toLocaleTimeString(dateLocale(lang), { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Jakarta" });
  return (
    <PlaybackSlider p={p} min={0} max={times.length - 1} label={s.forecast} className="forecast-bar" wordy={false} s={s}>
      <span className="forecast-label">
        <b>{now ? s.hoursAhead(0) : dayWord}</b> · {now ? fmtDate(t, lang) : clock} WIB
      </span>
    </PlaybackSlider>
  );
}

const LAYER_GROUPS: { title: "groupFire" | "groupAir" | "groupLand" | "groupMap"; keys: (keyof LayerToggles)[] }[] = [
  { title: "groupFire", keys: ["flames", "glow", "risk", "spread", "columns"] },
  { title: "groupAir", keys: ["stations", "smog", "himawari", "aod", "plumes", "wind"] },
  { title: "groupLand", keys: ["boundaries", "peat", "burnHistory"] },
  { title: "groupMap", keys: ["satellite"] },
];


export function LayerPanel({
  layers,
  setLayers,
  s,
  fold,
}: {
  layers: LayerToggles;
  setLayers: (l: LayerToggles) => void;
  s: Strings;
  /** fold the panel away (e.g. when a fire is opened); the reader can reopen it */
  fold?: boolean;
}) {
  const ref = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    if (fold && ref.current) ref.current.open = false;
  }, [fold]);
  const label: Record<keyof LayerToggles, string> = {
    satellite: s.layerSatellite,
    boundaries: s.layerBoundaries,
    peat: s.layerPeat,
    flames: s.layerFlames,
    glow: s.layerGlow,
    columns: s.layerColumns,
    stations: s.layerStations,
    risk: s.layerRisk,
    burnHistory: s.layerBurnHistory,
    smog: s.layerSmog,
    aod: s.layerAod,
    himawari: s.layerHimawari,
    plumes: s.layerPlumes,
    wind: s.layerWind,
    spread: s.layerSpread,
  };
  const on = Object.values(layers).filter(Boolean).length;
  return (
    // Open on desktop so the toggles are obvious; collapsed on phones.
    <details ref={ref} className="layer-panel">
      <summary aria-label={`${s.layers} (${on})`}>
        <span aria-hidden>☰</span> <span className="layer-word">{s.layers}</span> <span className="muted">({on})</span>
      </summary>
      {LAYER_GROUPS.map((g) => (
        <fieldset key={g.title}>
          <legend className="sr-only">{s[g.title]}</legend>
          <div className="group-title" aria-hidden>
            {s[g.title]}
          </div>
          {g.keys.map((k) => (
            <label key={k}>
              <input type="checkbox" checked={layers[k]} onChange={(e) => setLayers({ ...layers, [k]: e.target.checked })} />
              {label[k]}
            </label>
          ))}
        </fieldset>
      ))}
    </details>
  );
}

export function StationsList({ data, lang, s }: { data: Stations; lang: Lang; s: Strings }) {
  // Fresh readings only, highest first.
  const ranked = data.stations
    .flatMap((st) => (st.pm25 !== null && !st.stale ? [{ ...st, pm25: st.pm25 }] : []))
    .sort((a, b) => b.pm25 - a.pm25)
    .slice(0, 8);
  if (!ranked.length) return null;
  const SHOWN = 5;
  const cmp = data.cams_vs_obs;
  // 2 significant figures above 100: single hourly readings are not that precise.
  const round2 = (v: number) => (v >= 100 ? Math.round(v / 10 ** (Math.floor(Math.log10(v)) - 1)) * 10 ** (Math.floor(Math.log10(v)) - 1) : Math.round(v));
  const rows = (list: typeof ranked) => (
    <table className="table cities">
      <tbody>
        {list.map((st) => {
          const cat = ispuOf(st.pm25);
          return (
            <tr key={`${st.network}-${st.id}`} title={st.estimated ? s.estimated : undefined}>
              <td>
                {st.name}
                <div className="muted small">
                  {st.region} · {fmtDate(st.time, lang)} WIB
                </div>
              </td>
              <td className="num">
                {st.estimated || st.pm25 >= 100 ? "≈" : ""}
                {fmtInt(round2(st.pm25), lang)} µg/m³ <span className={`ispu ${cat}`}>{s.ispu[cat]}</span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
  return (
    <Card
      title={s.stationsTitle}
      method="stations"
      s={s}
      more={
        <>
          {ranked.length > SHOWN && rows(ranked.slice(SHOWN))}
          {cmp && cmp.haze_median_ratio != null && cmp.haze_median_ratio < 0.8 && (
            <div className="callout warn">
              {s.camsLow(cmp.haze_stations, Math.round(cmp.haze_median_ratio * 100), cmp.stations, Math.round(cmp.median_ratio * 100))}
            </div>
          )}
          <p className="note">
            {s.stationsNote} {s.updated} {fmtDate(data.generated_at, lang)} WIB.
          </p>
        </>
      }
    >
      {rows(ranked.slice(0, SHOWN))}
    </Card>
  );
}

// Model values above 500 µg/m³ are beyond what it can resolve.
const capPm = (v: number) => (v > 500 ? "> 500" : String(Math.round(v)));

/** "Sab 18 Okt, pagi" rather than a minute-precise time from 3-hourly frames. */
function halfDay(iso: string, lang: Lang, s: Strings): string {
  const d = new Date(iso);
  const hour = Number(dateFormat("en-GB", { hour: "2-digit", hour12: false, timeZone: "Asia/Jakarta" }).format(d));
  const day = dateFormat(dateLocale(lang), { weekday: "short", day: "numeric", month: "short", timeZone: "Asia/Jakarta" }).format(d);
  return `${day}, ${hour < 12 ? s.morning : hour < 18 ? s.afternoon : s.evening}`;
}

export function Cities({ cities, lang, s }: { cities: CityOutlook[]; lang: Lang; s: Strings }) {
  // Cities where fire smoke is expected first, then by forecast PM2.5 peak.
  const ranked = [...cities]
    .sort((a, b) => b.fire_smoke_peak - a.fire_smoke_peak || (b.pm25_days[0] ?? 0) - (a.pm25_days[0] ?? 0))
    .slice(0, 8);
  return (
    <Card title={s.cities} method="cities" s={s} folded>
      <table className="table cities">
        <thead>
          <tr>
            <th />
            <th className="num">{s.pmTomorrow}</th>
            <th className="num">{s.pmLater}</th>
            <th className="num">{s.smokeArrives}</th>
          </tr>
        </thead>
        <tbody>
          {ranked.map((c) => (
            <tr key={c.name}>
              <td>{c.name}</td>
              <td className="num">
                {c.pm25_day1_range ? `${capPm(c.pm25_day1_range[0])}–${capPm(c.pm25_day1_range[1])}` : "—"}
                {c.ispu_days[0] && <span className={`ispu ${c.ispu_days[0]}`}>{s.ispu[c.ispu_days[0]]}</span>}
              </td>
              <td className="num">
                {c.ispu_days.slice(1).map((cat, i) =>
                  cat ? (
                    <span key={i} className={`ispu ${cat}`}>
                      {s.ispu[cat]}
                    </span>
                  ) : null,
                )}
              </td>
              <td className="num">
                {c.fire_smoke_already ? s.alreadySmoky : c.fire_smoke_arrival ? halfDay(c.fire_smoke_arrival, lang, s) : s.noFireSmoke}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="note">{s.citiesNote}</p>
    </Card>
  );
}

export function TransboundaryPanel({
  data,
  lang,
  s,
  onSelect,
}: {
  data: Transboundary;
  lang: Lang;
  s: Strings;
  onSelect: (id: string) => void;
}) {
  return (
    <Card title={s.tbTitle} method="transboundary" s={s} folded>
      <p className="note">{s.tbIntro}</p>
      <table className="table cities tb">
        <tbody>
          {data.receptors.map((r) => {
            const pm = r.observed?.pm25 ?? r.pm25_now;
            const cat = ispuOf(pm);
            const named = r.provinces.filter((p) => p.name).slice(0, 2);
            // Round to 10%: a single-run model cannot support more precision.
            const p10 = (x: number) => `≈${Math.max(10, Math.round(x * 10) * 10)}%`;
            return (
              <tr key={r.name}>
                <td>
                  {r.name} <span className="muted small">{s.country[r.country]}</span>
                  <div className="muted small">
                    {r.reliable && named.length ? (
                      <>
                        {r.already_smoky ? `${s.alreadySmoky} · ` : ""}
                        {s.tbFrom} {named.map((p) => `${p.name} (${p10(p.share)})`).join(", ")}
                        {r.peat_share != null && ` · ${s.tbPeat} ${p10(r.peat_share)}`}
                      </>
                    ) : (
                      s.tbNone
                    )}
                  </div>
                  {r.reliable && r.fires[0] && (
                    <button className="linkish small" onClick={() => onSelect(r.fires[0].id)}>
                      {s.tbBiggest}: {r.fires[0].name}
                    </button>
                  )}
                </td>
                <td className="num">
                  {r.observed?.estimated ? "≈" : ""}
                  {Math.round(pm)} <span className={`ispu ${cat}`}>{s.ispu[cat]}</span>
                  <div className="muted small">
                    {r.observed ? (r.observed.estimated ? s.estimatedShort : s.tbMeasured) : s.tbForecast}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="note">
        {s.tbNote(data.share_window_h)} {s.updated} {fmtDate(data.generated_at, lang)} WIB.
      </p>
    </Card>
  );
}

/** "Hari ini" / "Besok" / "Lusa" for a WIB date, else the date itself. */
function relativeDay(date: string, lang: Lang, s: Strings): string {
  const days = daysFromToday(date);
  return days === 0 ? s.today : days === 1 ? s.tomorrow : days === 2 ? s.dayAfter : days === -1 ? s.yesterday : fmtDay(date, lang);
}

export function RiskPanel({ data, lang, s, onShow }: { data: Danger; lang: Lang; s: Strings; onShow: () => void }) {
  // The card has its own day choice; the map layer follows the time slider.
  const [day, setDay] = useState(0);
  const days = data.days.filter((d, i) => i === 0 || d.provinces).slice(0, 3);
  const d = days[Math.min(day, days.length - 1)];
  const sk = data.skill?.lead1;
  if (!d) return null;
  // Worst first, so the table and the headline agree.
  const provinces = (d.provinces ?? data.provinces)
    .filter((p) => p.high_share > 0)
    .sort((a, b) => b.extreme_share - a.extreme_share || b.high_share - a.high_share);
  const worst = provinces[0];
  const rows = (ps: ProvinceDanger[], head: boolean) => (
    <table className="table">
      {head && (
        <thead>
          <tr>
            <th />
            <th className="num">{s.riskClasses[3]}</th>
            <th className="num">{s.riskClasses[2]}</th>
          </tr>
        </thead>
      )}
      <tbody>
        {ps.map((p) => (
          <tr key={p.provinsi}>
            <td>{p.provinsi}</td>
            <td className="num">
              <span className="swatch" style={{ background: RISK_COLORS[3] }} /> {fmtPct(p.extreme_share)}
            </td>
            <td className="num">
              <span className="swatch" style={{ background: RISK_COLORS[2] }} /> {fmtPct(p.high_share - p.extreme_share)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
  const dayName = (i: number) => relativeDay(days[i].date, lang, s);
  return (
    <Card
      title={s.riskTitle(dateFormat(dateLocale(lang), { weekday: "long", day: "numeric", month: "short" }).format(new Date(`${d.date}T12:00:00+07:00`)))}
      method="danger"
      action={
        <button className="link" onClick={onShow}>
          {s.riskShow}
        </button>
      }
      s={s}
      folded
      lead={worst && worst.extreme_share > 0 ? s.riskLead(worst.provinsi, fmtPct(worst.extreme_share)) : undefined}
      more={
        <>
          {provinces.length > 6 && rows(provinces.slice(6), false)}
          <p className="note">
            {s.riskNote}
            {data.issued && ` ${s.riskIssued(fmtDay(data.issued, lang), -daysFromToday(data.issued))}`}
            {sk && ` ${s.riskSkill(fmtNum(sk.auc, lang, 2), Math.round((sk.classes.find((c) => c.class === 3)?.observed_rate ?? 0) * 100), fmtNum((sk.classes.find((c) => c.class === 0)?.observed_rate ?? 0) * 100, lang, 1))}`}{" "}
            {s.updated} {fmtDate(data.generated_at, lang)} WIB.
          </p>
        </>
      }
    >
      {days.length > 1 && (
        <div className="seg-row" role="group" aria-label={s.forecast}>
          {days.map((x, i) => (
            <button key={x.date} className={i === day ? "seg on" : "seg"} onClick={() => setDay(i)}>
              {dayName(i)}
            </button>
          ))}
        </div>
      )}
      {rows(provinces.slice(0, 6), true)}
    </Card>
  );
}

export function OutlookCard({ data, lang, s }: { data: Outlook; lang: Lang; s: Strings }) {
  const oni = data.oni[data.oni.length - 1];
  const wk = data.nino34_weekly[data.nino34_weekly.length - 1];
  const iod = data.iod_weekly[data.iod_weekly.length - 1];
  if (!oni && !iod) return null;
  const n = (v: number) => `${v > 0 ? "+" : ""}${fmtNum(v, lang, 2)}`;
  const warn = data.enso_phase?.startsWith("el_nino") || data.iod_positive;
  return (
    <Card
      title={s.outlookTitle}
      method="outlook"
      className={warn ? "outlook warn" : "outlook"}
      s={s}
      folded
      lead={data.enso_phase && <span className="outlook-head">{s.ensoPhase[data.enso_phase]}</span>}
    >
      <dl className="facts">
        {oni && (
          <>
            <dt>{s.oniLabel(oni.season, oni.year)}</dt>
            <dd>{n(oni.anom)} °C</dd>
          </>
        )}
        {wk && (
          <>
            <dt>{s.ninoWeekly(fmtDay(wk.week, lang))}</dt>
            <dd>{n(wk.nino34)} °C</dd>
          </>
        )}
        {iod && (
          <>
            <dt>{s.iodLabel(fmtDay(iod.week_end, lang))}</dt>
            <dd>
              {n(iod.iod)} °C{data.iod_positive ? ` · ${s.iodPositive}` : ""}
            </dd>
          </>
        )}
      </dl>
      {data.dry_chance.length > 0 && (
        <>
          <h3 className="sub">{s.dryTitle(data.dry_threshold_mm_day)}</h3>
          <table className="table">
            <tbody>
              {data.dry_chance.map((d) => (
                <tr key={d.provinsi}>
                  <td>{d.provinsi}</td>
                  <td className="num">{fmtPct(d.dry30)}</td>
                  <td className="num muted">{fmtPct(d.dry60)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      <p className="note">{s.outlookNote}</p>
    </Card>
  );
}

// Repeat burning (fire_history.json): how much of this season's fire is on
// land that already burned, by province.
export function RepeatBurnCard({ data, lang, s, onShow }: { data: FireHistory; lang: Lang; s: Strings; onShow: () => void }) {
  const nat = data.national;
  if (!nat) return null;
  const [y0, y1] = data.history_years;
  const lift = nat.lift === undefined ? null : fmtNum(nat.lift, lang, 1);
  const hc = data.hindcast;
  return (
    <Card
      title={s.repeatTitle}
      method="repeat"
      className="repeat"
      action={
        <button className="link" onClick={onShow}>
          {s.riskShow}
        </button>
      }
      s={s}
      folded
      lead={
        <p className="repeat-head">
          <b>{fmtPct(nat.share_before)}</b> {s.repeatHead(data.season, y0, y1)}
        </p>
      }
    >
      {data.peat && data.non_peat && <p className="repeat-sub">{s.repeatPeat(fmtPct(data.peat.share_before), fmtPct(data.non_peat.share_before))}</p>}
      {lift && <p className="repeat-sub">{s.repeatLift(fmtPct(data.prior_land_share), lift)}</p>}
      <div className="repeat-legend">
        <span>
          <span className="swatch" style={{ background: HISTORY_COLORS[3] }} />
          {s.repeatTwice}
        </span>
        <span>
          <span className="swatch" style={{ background: HISTORY_COLORS[1] }} />
          {s.repeatOnce}
        </span>
      </div>
      <table className="table repeat-table">
        <tbody>
          {data.by_provinsi.slice(0, 8).map((p) => (
            <tr key={p.provinsi}>
              <td>{p.provinsi}</td>
              <td className="bar-cell" title={`${fmtPct(p.share_before)} · ≥2: ${fmtPct(p.share_before2)}`}>
                <span className="bar-track">
                  <span className="bar once" style={{ width: fmtPct(p.share_before) }} />
                  <span className="bar twice" style={{ width: fmtPct(p.share_before2) }} />
                </span>
              </td>
              <td className="num">{fmtPct(p.share_before)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="note">
        {hc && `${s.repeatHindcast(hc.season, fmtPct(hc.share_in_prior_burned), fmtPct(hc.prior_land_share), y0, hc.season - 1)} `}
        {s.repeatNote}
      </p>
    </Card>
  );
}

// What to do tomorrow, per forecast ISPU category: school mode from SE
// Mendikdasmen 20/2026 and Kemenkes advice. Guidance only: schools follow the
// dinas pendidikan, which uses the official daily ISPU.
const HEALTH_ORDER: HealthLevel[] = ["berbahaya", "sangat_tidak_sehat", "tidak_sehat", "sedang"];

export function HealthCard({ cities, check, s }: { cities: CityOutlook[]; check: ForecastCheck | null; s: Strings }) {
  // Indonesian rules: Indonesian cities only, worst first.
  const local = cities.filter((c) => c.country !== "other");
  const groups = HEALTH_ORDER.map((cat) => ({ cat, names: local.filter((c) => c.ispu_days[0] === cat).map((c) => c.name) })).filter(
    (g) => g.names.length,
  );
  if (!groups.length) return null;
  const lead0 = check?.leads.find((l) => l.lead_day === 0);
  const group = (g: (typeof groups)[number]) => (
    <div key={g.cat} className={`health-group ${g.cat}`}>
      <div className="health-head">
        <span className={`ispu ${g.cat}`}>{s.ispu[g.cat]}</span>
        <span className="health-cities">
          {g.names.slice(0, 6).join(", ")}
          {g.names.length > 6 && <span className="muted"> {s.andMore(g.names.length - 6)}</span>}
        </span>
      </div>
      <ul>
        <li>
          <b>{s.healthSchool}</b> {s.healthSchoolRule[g.cat]}
        </li>
        <li>
          <b>{s.healthPublic}</b> {s.healthPublicRule[g.cat]}
        </li>
      </ul>
    </div>
  );
  return (
    <Card
      title={s.healthTitle}
      method="health"
      className="health"
      s={s}
      more={
        <>
          {groups.slice(2).map(group)}
          <p className="note">
            {s.healthNote}
            {check && lead0
              ? ` ${s.healthCheck(check.window_days, lead0.n, Math.round(lead0.hit * 100), Math.round(lead0.within_one * 100), lead0.persistence_hit != null ? Math.round(lead0.persistence_hit * 100) : null)}`
              : ` ${s.healthCheckPending}`}
          </p>
        </>
      }
    >
      {groups.slice(0, 2).map(group)}
    </Card>
  );
}

// Latest alerts, nationally or for one province, with the matching Atom
// feed to subscribe to (any feed reader, email digest or chat bot).
const ALERT_COLOR: Record<Alert["kind"], string> = { fire: "#ff7a1a", growth: "#ffb020", danger: "#e5322d", air: "#9085e9" };

export function AlertsCard({ data, lang, s, onSelect, onLook }: { data: Alerts; lang: Lang; s: Strings; onSelect: (id: string) => void; onLook: (f: Focus) => void }) {
  const [prov, setProv] = useState<string>("");
  const provinces = Object.keys(data.feeds).filter((k) => k !== "indonesia").sort();
  const all = data.alerts.filter((a) => (prov ? a.provinsi === prov : a.kind === "growth" || a.kind === "air" || (a.kind === "fire" && a.national)));
  // Air alerts all carry the forecast run's time: fold them into one line so
  // they do not push the fire alerts off the card.
  const air = all.filter((a) => a.kind === "air");
  const list = all.filter((a) => a.kind !== "air").slice(0, 10);
  const SHOWN = 4;
  const feed = dataUrl(data.feeds[prov || "indonesia"] ?? data.feeds.indonesia);
  const open = (a: Alert) => {
    if ("event" in a) onSelect(a.event);
    else if ("lon" in a) onLook({ lon: a.lon, lat: a.lat, zoom: 8 });
  };
  const items = (xs: Alert[]) => (
    <ul className="alert-list">
      {xs.map((a) => (
        <li key={a.id}>
          <button onClick={() => open(a)} disabled={a.kind === "danger"}>
            <span className="alert-dot" style={{ background: ALERT_COLOR[a.kind] }} />
            <span className="alert-body">
              <span className="alert-title">{s.alertText(a)}</span>
              <span className="muted">
                {fmtDate(a.time, lang)} WIB{a.provinsi && !prov ? ` · ${a.provinsi}` : ""}
              </span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
  return (
    <Card
      title={s.alertsTitle}
      method="alerts"
      className="alerts"
      s={s}
      more={
        <>
          {list.length > SHOWN && items(list.slice(SHOWN))}
          <p className="note">{s.alertsNote}</p>
        </>
      }
    >
      <div className="alerts-head">
        <select value={prov} onChange={(e) => setProv(e.target.value)} aria-label={s.alertsProvince}>
          <option value="">{s.alertsNational}</option>
          {provinces.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        <a className="link" href={feed} target="_blank" rel="noreferrer" title={s.alertsFeedHint}>
          {s.alertsSubscribe}
        </a>
      </div>
      {air.length > 0 && (
        <p className="alert-air">
          <span className="alert-dot" style={{ background: ALERT_COLOR.air }} />
          <span>
            {s.alertsAir}{" "}
            {air.slice(0, 6).map((a, i) => (
              <span key={a.id}>
                {i > 0 && ", "}
                <button className="link" onClick={() => open(a)}>
                  {a.city}
                </button>{" "}
                <span className={`ispu ${a.level}`}>{s.ispu[a.level]}</span>
              </span>
            ))}
            {air.length > 6 && <span className="muted"> {s.andMore(air.length - 6)}</span>}
          </span>
        </p>
      )}
      {list.length === 0 && air.length === 0 ? <p className="note">{s.alertsNone(data.days)}</p> : items(list.slice(0, SHOWN))}
    </Card>
  );
}
