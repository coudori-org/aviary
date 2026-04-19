/**
 * AuroraBackdrop — fixed-position coloured bleed that sits behind every
 * app surface. Three blobs drifting at different rates in the aurora-A
 * palette (violet → pink → amber) plus a cyan accent.
 *
 * Rendered once at the root layout; glass surfaces pick up the colour
 * through backdrop-blur. Pointer-events:none so it never intercepts
 * clicks.
 */
export function AuroraBackdrop() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-0 overflow-hidden"
    >
      <div className="aurora-blob aurora-blob-violet" />
      <div className="aurora-blob aurora-blob-pink" />
      <div className="aurora-blob aurora-blob-cyan" />
      {/* Very faint grain to break banding across the huge gradients. */}
      <div
        className="absolute inset-0 opacity-[0.03] mix-blend-overlay"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.55'/%3E%3C/svg%3E\")",
        }}
      />
    </div>
  );
}
