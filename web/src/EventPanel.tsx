import type { Playback } from "./hooks/usePlayback";
import { PlaybackSlider } from "./PlaybackSlider";
import { MethodLink } from "./Methodology";
import { isLocated, type EventPage, type LandInfo, type Progression, type ProgressionEvent } from "./api/events";
import type { SpreadForecast } from "./api/fire";
import { BarChart, LineChart } from "./charts";
import { Card } from "./Card";
import type { Focus } from "./MapView";
import { compassIndex } from "./geo";
import type { SmokeOutlook } from "./trajectory";
import { fmtDate, fmtDay, fmtHa, fmtInt, fmtNum, fmtPct, wibDate } from "./format";
import type { Lang, Strings } from "./i18n";
import { useEffect, useState } from "react";
import { landmarkName, loadPlaces, nearestLandmark } from "./PlaceSearch";

/** Share of quiet fires seen again on the same ~1.6 km cells within 7 days,
 * Jul-Sep 2026 (pipeline/scripts/backtest_fire_status.py): cooling = quiet 24 h,
 * out = quiet 72 h. */
const QUIET_BACK_7D = {
  cooling: { peat: 0.43, other: 0.33 },
  out: { peat: 0.39, other: 0.31 },
} as const;

// Single-series magnitude charts: one hue (categorical slot 2, dark step).
const AREA = "#d95926";
const FRP = "#d95926";

interface Props {
  event: EventPage;
  progression?: Progression | null;
  lang: Lang;
  s: Strings;
  /** the day timeline */
  timeline: Playback;
  spread: SpreadForecast | null;
  spreadDay: number;
  setSpreadDay: (d: number) => void;
  onClose: () => void;
  onLook: (f: Focus) => void;
  smoke: SmokeOutlook | null;
}


