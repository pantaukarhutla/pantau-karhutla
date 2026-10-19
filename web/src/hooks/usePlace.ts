// "Cek lokasimu": whether the panel is open, the chosen point, and whether
// the next map tap picks it.
import { useCallback, useState } from "react";
import type { Focus } from "../MapView";

export interface ChosenPlace {
  lon: number;
  lat: number;
  /** place name when chosen from the search; null for GPS or a map tap */
  label: string | null;
}

export interface PlaceCheck {
  open: boolean;
  setOpen: (open: boolean) => void;
  place: ChosenPlace | null;
  /** the next map tap picks the place */
  picking: boolean;
  togglePicking: () => void;
  /** set the place and fly there (zoom: closer for a village than a province) */
  choose: (lon: number, lat: number, label: string | null, zoom?: number) => void;
  /** the phone's position; sets gpsError when it is refused or times out */
  locate: () => void;
  gpsError: boolean;
  close: () => void;
}

export function usePlace(lookAt: (f: Focus) => void): PlaceCheck {
  const [open, setOpen] = useState(false);
  const [place, setPlace] = useState<ChosenPlace | null>(null);
  const [picking, setPicking] = useState(false);
  const [gpsError, setGpsError] = useState(false);
  const choose = useCallback(
    (lon: number, lat: number, label: string | null, zoom = 8.5) => {
      setPicking(false);
      setPlace({ lon, lat, label });
      lookAt({ lon, lat, zoom });
    },
    [lookAt],
  );
  const locate = useCallback(() => {
    setGpsError(false);
    navigator.geolocation?.getCurrentPosition(
      (p) => choose(p.coords.longitude, p.coords.latitude, null),
      () => setGpsError(true),
      { enableHighAccuracy: false, timeout: 15_000, maximumAge: 600_000 },
    );
  }, [choose]);
  return {
    open,
    setOpen,
    place,
    picking,
    togglePicking: () => setPicking(!picking),
    choose,
    locate,
    gpsError,
    close: () => {
      setOpen(false);
      setPicking(false);
    },
  };
}
