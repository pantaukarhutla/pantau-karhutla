// Season history ("Riwayat"): a day slider from 1 July instead of the
// forecast. The summary loads the first time the mode is opened.
import { useEffect, useMemo, useState } from "react";
import type { Smog } from "../api/air";
import type { HotspotRow } from "../api/events";
import { dayPm25, loadDayFires, loadHistory, type HistoryDay, type HistorySummary } from "../api/history";
import { usePlayback, type Playback } from "./usePlayback";

export interface SeasonHistory {
  summary: HistorySummary;
  playback: Playback;
  /** the day on the slider (none if the summary has no days) */
  day: HistoryDay | undefined;
  /** that day's fire cells */
  fires: HotspotRow[];
  /** that day's PM2.5 */
  smog: Smog | null;
}

/** null while history mode is off or its summary has not loaded. */
export function useHistoryMode(on: boolean): SeasonHistory | null {
  const [summary, setSummary] = useState<HistorySummary | null>(null);
  const [fires, setFires] = useState<HotspotRow[]>([]);
  const shown = on && summary !== null;
  // One day every 0.45 s, looping.
  const playback = usePlayback(summary?.days.length ?? 0, 450, { start: 0, loop: true, active: shown });
  const { setIndex } = playback;
  const day = summary?.days[playback.index];

  useEffect(() => {
    if (!on || summary) return;
    loadHistory().then((h) => {
      if (!h) return;
      setSummary(h);
      setIndex(h.days.length - 1);
    });
  }, [on, summary, setIndex]);

  useEffect(() => {
    if (!shown || !day) return;
    let cancelled = false;
    loadDayFires(day.date).then((f) => !cancelled && setFires(f));
    return () => {
      cancelled = true;
    };
  }, [shown, day]);

  const smog = useMemo(() => (summary && day ? dayPm25(summary, day.date) : null), [summary, day]);

  return shown ? { summary, playback, day, fires, smog } : null;
}
