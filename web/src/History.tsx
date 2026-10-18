import type { Playback } from "./hooks/usePlayback";
import { PlaybackSlider } from "./PlaybackSlider";
import { MethodLink } from "./Methodology";
import { BarChart } from "./charts";
import type { HistorySummary } from "./api/history";
import { fmtDay, fmtInt } from "./format";
import type { Lang, Strings } from "./i18n";

// Daily detections: single series, same hue as the event FRP bars.
const BAR = "#d95926";

/** Day slider for the season history. */
export function HistoryBar({ h, p, lang, s }: { h: HistorySummary; p: Playback; lang: Lang; s: Strings }) {
  const day = h.days[p.index];
  if (!day) return null;
  return (
    <PlaybackSlider p={p} min={0} max={h.days.length - 1} label={s.history} className="forecast-bar" wordy={false} s={s}>
      <span className="forecast-label">
        <b>{fmtDay(day.date, lang)}</b> · {fmtInt(day.hotspots, lang)} {s.detections}
      </span>
    </PlaybackSlider>
  );
}

export function HistoryPanel({ h, p, lang, s }: { h: HistorySummary; p: Playback; lang: Lang; s: Strings }) {
  const day = h.days[p.index];
  const top = day ? Object.entries(day.provinsi).slice(0, 5) : [];
  return (
    <div className="dashboard">
      <section>
        <h2>
          <span>
            {s.historyTitle(fmtDay(h.start, lang))} <MethodLink id="history" s={s} />
          </span>
        </h2>
        <BarChart
          values={h.days.map((d) => ({ label: fmtDay(d.date, lang), value: d.hotspots }))}
          color={BAR}
          highlight={p.index}
          height={130}
          yFormat={(y) => fmtInt(y, lang)}
          ariaLabel={s.historyChart}
          onSelect={p.setIndex}
        />
        <p className="note">{s.historyChartNote}</p>
      </section>
      {day && (
        <section>
          <h2>
            {fmtDay(day.date, lang)} · {fmtInt(day.hotspots, lang)} {s.detections}
          </h2>
          <table className="table">
            <tbody>
              {top.map(([p, v]) => (
                <tr key={p}>
                  <td>{p}</td>
                  <td className="num">{fmtInt(v, lang)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      <p className="note">{s.historyNote}</p>
    </div>
  );
}
