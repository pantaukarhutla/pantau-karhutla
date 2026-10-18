// "Cek lokasimu": whether the panel is open, the chosen point, and whether
// the next map tap picks it.
import { useCallback, useState } from "react";
import type { Focus } from "../MapView";

export interface ChosenPlace {
  lon: number;
  lat: number;
  /** regency name when chosen from the search; null for GPS or a map tap */
  label: string | null;
}

export interface PlaceCheck {
  open: boolean;
  setOpen: (open: boolean) => void;
  place: ChosenPlace | null;
  /** the next map tap picks the place */
  picking: boolean;
  togglePicking: () => void;
  /** set the place and fly there */
  choose: (lon: number, lat: number, label: string | null) => void;
  close: () => void;
}

export function usePlace(lookAt: (f: Focus) => void): PlaceCheck {
  const [open, setOpen] = useState(false);
  const [place, setPlace] = useState<ChosenPlace | null>(null);
  const [picking, setPicking] = useState(false);
  const choose = useCallback(
    (lon: number, lat: number, label: string | null) => {
      setPicking(false);
      setPlace({ lon, lat, label });
      lookAt({ lon, lat, zoom: 8.5 });
    },
    [lookAt],
  );
  return {
    open,
    setOpen,
    place,
    picking,
    togglePicking: () => setPicking(!picking),
    choose,
    close: () => {
      setOpen(false);
      setPicking(false);
    },
  };
}
