<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import Globe from 'globe.gl'
import { feature } from 'topojson-client'

const props = defineProps({
  servers: {
    type: Array,
    default: () => []
  }
})

const router = useRouter()
const globeRef = ref(null)
const worldFeatureCount = ref(0)
const activeCount = ref(0)
const globeStatus = ref('Loading')
const debugLogs = ref([])
const showDebug = ref(false)

// Server → region code (like server.centos.hk: CN / JP)
const REGION_CODES = {
  oracle: 'JP',
  tencent: 'CN',
}

const ISO_TO_ID = { 'CN': '156', 'JP': '392' }
const FLAG_EMOJI = { 'CN': '🇨🇳', 'JP': '🇯🇵' }
const COORD_MAP = {
  'CN': [35.8617, 104.1954],
  'JP': [36.2048, 138.2529],
}

let globeInstance = null
let isActive = true
let countriesGeoJSON = null
let animFrame = null

function addLog(msg) {
  debugLogs.value.push(`[${new Date().toLocaleTimeString()}] ${msg}`)
  if (debugLogs.value.length > 50) debugLogs.value.shift()
}

function getFlagHTML(code) {
  return `<span class="flag-emoji">${FLAG_EMOJI[code] || '🏳️'}</span>`
}

// Load countries topojson → geojson (same source as server.centos.hk)
async function loadGeoJSON() {
  if (countriesGeoJSON) return countriesGeoJSON
  addLog('Loading GeoJSON...')
  globeStatus.value = 'Loading'
  try {
    const res = await fetch('/maps/countries-110m.json')
    const topo = await res.json()
    countriesGeoJSON = feature(topo, topo.objects.countries).features
    addLog(`Loaded ${countriesGeoJSON.length} countries`)
    return countriesGeoJSON
  } catch (e) {
    addLog(`Load failed: ${e.message}`)
    return []
  }
}

// Filter polygons for the server region codes
function filterPolygons(codes) {
  if (!countriesGeoJSON || codes.length === 0) return []
  const result = []
  codes.forEach(code => {
    const numericId = ISO_TO_ID[code]
    const feat = countriesGeoJSON.find(f => {
      const fid = String(f.id)
      const props = f.properties || {}
      if (numericId && fid === numericId) return true
      if (numericId && fid === numericId.padStart(3, '0')) return true
      if (numericId && fid.replace(/^0+/, '') === numericId) return true
      if (props.ISO_A2 === code || props.iso_a2 === code) return true
      return false
    })
    if (feat) result.push({ code, geometry: feat.geometry, id: feat.id })
  })
  addLog(`Matched polygons: ${result.length}/${codes.length}`)
  return result
}

// Build points/arcs from active server codes
function generateData() {
  const codes = [...new Set(props.servers
    .filter(s => s.latest && REGION_CODES[s.name])
    .map(s => REGION_CODES[s.name]))]

  if (codes.length === 0) return { points: [], arcs: [], codes }

  const centerCode = codes.includes('CN') ? 'CN' : codes[0]
  const centerCoord = COORD_MAP[centerCode]
  const points = []
  const arcs = []

  codes.forEach(code => {
    const coord = COORD_MAP[code]
    if (coord) {
      points.push({ code, lat: coord[0], lng: coord[1] })
      if (code !== centerCode) {
        arcs.push({
          startLat: centerCoord[0], startLng: centerCoord[1],
          endLat: coord[0], endLng: coord[1]
        })
      }
    }
  })
  return { points, arcs, codes }
}

