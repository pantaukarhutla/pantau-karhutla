// Camera and terrain: 3D tilts over real terrain, 2D is flat and top-down;
// opening a fire frames it, closing it returns to the national overview. An
// open panel becomes map padding, so every camera move centres in the part
// of the map still visible.
import { useEffect, useRef } from "react";
import type { EventPage } from "../api/events";
import { TERRAIN_EXAGGERATION } from "./style";
import { isPhone, mapPadding } from "../viewport";
import type { MapHandle } from "./useMap";

interface View {
  center: [number, number];
  zoom: number;
}

export function useCamera(
  handle: React.RefObject<MapHandle | null>,
  is3d: boolean,
  selected: EventPage | null,
  home: View,
  panelOpen: boolean,
) {
  // Before the selection effect below, so a fire is framed in the new padding.
  useEffect(() => {
    handle.current?.map.setPadding(mapPadding(panelOpen));
  }, [handle, panelOpen]);

  const firstMode = useRef(true);
  useEffect(() => {
    const h = handle.current;
    if (!h) return;
    h.loaded.then(() => h.map.setTerrain(is3d ? { source: "terrainDem", exaggeration: TERRAIN_EXAGGERATION } : null));
    // The constructor already set the initial camera; only animate on toggles.
    if (firstMode.current) {
      firstMode.current = false;
      return;
    }
    if (!selected) h.map.easeTo({ pitch: is3d ? 45 : 0, bearing: is3d ? -8 : 0, duration: 600 });
    // Only the 2D/3D toggle moves the camera here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [is3d]);

  const hadSelection = useRef(false);
  const homeRef = useRef(home);
  homeRef.current = home;
  useEffect(() => {
    const map = handle.current?.map;
    if (!map) return;
    if (selected) {
      hadSelection.current = true;
      const [w, s, e, n] = selected.bbox;
      map.fitBounds(
        [
          [w, s],
          [e, n],
        ],
        {
          // Margins inside the map padding: clear of the layer button on
          // phones, and of the legend and time slider (bottom ~250 px) on desktop.
          padding: isPhone() ? { top: 64, bottom: 16, left: 24, right: 24 } : { top: 90, bottom: 250, left: 40, right: 40 },
          maxZoom: 13,
          pitch: is3d ? 62 : 0,
          bearing: is3d ? -20 : 0,
          duration: 1600,
        },
      );
    } else if (hadSelection.current) {
      hadSelection.current = false;
      map.flyTo({ center: homeRef.current.center, zoom: homeRef.current.zoom, pitch: is3d ? 45 : 0, bearing: is3d ? -8 : 0, duration: 1400 });
    }
  }, [handle, selected, is3d]);
}
