// The frame of the live satellite layer (Himawari-9 visible): the newest
// daylight frame NASA GIBS has published, re-checked every 10 minutes while
// the layer is on.
import { useEffect, useState } from "react";
import { himawariTime } from "../map/protocols";

const RECHECK_MS = 600_000;

export function useHimawariTime(enabled: boolean): string | null {
  const [time, setTime] = useState<string | null>(null);
  useEffect(() => {
    if (!enabled) return;
    let live = true;
    const check = () => himawariTime().then((t) => live && t && setTime(t));
    check();
    const timer = window.setInterval(check, RECHECK_MS);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, [enabled]);
  return enabled ? time : null;
}
