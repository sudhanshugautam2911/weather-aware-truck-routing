/** A route letter on a highway-shield shape. Recommended routes wear sign green. */
export function Shield({ id, recommended, size = 30 }: { id: string; recommended?: boolean; size?: number }) {
  const fill = recommended ? '#0f5e3f' : '#1b2026'
  return (
    <span className="shield" style={{ width: size, height: size * 1.08, fontSize: size * 0.48 }} aria-hidden="true">
      <svg viewBox="0 0 30 32.4" width={size} height={size * 1.08}>
        <path
          d="M2 2h26v13.5c0 8.2-6.2 12.8-13 15.4C8.2 28.3 2 23.7 2 15.5z"
          fill={fill}
          stroke="#fff"
          strokeWidth="1.6"
        />
        <path d="M3.5 3.5h23v5h-23z" fill="#fff" opacity="0.18" />
      </svg>
      <span>{id}</span>
    </span>
  )
}
