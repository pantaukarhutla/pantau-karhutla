import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { dangerDayAt } from "./api/fire";
import { Dashboard, FireStats, Sources } from "./Dashboard";
import { EventPanel } from "./EventPanel";
import { MapView, type Focus, type LayerToggles } from "./MapView";
import { Cities, ForecastBar, LayerPanel, AlertsCard, HealthCard, OutlookCard, RepeatBurnCard, RiskPanel, StationsList, TransboundaryPanel } from "./Controls";
import { strings, type Lang, type Strings } from "./i18n";
import { CompareCard } from "./Compare";
import { Legend } from "./Legend";
import { MethodologyPanel, MethodProvider } from "./Methodology";
import { PlacePanel } from "./Place";
import { PlaceSearch } from "./PlaceSearch";
import { AIR_HOURS, assessPlace } from "./placeReport";
import { ErrorBoundary } from "./ErrorBoundary";
import { REPO_URL } from "./links";
import { SMOKE_TICKS } from "./trajectory";
import type { MethodId } from "./methodText";
import { HistoryBar, HistoryPanel } from "./History";
import { browserLang, parseLang, useLang } from "./hooks/useLang";
import { useForecastTimeline } from "./hooks/useForecastTimeline";
import { useHistoryMode } from "./hooks/useHistoryMode";
import { usePersistentState } from "./hooks/usePersistentState";
import { usePlace } from "./hooks/usePlace";
import { useSelectedEvent, useSmokeOutlook } from "./hooks/useSelectedEvent";
import { loadPlumes } from "./api/air";
import { useAodDate } from "./hooks/useAodDate";
import { useHimawariTime } from "./hooks/useHimawariTime";
import { useAfterFirstPaint, useBurnGrid, useOnDemand, useStaticData, type StaticData } from "./hooks/useStaticData";
import { indonesiaView, isPhone } from "./viewport";
// Tables load on first use: most visitors only see the map.
const DataView = lazy(() => import("./DataView").then((m) => ({ default: m.DataView })));

interface View {
  center: [number, number];
  zoom: number;
}

