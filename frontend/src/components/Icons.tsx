const base = { width: 16, height: 16, viewBox: '0 0 16 16', fill: 'none', 'aria-hidden': true } as const

export const AlertIcon = () => (
  <svg {...base}>
    <path d="M8 1.5 15 14H1z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    <path d="M8 6v3.5M8 11.5v.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
  </svg>
)

export const InfoIcon = () => (
  <svg {...base}>
    <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.5" />
    <path d="M8 7v4.5M8 4.5V5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
  </svg>
)

export const PlayIcon = () => (
  <svg {...base}>
    <path d="M4.5 2.5v11l9-5.5z" fill="currentColor" />
  </svg>
)

export const PauseIcon = () => (
  <svg {...base}>
    <path d="M4 2.5h3v11H4zM9.5 2.5h3v11h-3z" fill="currentColor" />
  </svg>
)
