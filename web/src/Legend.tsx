// Map legend: one row per visible layer that needs a key.
import type { LayerToggles } from "./MapView";
import { MethodLink } from "./Methodology";
import { fmtDate, fmtDay } from "./format";
import type { Lang, Strings } from "./i18n";
import { HISTORY_COLORS, RISK_COLORS, STATUS_RGB, css } from "./palette";

export function Legend({
  open,
  layers,
  is3d,
  live,
  hasSpread,
  burnYears,
  aodDate,
  himawariTime,
  airPath,
  smokePath,
  lang,
  s,
}: {
  /** phones: shown only after the Legenda button */
  open: boolean;
  layers: LayerToggles;
  is3d: boolean;
  /** live mode (not season history) */
  live: boolean;
  /** the opened fire has a spread forecast */
  hasSpread: boolean;
  /** years of the repeat-burn layer, when loaded */
  burnYears: [number, number] | null;
  /** day of the satellite haze layer, when shown */
  aodDate: string | null;
  himawariTime: string | null;
  /** a checked place's incoming-air path is on the map */
  airPath: boolean;
  /** the opened fire's smoke path is on the map */
  smokePath: boolean;
  lang: Lang;
  s: Strings;
}) {
  return (
    <div className={open ? "legend open" : "legend"} aria-label="legend">
      <div>
        <span className="swatch flame" />
        {s.legendFlame}
      </div>
      <div>
        <span className="swatch" style={{ background: css(STATUS_RGB.cooling) }} />
        {s.status.cooling}
      </div>
      {layers.stations && live && (
        <div>
          <span className="swatch station" />
          {s.legendStations}
        </div>
      )}
      {layers.smog && (
        <div>
          <span className="swatch smog" />
          {s.legendSmog} <MethodLink id="haze" s={s} />
        </div>
      )}
      {layers.himawari && himawariTime && (
        <div>
          <span className="swatch himawari" />
          {s.legendHimawari(fmtDate(himawariTime, lang))} <MethodLink id="haze" s={s} />
        </div>
      )}
      {layers.aod && aodDate && (
        <div>
          <span className="swatch aod" />
          {s.legendAod(fmtDay(aodDate, lang))} <MethodLink id="haze" s={s} />
        </div>
      )}
      {airPath && (
        <div>
          <span className="swatch path air" />
          {s.legendAirPath}
        </div>
      )}
      {smokePath && (
        <div>
          <span className="swatch path smoke" />
          {s.legendSmokePath}
        </div>
      )}
      {layers.early && live && (
        <div>
          <span className="swatch early" />
          {s.legendEarly}
        </div>
      )}
      {layers.spread && hasSpread && (
        <div>
          <span className="swatch spread" />
          {s.legendSpread}
        </div>
      )}
      {layers.risk && live && (
        <div className="risk-legend">
          {s.riskClasses.map((c, i) => (
            <span key={c}>
              <span className="swatch" style={{ background: RISK_COLORS[i] }} />
              {c}
            </span>
          ))}
        </div>
      )}
      {layers.burnHistory && burnYears && (
        <div className="risk-legend">
          <span className="muted">{s.historyLegend(burnYears)}</span>
          {HISTORY_COLORS.map((c, i) => (
            <span key={c}>
              <span className="swatch" style={{ background: c }} />
              {i === 3 ? "≥4" : i + 1}
            </span>
          ))}
        </div>
      )}
      {layers.flames && is3d && live && <div className="legend-note">{s.illustration}</div>}
      <div className="legend-source">
        {s.legendSource} <MethodLink id="hotspots" s={s} />
      </div>
    </div>
  );
}
