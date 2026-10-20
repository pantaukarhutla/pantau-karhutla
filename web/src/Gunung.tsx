// Gunung terbakar (#/gunung): mountains with hotspots in the last 24 h, from the
// detections the map draws (events/hotspots_recent.json) and the summits in places.json.
import { useEffect, useMemo, useState } from "react";
import { tryJson } from "./api/fetch";
import type { HotspotRow } from "./api/events";
import { burningGunung, RADIUS_KM } from "./gunungList";
import { fmtDate, fmtInt } from "./format";
import type { Lang, Strings } from "./i18n";
import { landmarkName, loadPlaces } from "./PlaceSearch";
import { Pager, usePaged } from "./TableControls";

const SHOW_PEAKS = 3;

export function GunungTab({ lang, s, onOpenPlace }: { lang: Lang; s: Strings; onOpenPlace: (lon: number, lat: number, label: string) => void }) {
  const [data, setData] = useState<{ at: string; rows: HotspotRow[] } | null>(null);
  const [places, setPlaces] = useState<Awaited<ReturnType<typeof loadPlaces>>>(null);
  useEffect(() => {
    tryJson<{ generated_at: string; rows: HotspotRow[] }>("events/hotspots_recent.json").then((f) => setData({ at: f?.generated_at ?? "", rows: f?.rows ?? [] }));
    loadPlaces().then(setPlaces);
  }, []);
  const list = useMemo(() => (data && places ? burningGunung(places, data.rows) : null), [data, places]);
  const paged = usePaged(list ?? [], 100);
  if (!list || !data) return <p className="muted">{s.loading}</p>;
  // Ages count from when the file was written; add the time since.
  const sinceH = data.at ? Math.max(0, (Date.now() - Date.parse(data.at)) / 3.6e6) : 0;
  return (
    <div className="table-wrap">
      <p className="desa-lead">{list.length ? s.gunungLead(fmtInt(list.length, lang), RADIUS_KM) : s.gunungEmpty}</p>
      <table className="table data">
        <thead>
          <tr>
            <th>{s.gunungName}</th>
            <th className="num">{s.data24h}</th>
            <th className="num">{s.gunungNewest}</th>
          </tr>
        </thead>
        <tbody>
          {paged.rows.map((g) => {
            const name = landmarkName(g.name, g.type, s);
            const others = g.peaks.slice(1);
            return (
              <tr key={`${g.lon},${g.lat}`} className="clickable" onClick={() => onOpenPlace(g.lon, g.lat, `${name}, ${g.kabupaten}`)}>
                <td>
                  {name}
                  <div className="muted small">
                    {g.kabupaten} · {g.provinsi}
                  </div>
                  {others.length > 0 && (
                    <div className="muted small">
                      {s.gunungAlso(
                        others
                          .slice(0, SHOW_PEAKS)
                          .map((p) => p.name)
                          .join(", "),
                        Math.max(0, others.length - SHOW_PEAKS),
                      )}
                    </div>
                  )}
                </td>
                <td className="num">{fmtInt(g.hotspots, lang)}</td>
                <td className="num">{s.hoursAgo(g.newestH + sinceH)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <Pager paged={paged} />
      <p className="note">
        {s.gunungNote} {data.at && `${s.updated} ${fmtDate(data.at, lang)} WIB.`}
      </p>
    </div>
  );
}
