// The opened fire: its page, progression and spread forecast, loaded when the
// id changes. A late answer for a fire no longer open is dropped.
import { useEffect, useMemo, useState } from "react";
import type { CityOutlook, Wind } from "../api/air";
import { loadEvent, loadProgression, type Dashboard, type EventPage, type LiveEvent, type Progression } from "../api/events";
import { loadSpread, type SpreadForecast } from "../api/fire";
import { wibDate } from "../format";
import { smokeOutlook, type SmokeOutlook } from "../trajectory";
import { usePlayback, type Playback } from "./usePlayback";

/** Older spread forecasts are not shown (the pipeline refreshes them every run, ~2 h). */
const SPREAD_MAX_AGE_H = 12;

export interface SelectedEvent {
  event: EventPage | null;
  progression: Progression | null;
  spread: SpreadForecast | null;
  spreadDay: number;
  setSpreadDay: (d: number) => void;
  /** the fire's day timeline */
  timeline: Playback;
}

export function useSelectedEvent(eventId: string | null, dash: Dashboard | null, live: LiveEvent[]): SelectedEvent {
  const [event, setEvent] = useState<EventPage | null>(null);
  const [progression, setProgression] = useState<Progression | null>(null);
  const [spread, setSpread] = useState<SpreadForecast | null>(null);
  const [spreadDay, setSpreadDay] = useState(0);
  // One day per second, stopping at the last.
  const timeline = usePlayback(event?.days.length ?? 0, 1000, { start: 0, loop: false, active: event !== null });
  const { setIndex, setPlaying } = timeline;

  useEffect(() => {
    if (!eventId || !dash) {
      setEvent(null);
      setSpread(null);
      return;
    }
    let cancelled = false;
    loadEvent(dash.season, eventId)
      .then((ev) => {
        if (cancelled) return;
        setEvent(ev);
        setIndex(ev.days.length - 1);
        setPlaying(false);
      })
      .catch(() => {
        if (cancelled) return;
        // Single-detection fires have no published page; show what the live
        // list knows instead of a dead link.
        const fromList = live.find((e) => e.id === eventId);
        setEvent(fromList ? pageFromLive(fromList) : null);
        setIndex(0);
      });
    setProgression(null);
    loadProgression(dash.season, eventId).then((p) => !cancelled && setProgression(p));
    loadSpread(eventId).then((f) => {
      if (cancelled) return;
      setSpread(f);
      setSpreadDay(0);
    });
    return () => {
      cancelled = true;
    };
    // The live list is only a fallback: a list refresh must not reload the fire.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventId, dash]);

  // A spread forecast only for a fire still burning, and only a recent one:
  // forecasts are written for the most active fires each run and old files
  // stay on the server, so a fire that went out keeps its last forecast.
  const current = spread && event?.status === "active" && Date.now() - Date.parse(spread.t0) < SPREAD_MAX_AGE_H * 3_600_000;
  return { event, progression, spread: current ? spread : null, spreadDay, setSpreadDay, timeline };
}

/** Where the fire's smoke heads over the next day: live, still-burning fires only. */
export function useSmokeOutlook(event: EventPage | null, wind: Wind | null, towns: CityOutlook[], live: boolean): SmokeOutlook | null {
  return useMemo(() => {
    if (!event || event.status !== "active" || !wind || !live) return null;
    const [lon, lat] = event.centroid;
    return smokeOutlook(wind, lon, lat, Date.now(), towns);
  }, [event, wind, towns, live]);
}

function pageFromLive(e: LiveEvent): EventPage {
  const date = wibDate(e.lastSeen);
  return {
    id: e.id,
    name: e.name,
    status: e.status,
    first_seen: e.firstSeen,
    last_seen: e.lastSeen,
    hotspot_count: e.hotspots,
    peak_frp: e.peakFrp,
    total_frp: e.totalFrp,
    est_area_ha: e.areaHa,
    on_peat: e.onPeat,
    peat_share: null,
    provinsi: e.provinsi,
    kabupaten: e.kabupaten,
    nearest_town: "", // not in the live list
    nearest_town_km: 0,
    near_static: e.nearStatic,
    tier: e.tier,
    centroid: [e.lon, e.lat],
    bbox: [e.lon - 0.01, e.lat - 0.01, e.lon + 0.01, e.lat + 0.01],
    footprint: null,
    days: [{ date, hotspots: e.hotspots, frp_sum: e.totalFrp, peak_frp: e.peakFrp, area_ha: e.areaHa, growth_ha: e.areaHa, footprint: null }],
  };
}
