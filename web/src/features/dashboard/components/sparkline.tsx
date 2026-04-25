export interface SparklineProps {
  /** Ordered values, oldest first. */
  data: number[];
  /** Stroke color (CSS variable or hex). */
  color?: string;
  /** Pixel height of the SVG; width is fluid via viewBox. */
  height?: number;
}

export function Sparkline({
  data,
  color = "var(--accent-blue)",
  height = 32,
}: SparklineProps) {
  if (!data || data.length < 2) return null;
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const W = 100;
  const stepX = W / (data.length - 1);
  const pts = data.map(
    (v, i) =>
      [i * stepX, height - ((v - min) / range) * (height - 4) - 2] as const,
  );
  const linePath = pts
    .map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(2)},${p[1].toFixed(2)}`)
    .join(" ");
  const areaPath = `${linePath} L${W},${height} L0,${height} Z`;
  return (
    <svg
      viewBox={`0 0 ${W} ${height}`}
      preserveAspectRatio="none"
      width="100%"
      height={height}
      className="block"
      aria-hidden
    >
      <path d={areaPath} fill={color} opacity={0.12} />
      <path
        d={linePath}
        fill="none"
        stroke={color}
        strokeWidth={1.2}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
