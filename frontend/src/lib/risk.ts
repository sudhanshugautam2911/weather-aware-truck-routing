import type { RiskKey } from '../types'

// Ordered Low -> No Travel. Validated for colour-blind separation (all pairs);
// every use also carries a text label, so colour is never the only signal.
export const RISK_LEVELS: { key: RiskKey; label: string; color: string }[] = [
  { key: 'low', label: 'Low', color: '#5fb882' },
  { key: 'moderate', label: 'Moderate', color: '#f0c12c' },
  { key: 'high', label: 'High', color: '#ee7d24' },
  { key: 'severe', label: 'Severe', color: '#cf2f36' },
  { key: 'no_travel', label: 'No Travel', color: '#5c1a64' },
]

export const riskIndex = (key: RiskKey) => RISK_LEVELS.findIndex((r) => r.key === key)
export const riskLabel = (key: RiskKey) => RISK_LEVELS[riskIndex(key)].label
export const riskColor = (key: RiskKey) => RISK_LEVELS[riskIndex(key)].color
