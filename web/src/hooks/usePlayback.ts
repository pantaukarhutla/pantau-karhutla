import { useEffect, useState } from "react";

export interface Playback {
  /** current step, within 0..n-1 */
  index: number;
  setIndex: (i: number) => void;
  playing: boolean;
  setPlaying: (p: boolean) => void;
  /** play / pause; a timeline that stops at its end restarts from `start` */
  toggle: () => void;
  /** jump to a step chosen by the reader: stops playing */
  scrub: (i: number) => void;
}

interface Options {
  /** first step: where a loop starts over */
  start: number;
  /** at the end: start over (true) or stop (false) */
  loop: boolean;
  /** false: hold still while the timeline is not on screen */
  active: boolean;
}

/** A timeline of `n` steps that plays one step every `stepMs`. */
export function usePlayback(n: number, stepMs: number, { start, loop, active }: Options): Playback {
  const [raw, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const index = Math.min(raw, Math.max(0, n - 1));

  useEffect(() => {
    if (!playing || !active) return;
    const t = setInterval(() => {
      const atEnd = index + 1 >= n;
      if (atEnd && !loop) setPlaying(false);
      else setIndex(atEnd ? start : index + 1);
    }, stepMs);
    return () => clearInterval(t);
  }, [playing, active, index, n, start, loop, stepMs]);

  return {
    index,
    setIndex,
    playing,
    setPlaying,
    toggle: () => {
      if (!playing && !loop && index >= n - 1) setIndex(start);
      setPlaying(!playing);
    },
    scrub: (i) => {
      setPlaying(false);
      setIndex(i);
    },
  };
}