export function EventPanel({
  event,
  progression,
  lang,
  s,
  timeline,
  spread,
  spreadDay,
  setSpreadDay,
  onClose,
  onLook,
  smoke,
}: Props) {
  const n = event.days.length;
  const day = event.days[timeline.index];
  const areaSeries = [
    {
      key: "area",
      label: s.growth,
      color: AREA,
      emphasis: true,
      points: event.days.map((d, i) => [i, d.area_ha] as [number, number]),
    },
  ];

  return (
    <aside className="panel" aria-label={event.name}>
      <header className="panel-head">
        <div>
          <div className={`badge ${event.status}`}>
            <span className={`status-dot ${event.status}`} />
            {s.status[event.status]}
          </div>
          <h1>{event.name}</h1>
          <div className="muted">
            {event.kabupaten} · {event.provinsi}
          </div>
          <Landmark lon={event.centroid[0]} lat={event.centroid[1]} lang={lang} s={s} />
        </div>
        <button className="close" onClick={onClose} aria-label={s.close}>
          ×
        </button>
      </header>

      <div className="stats">
        <div>
          <div className="kpi-label">{s.area}</div>
          <div className="kpi-value">≈{fmtHa(event.est_area_ha, lang)}</div>
          <div className="kpi-sub">
            {fmtInt(Math.round(event.est_area_ha / 14.0625), lang)} {s.pixels}
          </div>
        </div>
        <div>
          <div className="kpi-label">{s.peakFrp}</div>
          <div className="kpi-value">
            {fmtInt(event.peak_frp, lang)} <small>MW</small>
          </div>
        </div>
        <div>
          <div className="kpi-label">{s.hotspots}</div>
          <div className="kpi-value">{fmtInt(event.hotspot_count, lang)}</div>
        </div>
      </div>

      <dl className="facts">
        <dt>{s.firstSeen}</dt>
        <dd>{fmtDate(event.first_seen, lang)} WIB</dd>
        <dt>{s.lastSeen}</dt>
        <dd>{fmtDate(event.last_seen, lang)} WIB</dd>
        {event.nearest_town && (
          <>
            <dt>{s.nearest}</dt>
            <dd>
              {event.nearest_town} ({fmtNum(event.nearest_town_km, lang, 1)} {s.km})
            </dd>
          </>
        )}
      </dl>

      {smoke && (
        <p className="smoke-heading">
          <span className="smoke-swatch" aria-hidden />
          {s.smokeHeading(s.compass[compassIndex(smoke.bearing)], smoke.town?.name ?? null, smoke.town?.hours ?? null)}{" "}
          <MethodLink id="haze" s={s} />
        </p>
      )}
      {event.status !== "active" && (
        <div className="callout">
          {s.quietNote(fmtPct(QUIET_BACK_7D[event.status][event.on_peat ? "peat" : "other"]), !!event.on_peat, event.status === "out")}{" "}
          <MethodLink id="events" s={s} />
        </div>
      )}
      {event.on_peat && (
        <div className="callout peat">
          <b>{s.peat}</b> {s.peatNote}
        </div>
      )}
      {event.near_static && <div className="callout warn">{s.nearStatic}</div>}
      {event.tier === "single" && <div className="callout warn">{s.singleEvidence}</div>}
      {event.history && event.history.cells >= 5 && (
        <div className="callout history">
          {event.history.share_before >= 0.05
            ? s.historyEvent(
                fmtPct(event.history.share_before),
                event.history.years
                  .slice()
                  .sort((x, y) => y.share - x.share)
                  .slice(0, 4)
                  .sort((x, y) => x.year - y.year)
                  .map((y) => y.year)
                  .join(", ") || "2012–2025",
              )
            : s.historyEventNone(2012)}
        </div>
      )}

      {SHOW_LAND && event.land && <LandSection land={event.land} lang={lang} s={s} />}

      {progression && <ProgressionSection p={progression} lang={lang} s={s} onLook={onLook} />}

      <Card
        title={s.growth}
        method="area"
        s={s}
        more={
          <>
            <h3 className="sub">
              {s.intensity} <MethodLink id="hotspots" s={s} />
            </h3>
            <BarChart
              values={event.days.map((d) => ({ label: fmtDay(d.date, lang), value: d.frp_sum }))}
              color={FRP}
              highlight={timeline.index}
              yFormat={(y) => fmtInt(y, lang)}
              ariaLabel={s.intensity}
              onSelect={timeline.setIndex}
            />
            <p className="note">{s.estimateNote}</p>
          </>
        }
      >
        <LineChart
          series={areaSeries}
          height={120}
          xFormat={(i) => fmtDay(event.days[Math.round(i)]?.date ?? event.days[0].date, lang)}
          yFormat={(y) => fmtHa(y, lang)}
          ariaLabel={s.growth}
        />
        <PlaybackSlider p={timeline} min={0} max={n - 1} label={s.day} className="timeline" wordy s={s}>
          <span className="timeline-day">
            {s.day} {timeline.index + 1}/{n} · {fmtDay(day.date, lang)} · {fmtHa(day.area_ha, lang)}
          </span>
        </PlaybackSlider>
      </Card>

      <Card
        title={s.spreadTitle}
        method="spread"
        className="spread"
        s={s}
        folded
        lead={spread && s.spreadLead(fmtHa(spread.days[0].new_area_ha, lang))}
      >
        {spread ? (
          <>
            <div className="seg-row">
              {spread.days.map((d, i) => (
                <button key={d.day} className={i === spreadDay ? "seg on" : "seg"} onClick={() => setSpreadDay(i)}>
                  {s.spreadDay(d.day)}
                </button>
              ))}
            </div>
            <div className="spread-stats">
              <div>
                <div className="kpi-label">{s.spreadNewArea}</div>
                <div className="kpi-value">≈{fmtHa(spread.days[spreadDay].new_area_ha, lang)}</div>
              </div>
              {(() => {
                const w = spread.weather[Math.min(spreadDay * 4, spread.weather.length - 1)];
                const dir = s.compassAbbr[compassIndex(w.to_deg)];
                const rain = spread.weather.slice(spreadDay * 4, spreadDay * 4 + 4).reduce((a, b) => a + b.rain_mm, 0);
                return (
                  <div>
                    <div className="kpi-label">
                      {s.wind} · {s.rain}
                    </div>
                    <div className="kpi-value small">
                      → {dir} {fmtNum(w.speed, lang, 1)} m/s · {rain.toFixed(0)} mm
                    </div>
                  </div>
                );
              })()}
            </div>
            <p className="note">{s.spreadNote}</p>
          </>
        ) : (
          <p className="note">{s.spreadNone}</p>
        )}
      </Card>
      {/* For citing or linking; not something a reader needs up top. */}
      <p className="note mono">ID: {event.id}</p>
    </aside>
  );
}

// Permit holders stay hidden until legal review (defamation risk); the
// pipeline also withholds them unless HAZE_PUBLISH_LAND=1.
const SHOW_LAND = false;

// PBPH activity codes (KEGIATAN) in plain words.
const ACTIVITY: Record<string, "actTimber" | "actServices" | "actNonTimber" | "actArea"> = {
  PHHK: "actTimber",
  PJL: "actServices",
  PHHBK: "actNonTimber",
  PUHHBK: "actNonTimber",
  PHHKBK: "actNonTimber",
  PPK: "actArea",
};

function activities(code: string | null, s: Strings): string {
  if (!code) return "";
  const names = new Set(
    code
      .split(",")
      .map((c) => ACTIVITY[c.trim().split("_")[0]])
      .filter(Boolean)
      .map((k) => s[k]),
  );
  return [...names].join(", ");
}

