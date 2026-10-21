import { useEffect, useRef, useState, type ReactNode } from "react";
import { formatNumber } from "../format";

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

// Tightest clean axis among 3-5 intervals, so a peak of 42 gets 0-50, not 0-80.
function niceScale(value: number): { max: number; ticks: number[] } {
  if (value <= 0) return { max: 4, ticks: [0, 1, 2, 3, 4] };
  let best = { max: Infinity, step: 1 };
  for (const n of [3, 4, 5]) {
    const raw = value / n;
    const mag = 10 ** Math.floor(Math.log10(raw));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
    if (step * n < best.max) best = { max: step * n, step };
  }
  const ticks = [];
  for (let t = 0; t <= best.max + 1e-9; t += best.step) ticks.push(t);
  return { max: best.max, ticks };
}

// Column with a 4px rounded data-end and a square base on the baseline.
function columnPath(x: number, y: number, w: number, h: number): string {
  if (h <= 0) return "";
  const r = Math.min(4, w / 2, h);
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}

export interface ColumnDatum {
  key: string;
  label: string;
  tooltip: string;
  value: number;
}

export function ColumnChart({ data, height = 220, valueLabel }: { data: ColumnDatum[]; height?: number; valueLabel: string }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);

  const margin = { top: 12, right: 4, bottom: 26, left: 32 };
  const innerW = Math.max(0, width - margin.left - margin.right);
  const innerH = height - margin.top - margin.bottom;
  const { max, ticks } = niceScale(Math.max(...data.map((d) => d.value), 0));
  const band = data.length ? innerW / data.length : 0;
  const barW = Math.min(24, Math.max(2, band - 4));
  const labelEvery = Math.max(1, Math.ceil(56 / Math.max(band, 1)));
  const y = (v: number) => margin.top + innerH - (v / max) * innerH;
  const hovered = hover !== null ? data[hover] : null;

  return (
    <div className="chart" ref={ref}>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label={`${valueLabel} per week, last ${data.length} weeks`}>
          {ticks.map((t) => (
            <g key={t}>
              <line className="chart-grid" x1={margin.left} x2={width - margin.right} y1={y(t)} y2={y(t)} />
              <text className="chart-axis" x={margin.left - 8} y={y(t)} dy="0.32em" textAnchor="end">
                {formatNumber(t)}
              </text>
            </g>
          ))}
          {data.map((d, i) => {
            const cx = margin.left + band * i + band / 2;
            return (
              <g key={d.key}>
                <path
                  className={`chart-col${hover === i ? " is-hover" : ""}${hover !== null && hover !== i ? " is-dim" : ""}`}
                  d={columnPath(cx - barW / 2, y(d.value), barW, margin.top + innerH - y(d.value))}
                />
                {i % labelEvery === 0 && (
                  <text className="chart-axis" x={cx} y={height - 8} textAnchor="middle">
                    {d.label}
                  </text>
                )}
                <rect
                  x={margin.left + band * i}
                  y={margin.top}
                  width={band}
                  height={innerH}
                  fill="transparent"
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                />
              </g>
            );
          })}
          <line className="chart-baseline" x1={margin.left} x2={width - margin.right} y1={y(0)} y2={y(0)} />
        </svg>
      )}
      {hovered && hover !== null && (
        <div
          className="chart-tooltip"
          style={{
            left: Math.min(Math.max(margin.left + band * hover + band / 2, 70), width - 70),
            top: y(hovered.value) - 8,
          }}
        >
          <div className="chart-tooltip-title">{hovered.tooltip}</div>
          <div className="chart-tooltip-row">
            <span className="swatch" style={{ background: "var(--series-1)" }} />
            <span>{valueLabel}</span>
            <strong>{formatNumber(hovered.value)}</strong>
          </div>
        </div>
      )}
      <table className="sr-only">
        <caption>{valueLabel} per week</caption>
        <tbody>
          {data.map((d) => (
            <tr key={d.key}>
              <th scope="row">{d.tooltip}</th>
              <td>{d.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export interface BarDatum {
  key: string;
  label: ReactNode;
  value: number;
  color?: string;
  onClick?: () => void;
}

export function BarList({ data, total }: { data: BarDatum[]; total?: number }) {
  const max = Math.max(...data.map((d) => d.value), 1);
  const sum = total ?? data.reduce((s, d) => s + d.value, 0);
  return (
    <ul className="bar-list">
      {data.map((d) => (
        <li key={d.key} className={d.onClick ? "clickable" : undefined} onClick={d.onClick}>
          <div className="bar-list-label">
            <span>{d.label}</span>
            <span className="bar-list-value">
              {formatNumber(d.value)}
              <span className="bar-list-pct">{sum ? `${Math.round((d.value / sum) * 100)}%` : ""}</span>
            </span>
          </div>
          <div className="bar-list-track">
            <div
              className="bar-list-fill"
              style={{ width: `${(d.value / max) * 100}%`, background: d.color ?? "var(--series-1)" }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

export interface SegmentDatum {
  key: string;
  label: string;
  value: number;
  color: string;
  onClick?: () => void;
}

export function SegmentedBar({ data }: { data: SegmentDatum[] }) {
  const [hover, setHover] = useState<string | null>(null);
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  return (
    <div className="segmented">
      <div className="segmented-bar" role="img" aria-label={data.map((d) => `${d.label}: ${d.value}`).join(", ")}>
        {data
          .filter((d) => d.value > 0)
          .map((d) => (
            <div
              key={d.key}
              className={`segment${hover && hover !== d.key ? " is-dim" : ""}`}
              style={{ flexGrow: d.value, background: d.color }}
              onMouseEnter={() => setHover(d.key)}
              onMouseLeave={() => setHover(null)}
              onClick={d.onClick}
              title={`${d.label}: ${formatNumber(d.value)} (${Math.round((d.value / total) * 100)}%)`}
            />
          ))}
      </div>
      <ul className="legend">
        {data.map((d) => (
          <li
            key={d.key}
            className={`${hover === d.key ? "is-hover" : ""}${d.onClick ? " clickable" : ""}`}
            onMouseEnter={() => setHover(d.key)}
            onMouseLeave={() => setHover(null)}
            onClick={d.onClick}
          >
            <span className="swatch" style={{ background: d.color }} />
            <span className="legend-label">{d.label}</span>
            <span className="legend-value">{formatNumber(d.value)}</span>
            <span className="legend-pct">{Math.round((d.value / total) * 100)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