// Shareable state lives in the hash: #/event/<id>?lang=en.
// #/@<lon>,<lat>,<zoom> opens the map at a place (links in the alert feeds).
function readHash(): { eventId: string | null; lang: Lang | null; view: View | null } {
  const [path, query] = window.location.hash.replace(/^#/, "").split("?");
  const m = path.match(/^\/event\/([\w-]+)/);
  const at = path.match(/^\/@(-?[\d.]+),(-?[\d.]+),([\d.]+)/);
  const lang = parseLang(new URLSearchParams(query).get("lang"));
  const view: View | null = at ? { center: [Number(at[1]), Number(at[2])], zoom: Number(at[3]) } : null;
  return { eventId: m ? m[1] : null, lang, view };
}

const INITIAL_VIEW: View = indonesiaView();
const MAX_MAP_REBUILDS = 3; // per minute

const LAYERS_KEY = "haze.layers.v3"; // v2: spread forecast off by default; v3: boundaries on
const DEFAULT_LAYERS: LayerToggles = {
  satellite: true,
  flames: true,
  glow: true,
  stations: true,
  risk: false,
  burnHistory: false,
  boundaries: true,
  peat: false,
  columns: false,
  smog: true,
  aod: false, // observed haze: opt in
  himawari: false, // live satellite image: opt in
  plumes: true,
  wind: true,
  spread: false, // experimental: opt in
};
/** Saved choices over the defaults, so layers added later start at their default. */
const parseLayers = (stored: string): LayerToggles => ({ ...DEFAULT_LAYERS, ...JSON.parse(stored) });

// Live-only layers (forecasts, stations, wind) make no sense on a past day.
const PAST_DAY_OFF = { plumes: false, wind: false, stations: false, spread: false, columns: false } satisfies Partial<LayerToggles>;

export default function App() {
  const [initial] = useState(readHash);
  const [lang, setLang] = useLang(initial.lang);
  const s = strings(lang);
  const [eventId, setEventId] = useState<string | null>(initial.eventId);
  // Low-end phones start in 2D (PRD); everyone can toggle.
  const [is3d, setIs3d] = useState(!isPhone());
  const [layers, setLayers] = usePersistentState(LAYERS_KEY, DEFAULT_LAYERS, parseLayers);
  const [mode, setMode] = useState<"live" | "history">("live");
  const [view, setView] = useState<"map" | "data">("map");
  const [method, setMethod] = useState<MethodId | null>(null);
  // A lost WebGL context (common after a tab sits hidden) breaks the map for
  // good; mount a new one at the same view once the tab is visible again.
  // Rate-limited so a failing GPU can't loop.
  const [rebuilt, setRebuilt] = useState<{ n: number; view: View | null }>({ n: 0, view: null });
  const rebuilds = useRef<number[]>([]);
  const onContextLost = useCallback((view: View) => {
    const rebuild = () => {
      const now = Date.now();
      rebuilds.current = rebuilds.current.filter((t) => now - t < 60_000);
      if (rebuilds.current.length >= MAX_MAP_REBUILDS) return;
      rebuilds.current.push(now);
      setRebuilt((r) => ({ n: r.n + 1, view }));
    };
    if (!document.hidden) return rebuild();
    const shown = () => {
      if (document.hidden) return;
      document.removeEventListener("visibilitychange", shown);
      rebuild();
    };
    document.addEventListener("visibilitychange", shown);
  }, []);
  // Where panels ask the map to look; a new object each time, so asking for
  // the same place twice flies there again.
  const [focus, setFocus] = useState<Focus | null>(null);
  // Phones: the dashboard is a bottom sheet at three heights. It starts as a
  // peek (just the fire count) so the map shows; opening a fire or looking at
  // a place folds it back, so you see what you asked for.
  const [sheet, setSheet] = useState<Sheet>("peek");
  const [menuOpen, setMenuOpen] = useState(false);
  const [legendOpen, setLegendOpen] = useState(false);
  const lookAt = useCallback((f: Focus) => {
    setFocus({ ...f });
    setSheet("peek");
  }, []);
  const selectFire = useCallback((id: string | null) => {
    setEventId(id);
    if (id) setSheet("peek");
  }, []);

  const data = useStaticData();
  const place = usePlace(lookAt);
  const burnGrid = useBurnGrid(data.fireHistory, layers.burnHistory || place.place !== null);
  const history = useHistoryMode(mode === "history");
  const aodDate = useAodDate(layers.aod, history?.day?.date);
  const himawariTime = useHimawariTime(layers.himawari && !history);
  // Fire-smoke plumes: after the first screen, and only with their layer on.
  const painted = useAfterFirstPaint();
  const plumes = useOnDemand(loadPlumes, layers.plumes && painted);
  const forecast = useForecastTimeline(data.smog, plumes, data.wind, !history);
  const sel = useSelectedEvent(eventId, data.dash, data.events);
  const selected = sel.event;
  const smoke = useSmokeOutlook(selected, data.wind, data.cities, !history);

  // Danger day = the WIB date of the forecast slider (tomorrow if none).
  const dangerDay = useMemo(() => dangerDayAt(data.danger, forecast.time), [data.danger, forecast.time]);
  const mapLayers = useMemo(() => (history ? { ...layers, ...PAST_DAY_OFF } : layers), [history, layers]);
  const progLabels = useMemo(() => ({ ignition: s.progIgnition, jump: s.progJump, compass: s.compassShort }), [s]);
  const smokePath = useMemo(
    () => {
      if (!smoke) return null;
      // Hour marks along the path; the farthest one says what the line is.
      const hours = SMOKE_TICKS.filter((h) => h < smoke.path.length);
      const last = hours[hours.length - 1];
      return { path: smoke.path, ticks: hours.map((h) => ({ hours: h, label: h === last ? s.smokeHere(h) : s.hoursAhead(h) })) };
    },
    [smoke, s],
  );
  const { smog, wind, danger, events } = data;
  const placeReport = useMemo(
    () => place.place && assessPlace(place.place.lon, place.place.lat, { smog, wind, danger, burnGrid, events, now: Date.now() }),
    [place.place, smog, wind, danger, burnGrid, events],
  );
  // The checked place's incoming air on the map: path[k] is where the air
  // arriving here in AIR_HOURS is AIR_HOURS - k hours from now, so the far
  // end is where it is now.
  const placeOnMap = useMemo(() => {
    if (!place.open || !placeReport) return null;
    const last = placeReport.airPath.length - 1;
    const at = (k: number) => AIR_HOURS - k;
    const ticks = last > 0 ? [{ hours: last, label: at(last) <= 0 ? s.airNowHere : s.hoursAhead(at(last)) }] : [];
    if (last > 12) ticks.push({ hours: 12, label: s.hoursAhead(at(12)) });
    return { ...placeReport, ticks };
  }, [place.open, placeReport, s]);

  useEffect(() => {
    // Only spell out the language in links when it differs from the browser's.
    const q = lang !== browserLang() ? `?lang=${lang}` : "";
    const h = eventId ? `#/event/${eventId}${q}` : q ? `#/${q}` : "";
    if (window.location.hash !== h) window.history.replaceState(null, "", h || window.location.pathname);
    document.documentElement.lang = lang;
  }, [eventId, lang]);

  const openOnMap = () => {
    setMode("live");
    setView("map");
  };

  return (
    <MethodProvider value={setMethod}>
    <div className={selected || place.open ? "app has-panel" : "app"}>
      <MapView
        key={rebuilt.n}
        danger={history ? null : data.danger}
        dangerDay={dangerDay}
        burnHistory={burnGrid}
        stations={data.stations?.stations ?? []}
        events={history ? [] : data.events}
        hotspots={history ? history.fires : data.hotspots}
        historyMode={history !== null}
        progression={selected ? sel.progression : null}
        lang={lang}
        labels={progLabels}
        satelliteDate={history?.day?.date}
        aodDate={aodDate}
        himawariTime={himawariTime}
        lightTime={
          history?.day
            ? Date.parse(`${history.day.date}T13:30:00+07:00`) // matches the afternoon satellite photo
            : forecast.time
        }
        selected={selected}
        spread={sel.spread}
        spreadDay={sel.spreadDay}
        dayIndex={sel.timeline.index}
        is3d={is3d}
        layers={mapLayers}
        smog={history ? history.smog : data.smog}
        plumes={plumes}
        wind={forecast.wind}
        smogFrame={history ? 0 : forecast.playback.index}
        plumeFrame={forecast.plumeFrame}
        focus={focus}
        smokePath={smokePath}
        place={placeOnMap}
        picking={place.open && place.picking}
        onPickPoint={(lon, lat) => place.choose(lon, lat, null)}
        onSelect={selectFire}
        initialView={initial.view ?? INITIAL_VIEW}
        startView={rebuilt.view ?? undefined}
        animate={!method}
        onContextLost={onContextLost}
      />

      <header className={menuOpen ? "topbar menu-open" : "topbar"}>
        <div className="brand">
          <span className="logo" aria-hidden>
            ●
          </span>
          <div>
            <div className="brand-title">{s.title}</div>
            <div className="brand-sub">{s.subtitle}</div>
          </div>
        </div>
        <PlaceSearch
          className="top-search"
          s={s}
          onChoose={(lon, lat, label, zoom) => {
            setEventId(null);
            setMenuOpen(false);
            place.setOpen(true);
            place.choose(lon, lat, label, zoom);
          }}
          onGps={() => {
            setEventId(null);
            setMenuOpen(false);
            place.setOpen(true);
            place.locate();
          }}
        />
        <nav className="toggles main-toggles" aria-label={s.title}>
          <span className="seg-group">
            <button className={view === "map" ? "seg on" : "seg"} onClick={() => setView("map")}>
              {s.viewMap}
            </button>
            <button className={view === "data" ? "seg on" : "seg"} onClick={() => setView("data")}>
              {s.viewData}
            </button>
          </span>
          <span className="seg-group">
            <button className={mode === "live" ? "seg on" : "seg"} onClick={() => setMode("live")}>
              {s.modeLive}
            </button>
            <button
              className={mode === "history" ? "seg on" : "seg"}
              onClick={() => {
                setEventId(null);
                setMode("history");
              }}
            >
              {s.modeHistory}
            </button>
          </span>
          <span className="seg-group">
            <button
              className={place.open ? "seg place-btn on" : "seg place-btn"}
              onClick={() => {
                setEventId(null);
                place.setOpen(!place.open);
              }}
            >
              <span aria-hidden>◎</span> <span className="place-full">{s.placeTitle}</span>
                <span className="place-short">{s.placeShort}</span>
            </button>
          </span>
          <span className="seg-group">
            <button className={is3d ? "seg on" : "seg"} onClick={() => setIs3d(true)}>
              {s.view3d}
            </button>
            <button className={!is3d ? "seg on" : "seg"} onClick={() => setIs3d(false)}>
              {s.view2d}
            </button>
          </span>
        </nav>
        <div className="toggles util-toggles">
          <button className={menuOpen ? "seg menu-btn on" : "seg menu-btn"} onClick={() => setMenuOpen(!menuOpen)} aria-expanded={menuOpen} aria-label={s.menu}>
            <span aria-hidden>☰</span>
          </button>
          <button className="seg" onClick={() => setLang(lang === "id" ? "en" : "id")}>
            {lang === "id" ? "EN" : "ID"}
          </button>
          <button className="seg" onClick={() => setMethod("hotspots")} title={s.methodTitle}>
            <span className="method-short">{s.methodShort}</span>
            <span className="method-icon" aria-hidden>
              ⓘ
            </span>
          </button>
          <a className="seg gh-link" href={REPO_URL} target="_blank" rel="noopener" title={s.openSource} aria-label={s.openSource}>
            <svg className="gh-mark" viewBox="0 0 16 16" width="15" height="15" aria-hidden="true"><path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>
            <span className="gh-word">GitHub</span>
          </a>
        </div>
      </header>
      {method && (
        // A failing panel closes instead of taking the map down with it.
        <ErrorBoundary key={method} onError={() => setMethod(null)}>
          <MethodologyPanel at={method} lang={lang} s={s} onClose={() => setMethod(null)} onPick={setMethod} />
        </ErrorBoundary>
      )}

      {view === "data" && data.dash && (
        <Suspense fallback={<div className="data-view muted">{s.loading}</div>}>
        <DataView
          season={data.dash.season}
          lang={lang}
          s={s}
          onOpenFire={(id) => {
            openOnMap();
            selectFire(id);
          }}
          onOpenPlace={(lon, lat, label) => {
            openOnMap();
            setEventId(null);
            lookAt({ lon, lat, zoom: 11, label });
          }}
        />
        </Suspense>
      )}

      <div className={`sidebar sheet-${sheet}`}>
        {/* Phones: the sidebar is a bottom sheet; tap or drag this handle. */}
        <SheetHandle sheet={sheet} setSheet={setSheet} s={s} />
        {data.error && <div className="callout warn">{data.error}</div>}
        {history ? (
          <HistoryPanel h={history.summary} p={history.playback} lang={lang} s={s} />
        ) : (
          <LiveCards data={data} lang={lang} s={s} onSelect={selectFire} onLook={lookAt} showLayer={(k) => setLayers({ ...layers, [k]: true })} />
        )}
      </div>

      {place.open && (
        <PlacePanel
          report={placeReport}
          label={place.place?.label ?? null}
          picking={place.picking}
          historyYears={data.fireHistory?.history_years ?? null}
          lang={lang}
          s={s}
          onPlace={place.choose}
          onGps={place.locate}
          gpsError={place.gpsError}
          onPick={place.togglePicking}
          onOpenFire={(id) => {
            place.setOpen(false);
            selectFire(id);
          }}
          onClose={place.close}
        />
      )}
      {selected && !place.open && (
        <EventPanel
          smoke={smoke}
          event={selected}
          lang={lang}
          s={s}
          timeline={sel.timeline}
          spread={sel.spread}
          progression={sel.progression}
          spreadDay={sel.spreadDay}
          setSpreadDay={sel.setSpreadDay}
          onClose={() => setEventId(null)}
          onLook={lookAt}
        />
      )}

      <LayerPanel layers={layers} setLayers={setLayers} s={s} fold={!!eventId || place.open} />

      {history ? (
        <HistoryBar h={history.summary} p={history.playback} lang={lang} s={s} />
      ) : (
        <ForecastBar times={forecast.times} p={forecast.playback} nowIndex={forecast.nowIndex} lang={lang} s={s} />
      )}

      <button className={legendOpen ? "seg legend-btn on" : "seg legend-btn"} onClick={() => setLegendOpen(!legendOpen)} aria-expanded={legendOpen}>
        {s.legendShow}
      </button>
      <Legend
        open={legendOpen}
        layers={layers}
        is3d={is3d}
        live={mode === "live"}
        hasSpread={sel.spread !== null}
        burnYears={data.fireHistory?.history_years ?? null}
        aodDate={aodDate}
        himawariTime={himawariTime}
        airPath={!!placeOnMap && placeOnMap.airPath.length > 1}
        smokePath={!!smokePath}
        lang={lang}
        s={s}
      />
    </div>
    </MethodProvider>
  );
}

type Sheet = "peek" | "half" | "full";
const SHEETS: Sheet[] = ["peek", "half", "full"];

/** Bottom-sheet handle (phones): a tap steps peek → half → full → peek; a drag
 *  of more than 30 px moves one step up or down. */
function SheetHandle({ sheet, setSheet, s }: { sheet: Sheet; setSheet: (v: Sheet) => void; s: Strings }) {
  const startY = useRef<number | null>(null);
  const k = SHEETS.indexOf(sheet);
  const step = (d: number) => setSheet(SHEETS[Math.min(Math.max(k + d, 0), SHEETS.length - 1)]);
  return (
    <button
      className="sheet-handle"
      onClick={() => setSheet(SHEETS[(k + 1) % SHEETS.length])}
      onTouchStart={(e) => (startY.current = e.touches[0].clientY)}
      onTouchEnd={(e) => {
        if (startY.current === null) return;
        const dy = e.changedTouches[0].clientY - startY.current;
        startY.current = null;
        if (Math.abs(dy) > 30) {
          e.preventDefault(); // a drag, not a tap: no click after it
          step(dy < 0 ? 1 : -1);
        }
      }}
      aria-expanded={sheet !== "peek"}
      aria-label={sheet === "full" ? s.sheetLess : s.sheetMore}
    >
      <span aria-hidden />
    </button>
  );
}

/** The live sidebar: each card once its data has loaded. */
function LiveCards({
  data,
  lang,
  s,
  onSelect,
  onLook,
  showLayer,
}: {
  data: StaticData;
  lang: Lang;
  s: Strings;
  onSelect: (id: string) => void;
  onLook: (f: Focus) => void;
  showLayer: (k: keyof LayerToggles) => void;
}) {
  const { dash, area, alerts, stations, cities, forecastCheck, outlook, compare, fireHistory, danger, transboundary } = data;
  return (
    <>
      {dash ? <Dashboard data={dash} lang={lang} s={s} /> : <div className="muted">{s.loading}</div>}
      {alerts && <AlertsCard data={alerts} lang={lang} s={s} onSelect={onSelect} onLook={onLook} />}
      {cities.length > 0 && <HealthCard cities={cities} check={forecastCheck} s={s} />}
      {stations && <StationsList data={stations} lang={lang} s={s} />}
      {dash && <FireStats data={dash} area={area} lang={lang} s={s} onSelect={onSelect} />}
      {compare && <CompareCard data={compare} lang={lang} s={s} />}
      {danger && <RiskPanel data={danger} lang={lang} s={s} onShow={() => showLayer("risk")} />}
      {fireHistory && <RepeatBurnCard data={fireHistory} lang={lang} s={s} onShow={() => showLayer("burnHistory")} />}
      {outlook && <OutlookCard data={outlook} lang={lang} s={s} />}
      {transboundary && <TransboundaryPanel data={transboundary} lang={lang} s={s} onSelect={onSelect} />}
      {cities.length > 0 && <Cities cities={cities} lang={lang} s={s} />}
      <Sources s={s} />
    </>
  );
}
