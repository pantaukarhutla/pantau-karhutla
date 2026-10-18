// The pipeline's files that load once per visit. Optional files stay null
// when missing; the two the app needs report an error instead.
import { useEffect, useState } from "react";
import { loadArea, loadDashboard, loadLive, loadLiveOut, loadRecentHotspots, type AreaEstimate, type Dashboard, type HotspotRow, type LiveEvent } from "../api/events";
import {
  loadCities,
  loadSmog,
  loadStations,
  loadTransboundary,
  loadWind,
  type CityOutlook,
  type ForecastCheck,
  type Smog,
  type Stations,
  type Transboundary,
  type Wind,
} from "../api/air";
import { loadAlerts, loadDanger, loadFireHistory, loadFireHistoryGrid, loadOutlook, type Alerts, type Danger, type FireHistory, type Outlook } from "../api/fire";
import { loadCompare, type Compare } from "../api/compare";
import type { GridSpec } from "../grid";

export interface StaticData {
  /** a required file failed to load */
  error: string | null;
  dash: Dashboard | null;
  events: LiveEvent[];
  hotspots: HotspotRow[];
  area: AreaEstimate | null;
  alerts: Alerts | null;
  smog: Smog | null;
  wind: Wind | null;
  stations: Stations | null;
  cities: CityOutlook[];
  forecastCheck: ForecastCheck | null;
  transboundary: Transboundary | null;
  danger: Danger | null;
  outlook: Outlook | null;
  fireHistory: FireHistory | null;
  compare: Compare | null;
}

export function useStaticData(): StaticData {
  const [error, setError] = useState<string | null>(null);
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [hotspots, setHotspots] = useState<HotspotRow[]>([]);
  const [area, setArea] = useState<AreaEstimate | null>(null);
  const [alerts, setAlerts] = useState<Alerts | null>(null);
  const [smog, setSmog] = useState<Smog | null>(null);
  const [wind, setWind] = useState<Wind | null>(null);
  const [stations, setStations] = useState<Stations | null>(null);
  const [cities, setCities] = useState<CityOutlook[]>([]);
  const [forecastCheck, setForecastCheck] = useState<ForecastCheck | null>(null);
  const [transboundary, setTransboundary] = useState<Transboundary | null>(null);
  const [danger, setDanger] = useState<Danger | null>(null);
  const [outlook, setOutlook] = useState<Outlook | null>(null);
  const [fireHistory, setFireHistory] = useState<FireHistory | null>(null);
  const [compare, setCompare] = useState<Compare | null>(null);

  useEffect(() => {
    // Updates from a cancelled run (React mounts twice in development) are dropped.
    let live = true;
    const keep =
      <T,>(set: (v: T) => void) =>
      (v: T) => {
        if (live) set(v);
      };
    // What the first screen shows: fires, smoke, alerts, air and health advice.
    const fail = keep((e: unknown) => setError(String(e)));
    loadLive()
      .then(keep((burning: LiveEvent[]) => setEvents((out) => [...burning, ...out])))
      .catch(fail);
    loadDashboard().then(keep(setDash)).catch(fail);
    loadRecentHotspots().then(keep(setHotspots));
    loadAlerts().then(keep(setAlerts));
    loadSmog().then(keep(setSmog));
    loadWind().then(keep(setWind));
    loadStations().then(keep(setStations));
    loadCities().then(
      keep((c: Awaited<ReturnType<typeof loadCities>>) => {
        setCities(c?.cities ?? []);
        setForecastCheck(c?.forecast_check ?? null);
      }),
    );
    // The rest (folded cards, grey dots of fires already out) once the page
    // has drawn, so it does not compete with the first screen on slow phones.
    const cancelLater = afterFirstPaint(() => {
      loadLiveOut().then(keep((out: LiveEvent[]) => setEvents((burning) => [...burning, ...out])));
      loadArea().then(keep(setArea));
      loadTransboundary().then(keep(setTransboundary));
      loadDanger().then(keep(setDanger));
      loadOutlook().then(keep(setOutlook));
      loadFireHistory().then(keep(setFireHistory));
      loadCompare().then(keep(setCompare));
    });
    return () => {
      live = false;
      cancelLater();
    };
  }, []);

  return {
    error,
    dash,
    events,
    hotspots,
    area,
    alerts,
    smog,
    wind,
    stations,
    cities,
    forecastCheck,
    transboundary,
    danger,
    outlook,
    fireHistory,
    compare,
  };
}

/** Run `fn` when the browser is idle after the first paint (at most ~2.5 s
 * later); returns a cancel function. */
function afterFirstPaint(fn: () => void): () => void {
  // Safari has no requestIdleCallback: fall back to a short delay.
  if (typeof window.requestIdleCallback === "function") {
    const id = window.requestIdleCallback(fn, { timeout: 2500 });
    return () => window.cancelIdleCallback(id);
  }
  const id = setTimeout(fn, 1200);
  return () => clearTimeout(id);
}

/** False until the browser is idle after the first paint. */
export function useAfterFirstPaint(): boolean {
  const [done, setDone] = useState(false);
  useEffect(() => afterFirstPaint(() => setDone(true)), []);
  return done;
}

/** A file fetched only once `wanted` (e.g. its layer is switched on), then kept. */
export function useOnDemand<T>(load: () => Promise<T | null>, wanted: boolean): T | null {
  const [value, setValue] = useState<T | null>(null);
  const [asked, setAsked] = useState(false);
  useEffect(() => {
    if (!wanted || asked) return;
    setAsked(true);
    load().then(setValue);
  }, [wanted, asked, load]);
  return value;
}

export interface BurnGrid {
  grid: GridSpec;
  field: Int8Array;
}

/** Fire years per cell. The grid is ~0.4 MB: fetched only once `wanted`. */
export function useBurnGrid(history: FireHistory | null, wanted: boolean): BurnGrid | null {
  const [burnGrid, setBurnGrid] = useState<BurnGrid | null>(null);
  useEffect(() => {
    if (wanted && history && !burnGrid) {
      loadFireHistoryGrid(history.grid).then((field) => field && setBurnGrid({ grid: history.grid, field }));
    }
  }, [wanted, history, burnGrid]);
  return burnGrid;
}