async function initGlobe() {
  const container = globeRef.value
  if (!container) return

  const width = container.clientWidth
  const height = container.clientHeight
  if (width < 10 || height < 10) return

  await loadGeoJSON()

  const { points, arcs, codes } = generateData()
  if (codes.length === 0) {
    globeStatus.value = 'No Data'
    return
  }

  activeCount.value = codes.length
  const polygons = filterPolygons(codes)
  worldFeatureCount.value = countriesGeoJSON.length

  try {
    const globe = Globe()
    globe(container)
    globe.width(width)
    globe.height(height)

    // Same visual stack as server.centos.hk
    globe.backgroundImageUrl('/maps/night-sky.png')
    globe.globeImageUrl('/maps/earth-night.jpg')
    globe.bumpImageUrl('/maps/earth-topology.png')
    globe.atmosphereColor('rgba(26, 84, 144, 0.8)')
    globe.atmosphereAltitude(0.25)

    // Highlighted country polygons (cyan glow like server.centos.hk)
    if (polygons.length > 0) {
      globe.polygonsData(polygons)
      globe.polygonAltitude(0.01)
      globe.polygonCapColor(() => 'rgba(0, 200, 255, 0.4)')
      globe.polygonSideColor(() => 'rgba(0, 200, 255, 0.2)')
      globe.polygonStrokeColor(() => '#00ffff')

      let hoveredPolygon = null

      globe.onPolygonHover((polygon, prevPolygon) => {
        hoveredPolygon = polygon
        globe.controls().autoRotate = !polygon

        globe.polygonAltitude(d => d === polygon ? 0.06 : 0.01)
        globe.polygonCapColor(d => d === polygon
          ? 'rgba(0, 255, 255, 0.8)'
          : 'rgba(0, 200, 255, 0.4)')
        globe.polygonSideColor(d => d === polygon
          ? 'rgba(0, 255, 255, 0.6)'
          : 'rgba(0, 200, 255, 0.15)')
      })

      globe.onPolygonClick((polygon) => {
        if (!polygon || !polygon.code) return
        const coord = COORD_MAP[polygon.code]
        if (coord) {
          const currentRings = globe.ringsData() || []
          const clickRipples = []
          for (let i = 0; i < 3; i++) {
            clickRipples.push({
              lat: coord[0], lng: coord[1],
              maxRadius: 5 + i * 2,
              propagationSpeed: 3 + i,
              repeatPeriod: 0,
              altitude: 0.02
            })
          }
          globe.ringsData([...currentRings, ...clickRipples])
          setTimeout(() => {
            const rings = globe.ringsData() || []
            globe.ringsData(rings.filter(r => !clickRipples.includes(r)))
          }, 2000)
        }
      })

      globe.polygonLabel(d => {
        return `<div class="earth-label-card">
          <div class="flag-display">${getFlagHTML(d.code)}</div>
          <b>${d.code}</b>
        </div>`
      })
    }

    // Server location markers: pulsing rings + points (compact)
    globe.ringsData(points)
    globe.ringColor(() => '#00ffff')
    globe.ringMaxRadius(2.8)
    globe.ringPropagationSpeed(2)
    globe.ringRepeatPeriod(1000)

    globe.pointsData(points)
    globe.pointColor(() => '#00ffff')
    globe.pointAltitude(0.02)
    globe.pointRadius(0.3)

    // Flag + region-code labels (HTML overlays)
    globe.htmlElementsData(points)
    globe.htmlElement(d => {
      const el = document.createElement('div')
      el.innerHTML = `<div class="earth-label-card">
        <div class="flag-display">${getFlagHTML(d.code)}</div>
        <b>${d.code}</b>
      </div>`
      el.style.pointerEvents = 'none'
      return el
    })
    globe.htmlLat(d => d.lat)
    globe.htmlLng(d => d.lng)
    globe.htmlAltitude(0.05)

    // Connection arcs (cyan → magenta like server.centos.hk)
    globe.arcsData(arcs)
    globe.arcColor(() => ['rgba(0, 255, 255, 0.5)', 'rgba(255, 0, 255, 0.5)'])
    globe.arcDashLength(0.7)
    globe.arcDashGap(0.2)
    globe.arcDashAnimateTime(2000)
    globe.arcStroke(1.2)
    globe.arcAltitude(0.3)

    // Face Asia on load
    globe.pointOfView({
      lat: codes.includes('CN') ? 35 : 20,
      lng: codes.includes('CN') ? 110 : 0,
      altitude: 2.5
    })

    globe.controls().autoRotate = true
    globe.controls().autoRotateSpeed = 0.8
    globe.controls().enableZoom = true

    globeInstance = globe
    globeStatus.value = 'Active'
    addLog(`Globe ready! ${codes.length} regions, ${polygons.length} polygons`)

  } catch (error) {
    globeStatus.value = 'Error'
    addLog(`Error: ${error.message}`)
    console.error(error)
  }
}

function updateGlobe() {
  if (!globeInstance) return
  const { points, arcs, codes } = generateData()
  if (codes.length === 0) return
  activeCount.value = codes.length

  const polygons = filterPolygons(codes)
  if (polygons.length > 0) globeInstance.polygonsData(polygons)
  globeInstance.ringsData(points)
  globeInstance.pointsData(points)
  globeInstance.htmlElementsData(points)
  globeInstance.arcsData(arcs)
}

onMounted(async () => {
  await initGlobe()
  // Retry if data wasn't ready yet (servers still loading)
  if (!globeInstance) {
    const retry = setInterval(async () => {
      await initGlobe()
      if (globeInstance) clearInterval(retry)
    }, 2000)
    setTimeout(() => clearInterval(retry), 30000)
  }
  // Poll for server changes
  animFrame = setInterval(() => updateGlobe(), 30000)
})

onUnmounted(() => {
  if (animFrame) clearInterval(animFrame)
  if (globeInstance) {
    globeInstance._destructor && globeInstance._destructor()
    globeInstance = null
  }
})
</script>

