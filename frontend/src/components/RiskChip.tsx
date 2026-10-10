import { riskColor, riskLabel } from '../lib/risk'
import type { RiskKey } from '../types'

export function RiskChip({ level }: { level: RiskKey }) {
  return (
    <span className="risk-chip">
      <i className="swatch" style={{ background: riskColor(level) }} />
      {riskLabel(level)}
    </span>
  )
}
