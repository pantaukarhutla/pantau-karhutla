// The day of the satellite haze layer (MODIS aerosol optical depth): the
// newest complete day NASA has published, or the replayed day in history
// mode. Looked up only while the layer is on.
import { useEffect, useState } from "react";
import { wibDate } from "../format";
import { aodDateFor } from "../map/protocols";

export function useAodDate(enabled: boolean, historyDay: string | undefined): string | null {
  const [date, setDate] = useState<string | null>(null);
  useEffect(() => {
    if (!enabled) return;
    let live = true;
    aodDateFor(historyDay ?? wibDate(new Date().toISOString()), !historyDay).then((d) => live && setDate(d));
    return () => {
      live = false;
    };
  }, [enabled, historyDay]);
  return enabled ? date : null;
}
