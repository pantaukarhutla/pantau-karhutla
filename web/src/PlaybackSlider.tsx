// Play button + range slider for a timeline (forecast hours, season days,
// a fire's days). The readout beside it is the caller's.
import type { ReactNode } from "react";
import type { Playback } from "./hooks/usePlayback";
import type { Strings } from "./i18n";

export function PlaybackSlider({
  p,
  min,
  max,
  label,
  className,
  wordy,
  s,
  children,
}: {
  p: Playback;
  min: number;
  max: number;
  label: string;
  className: string;
  /** "▶ Play" with words, rather than the bare symbol */
  wordy: boolean;
  s: Strings;
  children: ReactNode;
}) {
  const word = p.playing ? s.pause : s.play;
  const icon = p.playing ? "❚❚" : "▶";
  return (
    <div className={className} role="group" aria-label={label}>
      <button className="play" onClick={p.toggle} aria-label={wordy ? undefined : word}>
        {wordy ? `${icon} ${word}` : icon}
      </button>
      <input type="range" min={min} max={max} value={p.index} onChange={(e) => p.scrub(Number(e.target.value))} aria-label={label} />
      {children}
    </div>
  );
}
