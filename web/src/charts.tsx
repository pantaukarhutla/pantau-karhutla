import { useMemo, useRef, useState } from "react";

// Small dependency-free SVG charts. Mark specs: 2px lines, thin bars with a
// 2px gap and rounded data-ends, recessive axes, crosshair + tooltip on hover.

export interface Series {
  key: string;
  label: string;
  points: [number, number][]; // x, y
  color: string;
  emphasis?: boolean; // the highlighted series; others are muted context
}

interface LineProps {
  series: Series[];
  height?: number;
  xFormat: (x: number) => string;
  yFormat: (y: number) => string;
  xTicks?: number[];
  /** Tooltip heading; defaults to xFormat (axis ticks can be coarser). */
  xTooltipFormat?: (x: number) => string;
  ariaLabel: string;
}

const PAD = { top: 10, right: 52, bottom: 20, left: 40 };

function niceMax(v: number): number {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  return Math.ceil(v / p) * p;
}

export function LineChart({ series, height = 150, xFormat, yFormat, xTicks, xTooltipFormat, ariaLabel }: LineProps) {
  const ref = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const width = 340;
  const all = series.flatMap((s) => s.points);
  const xMin = Math.min(...all.map((p) => p[0]));
  const xMax = Math.max(...all.map((p) => p[0]));
  const yMax = niceMax(Math.max(...all.map((p) => p[1])));
  const sx = (x: number) => PAD.left + ((x - xMin) / (xMax - xMin || 1)) * (width - PAD.left - PAD.right);
  const sy = (y: number) => height - PAD.bottom - (y / yMax) * (height - PAD.top - PAD.bottom);
  const path = (pts: [number, number][]) => pts.map((p, i) => `${i ? "L" : "M"}${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join("");

  const onMove = (e: React.PointerEvent) => {
    const r = ref.current!.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * width;
    const t = xMin + ((x - PAD.left) / (width - PAD.left - PAD.right)) * (xMax - xMin);
    setHover(Math.max(xMin, Math.min(xMax, Math.round(t))));
  };
  const valueAt = (s: Series, x: number) => {
    let best: [number, number] | undefined;
    for (const p of s.points) if (p[0] <= x) best = p;
    return best && x <= s.points[s.points.length - 1][0] ? best[1] : undefined;
  };
  // Order the emphasised series last so it draws on top.
  const ordered = [...series].sort((a, b) => Number(!!a.emphasis) - Number(!!b.emphasis));

  return (
    <div className="chart">
      <svg
        ref={ref}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={ariaLabel}
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      >
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line className="grid" x1={PAD.left} x2={width - PAD.right} y1={sy(yMax * f)} y2={sy(yMax * f)} />
            <text className="tick" x={PAD.left - 6} y={sy(yMax * f)} dy="0.32em" textAnchor="end">
              {yFormat(yMax * f)}
            </text>
          </g>
        ))}
        {(xTicks ?? [xMin, xMax]).map((x) => (
          <text key={x} className="tick" x={sx(x)} y={height - 4} textAnchor="middle">
            {xFormat(x)}
          </text>
        ))}
        {ordered.map((s) => (
          <path
            key={s.key}
            d={path(s.points)}
            fill="none"
            stroke={s.color}
            strokeWidth={s.emphasis ? 2.5 : 1.5}
            strokeLinejoin="round"
            opacity={s.emphasis || series.length === 1 ? 1 : 0.75}
          />
        ))}
        {/* Direct labels at line ends (<= 4 series), in text ink, beside a colour swatch. */}
        {series.length > 1 &&
          series.map((s) => {
            const last = s.points[s.points.length - 1];
            return (
              <g key={s.key} transform={`translate(${sx(last[0]) + 4},${sy(last[1])})`}>
                <circle r={3} fill={s.color} />
                <text className={s.emphasis ? "label strong" : "label"} x={6} dy="0.32em">
                  {s.label}
                </text>
              </g>
            );
          })}
        {hover !== null && (
          <line className="crosshair" x1={sx(hover)} x2={sx(hover)} y1={PAD.top} y2={height - PAD.bottom} />
        )}
        <rect x={PAD.left} y={0} width={width - PAD.left - PAD.right} height={height} fill="transparent" />
      </svg>
      {hover !== null && (
        <div className="tooltip" style={{ left: `${(sx(hover) / width) * 100}%` }}>
          <div className="tooltip-title">{(xTooltipFormat ?? xFormat)(hover)}</div>
          {series.map((s) => {
            const v = valueAt(s, hover);
            return v === undefined ? null : (
              <div key={s.key} className="tooltip-row">
                <span className="swatch" style={{ background: s.color }} />
                <span>{s.label}</span>
                <b>{yFormat(v)}</b>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

interface BarProps {
  values: { label: string; value: number }[];
  color: string;
  highlight?: number; // index drawn at full strength (timeline position)
  height?: number;
  yFormat: (y: number) => string;
  ariaLabel: string;
  onSelect?: (i: number) => void;
}

export function BarChart({ values, color, highlight, height = 110, yFormat, ariaLabel, onSelect }: BarProps) {
  const [hover, setHover] = useState<number | null>(null);
  const width = 340;
  const yMax = useMemo(() => niceMax(Math.max(...values.map((v) => v.value), 0)), [values]);
  const inner = width - PAD.left - 12;
  const step = inner / Math.max(values.length, 1);
  const bw = Math.max(1, step - 2); // 2px surface gap between bars
  const sy = (y: number) => height - PAD.bottom - (y / yMax) * (height - PAD.top - PAD.bottom);
  const base = sy(0);
  const shown = hover ?? highlight;
  return (
    <div className="chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={ariaLabel} onPointerLeave={() => setHover(null)}>
        {[0, 1].map((f) => (
          <g key={f}>
            <line className="grid" x1={PAD.left} x2={width - 12} y1={sy(yMax * f)} y2={sy(yMax * f)} />
            <text className="tick" x={PAD.left - 6} y={sy(yMax * f)} dy="0.32em" textAnchor="end">
              {yFormat(yMax * f)}
            </text>
          </g>
        ))}
        {values.map((v, i) => {
          const x = PAD.left + i * step + 1;
          const y = sy(v.value);
          const r = Math.min(4, bw / 2, base - y);
          // Rounded data-end, square at the baseline.
          const d = `M${x},${base}V${y + r}Q${x},${y} ${x + r},${y}H${x + bw - r}Q${x + bw},${y} ${x + bw},${y + r}V${base}Z`;
          return (
            <g key={i} onPointerEnter={() => setHover(i)} onClick={() => onSelect?.(i)} style={{ cursor: onSelect ? "pointer" : undefined }}>
              <rect x={PAD.left + i * step} y={PAD.top} width={step} height={height - PAD.top - PAD.bottom} fill="transparent" />
              <path d={d} fill={color} opacity={highlight === undefined || i <= highlight ? 1 : 0.3} />
            </g>
          );
        })}
        <line className="axis" x1={PAD.left} x2={width - 12} y1={base} y2={base} />
        <text className="tick" x={PAD.left} y={height - 4}>
          {values[0]?.label}
        </text>
        <text className="tick" x={width - 12} y={height - 4} textAnchor="end">
          {values[values.length - 1]?.label}
        </text>
      </svg>
      {shown !== undefined && shown !== null && values[shown] && hover !== null && (
        <div className="tooltip" style={{ left: `${((PAD.left + (shown + 0.5) * step) / width) * 100}%` }}>
          <div className="tooltip-title">{values[shown].label}</div>
          <div className="tooltip-row">
            <span className="swatch" style={{ background: color }} />
            <b>{yFormat(values[shown].value)}</b>
          </div>
        </div>
      )}
    </div>
  );
}