function LandSection({ land, lang, s }: { land: LandInfo; lang: Lang; s: Strings }) {
  return (
    <section>
      <h2>{s.landTitle}</h2>
      {land.concessions.length ? (
        <table className="table">
          <tbody>
            {land.concessions.map((c) => (
              <tr key={c.name}>
                <td>
                  {c.name}
                  <div className="muted small">
                    {[c.type, activities(c.activity, s), c.sk ? `SK ${c.sk}` : null].filter(Boolean).join(" · ")}
                  </div>
                </td>
                <td className="num">{fmtPct(c.share)}</td>
              </tr>
            ))}
            {land.outside_share != null && land.outside_share > 0 && (
              <tr>
                <td className="muted">{s.landOutside}</td>
                <td className="num">{fmtPct(land.outside_share)}</td>
              </tr>
            )}
          </tbody>
        </table>
      ) : (
        <p>{s.landNone}</p>
      )}
      <p className="note">
        {s.landNote(land.sampled_cells)} {s.landSource}: {land.source}, {s.landChecked} {fmtDay(land.checked, lang)}.
      </p>
    </section>
  );
}

const EVENT_ICON: Record<string, string> = { ignition: "●", rapid_growth: "▲", jump: "↗", stall: "■" };

function ProgressionSection({ p, lang, s, onLook }: { p: Progression; lang: Lang; s: Strings; onLook: (f: Focus) => void }) {
  const ig = p.ignition;
  const ros = p.ros.filter((r) => r.adv_p90_km !== undefined);
  const profile = p.profile;
  const events = p.events.filter((e) => e.type !== "ignition");
  const eventList = (es: ProgressionEvent[]) => (
    <ul className="key-events">
      {es.map((e, i) => (
        <li key={i}>
          {/* A jump's arrow points where the fire went (the glyph points north-east). */}
          <span
            className={`ke ${e.type}`}
            style={e.type === "jump" && e.bearing !== undefined ? { transform: `rotate(${e.bearing - 45}deg)` } : undefined}
            aria-hidden
          >
            {EVENT_ICON[e.type]}
          </span>
          <span>
            {isLocated(e) ? (
              <button className="linkish" onClick={() => onLook({ lon: e.lon, lat: e.lat })}>
                {e.type === "jump" && e.bearing !== undefined
                  ? s.progJumpDir(fmtNum(e.value, lang, 1), s.compass[compassIndex(e.bearing)])
                  : s.progEvent[e.type](e.value)}
              </button>
            ) : (
              s.progEvent[e.type](e.value)
            )}{" "}
            <span className="muted small">{fmtDay(wibDate(e.t), lang)}</span>
          </span>
        </li>
      ))}
    </ul>
  );
  return (
    <Card
      title={s.progTitle}
      method="progression"
      s={s}
      more={
        <>
          {events.length > 4 && eventList(events.slice(4))}
          {ros.length > 1 && (
            <>
              <h3 className="sub">{s.progRos}</h3>
              <BarChart
                values={ros.map((r) => ({ label: fmtDay(wibDate(r.t), lang), value: r.adv_p90_km ?? 0 }))}
                color={AREA}
                height={100}
                yFormat={(y) => `${fmtNum(y, lang, 1)} km`}
                ariaLabel={s.progRos}
              />
            </>
          )}
          {profile && profile.relief_m >= 20 && (
            <>
              <h3 className="sub">{s.progProfile(profile.relief_m)}</h3>
              <LineChart
                series={[
                  {
                    key: "elev",
                    label: s.progElevation,
                    color: "#8a9a5b",
                    emphasis: true,
                    points: profile.d_km.map((d, i) => [d, profile.elev_m[i]] as [number, number]),
                  },
                ]}
                height={100}
                xFormat={(x) => `${x.toFixed(0)} km`}
                yFormat={(y) => `${Math.round(y)} m`}
                ariaLabel={s.progElevation}
              />
            </>
          )}
          <p className="note">{s.progNote(Math.round(p.method.cv_within_12h * 100), Math.round(p.method.cv_within_24h * 100))}</p>
        </>
      }
    >
      <p className="small">
        <button className="linkish" onClick={() => onLook({ lon: ig.lon, lat: ig.lat })}>
          {s.progIgnitionAt(fmtDate(ig.t, lang), Math.round(ig.uncertainty_h))}
        </button>
        {ig.started_earlier && <span className="muted"> {s.progStartedEarlier}</span>}
      </p>
      {eventList(events.slice(0, 4))}
    </Card>
  );
}

/** "Dekat Gunung X (±3 km)" under the fire's name, from the place index.
 *  ponytail: loads places.json (~1.5 MB gz) on the first fire opened; write the landmark
 *  into the event pages in the pipeline if that becomes a cost. */
function Landmark({ lon, lat, lang, s }: { lon: number; lat: number; lang: Lang; s: Strings }) {
  const [text, setText] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    setText(null);
    loadPlaces().then((pl) => {
      const lm = pl && nearestLandmark(pl, lon, lat);
      if (live && lm) setText(s.nearFeature(landmarkName(lm.name, lm.type, s), fmtNum(lm.km, lang, lm.km < 10 ? 1 : 0)));
    });
    return () => {
      live = false;
    };
  }, [lon, lat, lang, s]);
  return text ? <div className="muted">{text}</div> : null;
}
