// "Cek lokasimu" panel: choose a point (GPS, map tap or regency search) and
// read what the forecast and the fire record say about it.
import { useEffect, useState } from "react";
import { tryJson } from "./api/fetch";
import { bearingDeg, compassIndex, distanceKm } from "./geo";
import { fmtDay, fmtInt, fmtNum, wibDate } from "./format";
import type { Lang, Strings } from "./i18n";
import { MethodLink } from "./Methodology";
import { RISK_COLORS } from "./palette";
import { AIR_HOURS, NEAR_KM, type NearFire, type PlaceReport } from "./placeReport";

interface Label {
  name: string;
  lon: number;
  lat: number;
}

/** Name of the regency/city whose label point is nearest (within 80 km). */
function nearestRegency(labels: Label[], lon: number, lat: number): string | null {
  let best: { name: string; km: number } | null = null;
  for (const l of labels) {
    const km = distanceKm(lon, lat, l.lon, l.lat);
    if (!best || km < best.km) best = { name: l.name, km };
  }
  return best && best.km <= 80 ? best.name : null;
}

type LabelFile = { features: { properties: { name: string; level: string }; geometry: { coordinates: [number, number] } }[] };

/** Regency/city names with a point each, for the search box (loaded on first open). */
function useRegencies(): Label[] {
  const [labels, setLabels] = useState<Label[]>([]);
  useEffect(() => {
    tryJson<LabelFile>("boundaries/labels.geojson").then((f) =>
      setLabels(
        (f?.features ?? [])
          .filter((x) => x.properties.level === "kabupaten")
          .map((x) => ({ name: x.properties.name, lon: x.geometry.coordinates[0], lat: x.geometry.coordinates[1] }))
          .sort((a, b) => a.name.localeCompare(b.name)),
      ),
    );
  }, []);
  return labels;
}

interface Props {
  report: PlaceReport | null;
  label: string | null;
  picking: boolean;
  historyYears: [number, number] | null;
  lang: Lang;
  s: Strings;
  onPlace: (lon: number, lat: number, label: string | null) => void;
  onPick: () => void;
  onOpenFire: (id: string) => void;
  onClose: () => void;
}

