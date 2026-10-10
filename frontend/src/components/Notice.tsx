import type { ReactNode } from 'react'
import { AlertIcon, InfoIcon } from './Icons'

export function Notice({
  tone,
  title,
  children,
  action,
}: {
  tone: 'error' | 'warn' | 'info'
  title?: string
  children: ReactNode
  action?: { label: string; onClick: () => void }
}) {
  return (
    <div className={`notice notice-${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      {tone === 'info' ? <InfoIcon /> : <AlertIcon />}
      <div>
        {title && <strong>{title}</strong>}
        <p>{children}</p>
        {action && (
          <button type="button" className="btn btn-quiet" onClick={action.onClick}>
            {action.label}
          </button>
        )}
      </div>
    </div>
  )
}
