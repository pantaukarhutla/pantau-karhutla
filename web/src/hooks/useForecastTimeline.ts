// The haze timeline: the last 72 h and the 72 h forecast on one slider
// (3-hourly smog frames); plume and wind frames follow the nearest time.
import { useEffect, useMemo } from "react";
import type { Plumes, Smog, Wind, WindFrame } from "../api/air";
import { nearestFrame } from "../grid";
import { usePlayback, type Playback } from "./usePlayback";

export interface ForecastTimeline {
  /** smog frame times (ISO) */
  times: string[];
  /** frame closest to the present: where the slider opens */
  nowIndex: number;
  playback: Playback;
  /** time shown (ms) */
  time: number;
  /** -1 before the smoke model's first frame (it only runs forward) */
  plumeFrame: number;
  wind: WindFrame | null;
}

/** `active`: the forecast bar is on screen (plays only then). */
export function useForecastTimeline(smog: Smog | null, plumes: Plumes | null, wind: Wind | null, active: boolean): ForecastTimeline {
  const times = useMemo(() => smog?.times ?? [], [smog]);
  const nowIndex = useMemo(() => (times.length ? nearestFrame(times, Date.now()) : 0), [times]);
  // One step every 0.6 s; after +72 h it starts over from -72 h.
  const playback = usePlayback(times.length, 600, { start: 0, loop: true, active });
  const { setIndex } = playback;
  useEffect(() => setIndex(nowIndex), [nowIndex, setIndex]);

  const time = times.length ? Date.parse(times[playback.index]) : Date.now();
  const plumeFrame = !plumes?.times.length
    ? 0
    : time < Date.parse(plumes.times[0]) - 90 * 60_000
      ? -1
      : nearestFrame(plumes.times, time);
  const windFrame = useMemo(() => {
    if (!wind?.times.length) return null;
    const k = nearestFrame(wind.times, time);
    return { grid: wind.grid, u: wind.u_x10[k], v: wind.v_x10[k] };
  }, [wind, time]);

  return { times, nowIndex, playback, time, plumeFrame, wind: windFrame };
}