export function PlacePanel({ report, label, picking, historyYears, lang, s, onPlace, onPick, onOpenFire, onClose }: Props) {
  const regencies = useRegencies();
  const [query, setQuery] = useState("");
  const [gpsError, setGpsError] = useState(false);
  const matches = query.trim().length >= 2 ? regencies.filter((r) => r.name.toLowerCase().includes(query.trim().toLowerCase())).slice(0, 6) : [];

  const gps = () => {
    setGpsError(false);
    navigator.geolocation?.getCurrentPosition(
      (p) => onPlace(p.coords.longitude, p.coords.latitude, null),
      () => setGpsError(true),
      { enableHighAccuracy: false, timeout: 15_000, maximumAge: 600_000 },
    );
  };
  // Already allowed before: locate at once instead of asking for a second tap.
  useEffect(() => {
    if (report) return;
    navigator.permissions
      ?.query({ name: "geolocation" })
      .then((st) => st.state === "granted" && gps())
      .catch(() => {});
    // Once, when the panel opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // A point without a name is called after the nearest regency or city.
  const near = report && !label ? nearestRegency(regencies, report.lon, report.lat) : null;

  return (
    <aside className="panel place-panel" aria-label={s.placeTitle}>
      <header className="panel-head">
        <div>
          <h1>
            {s.placeTitle} <MethodLink id="place" s={s} />
          </h1>
          <p className="muted">{s.placeLead}</p>
        </div>
        <button className="close" onClick={onClose} aria-label={s.close}>
          ×
        </button>
      </header>

      <div className="place-inputs">
        <div className="seg-row wrap">
          <button className="seg" onClick={gps}>
            {s.placeGps}
          </button>
          <button className={picking ? "seg on" : "seg"} onClick={onPick}>
            {s.placePick}
          </button>
        </div>
        <input type="search" placeholder={s.placeSearch} value={query} onChange={(e) => setQuery(e.target.value)} aria-label={s.placeSearch} />
        {matches.length > 0 && (
          <ul className="place-matches">
            {matches.map((m) => (
              <li key={m.name}>
                <button
                  onClick={() => {
                    setQuery("");
                    onPlace(m.lon, m.lat, m.name);
                  }}
                >
                  {m.name}
                </button>
              </li>
            ))}
          </ul>
        )}
        {picking && <p className="muted">{s.placePicking}</p>}
        {gpsError && <p className="callout warn">{s.placeGpsError}</p>}
      </div>

      {report && (
        <PlaceReportView report={report} label={label ?? (near ? s.placeNear(near) : null)} historyYears={historyYears} lang={lang} s={s} onOpenFire={onOpenFire} />
      )}
    </aside>
  );
}

function PlaceReportView({
  report: r,
  label,
  historyYears,
  lang,
  s,
  onOpenFire,
}: {
  report: PlaceReport;
  label: string | null;
  historyYears: [number, number] | null;
  lang: Lang;
  s: Strings;
  onOpenFire: (id: string) => void;
}) {
  const dir = (bearing: number) => s.compass[compassIndex(bearing)];
  const km = (v: number) => fmtNum(v, lang, v < 10 ? 1 : 0);
  const upwind = r.fires.filter((f) => f.upwind);
  // Where the air comes from: the path's far end, as seen from here.
  const from = r.airPath.length > 3 ? r.airPath[r.airPath.length - 1] : null;
  const lat = `${Math.abs(r.lat).toFixed(3)}°${r.lat < 0 ? (lang === "id" ? "LS" : "S") : lang === "id" ? "LU" : "N"}`;
  const lon = `${r.lon.toFixed(3)}°${lang === "id" ? "BT" : "E"}`;
  const today = wibDate(new Date().toISOString());
  const tomorrow = wibDate(new Date(Date.now() + 86_400_000).toISOString());
  const dayName = (date: string) => (date === today ? s.today : date === tomorrow ? s.tomorrow : fmtDay(date, lang));
  const first = r.air[0];
  // Fires are named after the nearest town, so several can share a name:
  // one row per name, at the nearest one.
  const byName = new Map<string, NearFire & { count: number }>();
  for (const f of r.fires) {
    const g = byName.get(f.fire.name);
    if (g) g.count++;
    else byName.set(f.fire.name, { ...f, count: 1 });
  }
  const groups = [...byName.values()];
  const nearest = r.fires.length ? r.fires.reduce((a, b) => (b.km < a.km ? b : a)) : null;

  return (
    <div className="place-report">
      <h2>{label ?? s.placeHere(lat, lon)}</h2>

      <section>
        <h3 className="sub">
          {s.placeAir} <MethodLink id="haze" s={s} />
        </h3>
        {first ? (
          <>
            <p className="place-answer">
              {dayName(first.date)}: <span className={`ispu big ${first.ispu}`}>{s.ispu[first.ispu]}</span>
            </p>
            {first.ispu !== "baik" && (
              <ul className="place-advice">
                <li>
                  <b>{s.healthSchool}</b> {s.healthSchoolRule[first.ispu]}
                </li>
                <li>
                  <b>{s.healthPublic}</b> {s.healthPublicRule[first.ispu]}
                </li>
              </ul>
            )}
            <table className="table place-air">
              <tbody>
                {r.air.map((d) => (
                  <tr key={d.date}>
                    <td>{dayName(d.date)}</td>
                    <td>
                      <span className={`ispu ${d.ispu}`}>{s.ispu[d.ispu]}</span>
                    </td>
                    <td className="num muted">{s.pmValue(fmtInt(d.pm25, lang))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : (
          <p className="muted">{s.placeNoAir}</p>
        )}
      </section>

      <section>
        <h3 className="sub">{s.placeFiresTitle}</h3>
        {nearest ? (
          <>
            <p className="place-answer">{s.placeNearest(km(nearest.km), dir(nearest.bearing))}</p>
            <p className="muted small">{s.placeFiresCount(r.fires.length, NEAR_KM)}</p>
            <ul className="place-fires">
              {groups.slice(0, 5).map((g) => (
                <li key={g.fire.id}>
                  <button className="linkish" onClick={() => onOpenFire(g.fire.id)}>
                    {g.fire.name}
                  </button>
                  <span className="muted">
                    {" "}
                    · {s.placeFireAt(km(g.km), dir(g.bearing))}
                    {g.count > 1 && ` · ${s.placeMore(g.count - 1)}`}
                    {g.upwind && <b className="upwind"> · {s.placeUpwind}</b>}
                  </span>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="place-answer">{s.placeNoFires(NEAR_KM)}</p>
        )}
        {from && (
          <p className="place-line">
            {s.placeAirFrom(dir(bearingDeg(r.lon, r.lat, from.lon, from.lat)), AIR_HOURS)}
            {upwind.length ? s.placeAirFires(upwind.length) : s.placeAirClean}
            {s.placeAirMap}
          </p>
        )}
      </section>

      {r.danger && (
        <p className="place-line">
          <span className="swatch" style={{ background: RISK_COLORS[r.danger.cls] }} /> {s.placeDanger(s.riskClasses[r.danger.cls])}{" "}
          <MethodLink id="danger" s={s} />
        </p>
      )}
      {r.burnYears !== null && historyYears && (
        <p className="place-line">
          {s.placeBurn(r.burnYears, historyYears[0], historyYears[1])} <MethodLink id="repeat" s={s} />
        </p>
      )}
      <p className="note">{s.placeNote}</p>
    </div>
  );
}
