import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/overpass'
import { setWorkerUrl } from 'maplibre-gl'
// The worker is a self-contained file; bundle it as an asset so the map works
// in both the dev server and the production build.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import 'maplibre-gl/dist/maplibre-gl.css'
import './styles.css'
import App from './App'

setWorkerUrl(workerUrl)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