<template>
  <div class="globe-page">
    <div ref="globeRef" class="globe-render-area"></div>

    <div class="earth-header">
      <div class="earth-title">DFshmily /// LINKED</div>
      <button class="disconnect-btn" @click="router.push('/')">DISCONNECT</button>
    </div>

    <div class="earth-stats">
      <div>Detected <span>{{ activeCount }}</span> regions</div>
      <div>Polygons <span>{{ worldFeatureCount }}</span> loaded</div>
      <div>Status: <span style="color:#00ffff">{{ globeStatus }}</span></div>
      <div class="toggle-debug" @click="showDebug = !showDebug">[Debug]</div>
    </div>

    <div v-if="showDebug" class="debug-panel">
      <div v-for="(log, i) in debugLogs" :key="i">{{ log }}</div>
    </div>
  </div>
</template>

<style scoped>
.globe-page {
  position: relative;
  width: 100%;
  height: 100vh;
  background: linear-gradient(135deg, rgba(0, 5, 15, 0.98), rgba(0, 10, 25, 0.98));
  overflow: hidden;
}

.globe-render-area {
  width: 100%;
  height: 100%;
  cursor: grab;
}
.globe-render-area:active { cursor: grabbing; }

.earth-header {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  padding: 20px 30px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  z-index: 10;
  background: linear-gradient(180deg, rgba(0,0,0,0.95) 0%, transparent 100%);
  pointer-events: none;
  backdrop-filter: blur(10px);
  box-sizing: border-box;
}

.earth-title {
  color: #00ffff;
  font-family: 'Segoe UI', monospace;
  letter-spacing: 4px;
  font-weight: 700;
  font-size: 20px;
  text-shadow: 0 0 15px rgba(0, 255, 255, 0.8);
  pointer-events: auto;
}

.disconnect-btn {
  pointer-events: auto;
  color: #fff;
  background: linear-gradient(135deg, rgba(0, 100, 150, 0.3), rgba(0, 50, 100, 0.3));
  border: 1px solid rgba(0, 255, 255, 0.6);
  padding: 10px 24px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.3s;
  font-family: 'Consolas', monospace;
  border-radius: 6px;
}
.disconnect-btn:hover {
  background: linear-gradient(135deg, rgba(0, 255, 255, 0.4), rgba(0, 200, 255, 0.4));
  box-shadow: 0 0 20px rgba(0, 255, 255, 0.6);
}

.earth-stats {
  position: absolute;
  top: 80px;
  left: 30px;
  color: rgba(255, 255, 255, 0.95);
  font-family: 'Consolas', monospace;
  font-size: 13px;
  z-index: 10;
  background: rgba(0, 20, 40, 0.85);
  padding: 15px 20px;
  border: 1px solid rgba(0, 255, 255, 0.5);
  border-radius: 6px;
  backdrop-filter: blur(10px);
}
.earth-stats div { margin: 4px 0; }
.earth-stats span { color: #00ffff; font-weight: bold; }
.toggle-debug { opacity: 0.7; cursor: pointer; color: #4da3ff; }

.debug-panel {
  position: absolute;
  top: 220px;
  left: 30px;
  z-index: 10;
  color: #00ffff;
  font-family: 'Consolas', monospace;
  font-size: 11px;
  background: rgba(0, 20, 40, 0.9);
  border: 1px solid rgba(0, 255, 255, 0.3);
  border-radius: 6px;
  padding: 10px 14px;
  max-height: 40vh;
  overflow-y: auto;
  line-height: 1.6;
}

.globe-legend,
.globe-tip,
.legend-item,
.legend-dot,
.legend-code,
.legend-name { display: none; }

/* Globe.gl HTML label styling — compact */
:deep(.earth-label-card) {
  background: linear-gradient(135deg, rgba(0, 20, 40, 0.98), rgba(0, 10, 30, 0.98)) !important;
  border: 1.5px solid #00ffff !important;
  color: #fff !important;
  padding: 5px 10px !important;
  border-radius: 6px !important;
  font-size: 12px !important;
  display: flex !important;
  align-items: center !important;
  gap: 6px !important;
  box-shadow: 0 0 15px rgba(0, 255, 255, 0.5) !important;
  white-space: nowrap !important;
  font-family: 'Consolas', monospace !important;
  line-height: 1 !important;
  pointer-events: none !important;
  transform: translate(-50%, -50%);
}
:deep(.earth-label-card .flag-display) {
  display: flex !important;
  align-items: center !important;
  min-width: 18px !important;
}
:deep(.earth-label-card .flag-emoji) {
  font-size: 18px !important;
  font-family: "Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji", sans-serif !important;
}
:deep(.earth-label-card b) {
  color: #00ffff !important;
  text-shadow: 0 0 8px rgba(0, 255, 255, 0.7) !important;
}

@media (max-width: 768px) {
  .earth-header { padding: 14px 16px; }
  .earth-title { font-size: 15px; letter-spacing: 2px; }
  .disconnect-btn { padding: 8px 16px; font-size: 12px; }
  .earth-stats { top: 64px; left: 14px; font-size: 11px; padding: 10px 14px; }
  .debug-panel { top: 190px; left: 14px; font-size: 10px; }
}
</style>
