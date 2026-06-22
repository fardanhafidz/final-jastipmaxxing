/**
 * JASTIPMAXXING — Frontend Logic
 * Maps page: point management, POI search, route optimization, result display.
 */

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let map;
let basecamp = null;
let pickups = [];
let deliveries = [];
let routeLayer = null;
let resultMarkers = [];
let idCounter = 0;
let currentMode = 'basecamp';

const COLORS = { basecamp: '#22C55E', pickup: '#3B82F6', delivery: '#F97316' };

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
    if (!document.getElementById('map')) return; // only init on maps page
    initMap();
    bindEvents();
    checkHistoryView();
});

function initMap() {
    map = L.map('map', { zoomControl: false }).setView([-7.2815, 112.7950], 14);
    L.control.zoom({ position: 'bottomright' }).addTo(map);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap',
        maxZoom: 19,
    }).addTo(map);

    map.on('click', onMapClick);
}

function bindEvents() {
    // Mode buttons
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentMode = btn.dataset.mode;
        });
    });

    // Optimize button
    document.getElementById('btnOptimize').addEventListener('click', runOptimize);

    // POI search
    let searchTimer;
    let hideTimer;
    const poiSearch = document.getElementById('poiSearch');
    const floatSearch = document.getElementById('floatSearch');

    poiSearch.addEventListener('input', () => {
        clearTimeout(searchTimer);
        clearTimeout(hideTimer);
        showSearchResults();
        searchTimer = setTimeout(searchPoi, 350);
    });
    poiSearch.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); searchPoi(); }
    });
    poiSearch.addEventListener('focus', () => {
        clearTimeout(hideTimer);
        showSearchResults();
    });
    // Auto-hide results after 2s of inactivity
    document.addEventListener('click', (e) => {
        if (floatSearch && !floatSearch.contains(e.target)) {
            startHideTimer();
        }
    });
    document.getElementById('poiCategory').addEventListener('change', () => {
        clearTimeout(hideTimer);
        showSearchResults();
        searchPoi();
    });

    // Sidebar toggle (mobile + desktop collapsed state)
    const toggle = document.getElementById('sidebarToggle');
    const sidebar = document.getElementById('sidebar');
    if (toggle && sidebar) {
        toggle.addEventListener('click', () => {
            if (window.innerWidth <= 768) {
                sidebar.classList.toggle('open');
            } else {
                sidebar.classList.remove('collapsed');
                toggle.style.display = 'none';
                setTimeout(() => map.invalidateSize(), 350);
            }
        });
    }

    // Sidebar collapse (desktop)
    const collapseBtn = document.getElementById('sidebarCollapse');
    if (collapseBtn && sidebar) {
        collapseBtn.addEventListener('click', () => {
            sidebar.classList.toggle('collapsed');
            // Show mobile toggle when collapsed on desktop
            const mobileToggle = document.getElementById('sidebarToggle');
            if (window.innerWidth > 768 && mobileToggle) {
                mobileToggle.style.display = sidebar.classList.contains('collapsed') ? 'flex' : 'none';
            }
            // Let Leaflet recalculate map size
            setTimeout(() => map.invalidateSize(), 350);
        });
    }

    // Reset route button
    document.getElementById('btnReset').addEventListener('click', () => {
        clearResults();
    });
}

// Check if we came from history with route data
function checkHistoryView() {
    const saved = sessionStorage.getItem('viewRoute');
    if (!saved) return;
    sessionStorage.removeItem('viewRoute');
    try {
        const data = JSON.parse(saved);
        displayResults(data);
    } catch (e) { console.error('Failed to load history route:', e); }
}

// ---------------------------------------------------------------------------
// Map click — add point
// ---------------------------------------------------------------------------
function onMapClick(e) {
    const lat = e.latlng.lat;
    const lng = e.latlng.lng;
    const id = 'pt_' + (++idCounter);

    if (currentMode === 'basecamp') {
        if (basecamp) map.removeLayer(basecamp.marker);
        const marker = createMarker(lat, lng, 'BC', 'basecamp', 'Basecamp');
        basecamp = { id, name: 'Basecamp', lat, lng, marker };
    } else if (currentMode === 'pickup') {
        const name = 'Pickup ' + (pickups.length + 1);
        const marker = createMarker(lat, lng, 'P' + (pickups.length + 1), 'pickup', name);
        pickups.push({ id, name, lat, lng, marker });
    } else if (currentMode === 'delivery') {
        if (pickups.length === 0) {
            showNotification('Add a pickup point first!', 'warning');
            return;
        }
        const owner = pickups[0]; // default to first pickup
        const name = 'Delivery ' + (deliveries.length + 1);
        const marker = createMarker(lat, lng, 'D' + (deliveries.length + 1), 'delivery', name);
        deliveries.push({ id, name, lat, lng, marker, ownerId: owner.id });
    }

    updatePointsList();
}

// ---------------------------------------------------------------------------
// Markers
// ---------------------------------------------------------------------------
function createMarker(lat, lng, label, type, tooltip) {
    const icon = L.divIcon({
        className: '',
        html: `<div class="map-marker ${type}">${label}</div>`,
        iconSize: [32, 32],
        iconAnchor: [16, 16],
    });
    const marker = L.marker([lat, lng], { icon }).addTo(map);
    marker.bindTooltip(tooltip, { direction: 'top', offset: [0, -18] });
    return marker;
}

// ---------------------------------------------------------------------------
// Points list
// ---------------------------------------------------------------------------
function updatePointsList() {
    const container = document.getElementById('pointsList');
    container.innerHTML = '';

    const total = (basecamp ? 1 : 0) + pickups.length + deliveries.length;
    document.getElementById('pointCount').textContent = total + ' TOTAL';

    // Enable/disable optimize button
    const canOptimize = basecamp && pickups.length > 0 &&
        pickups.every(p => deliveries.some(d => d.ownerId === p.id));
    document.getElementById('btnOptimize').disabled = !canOptimize;

    if (basecamp) {
        container.appendChild(createPointCard('basecamp', 'BC', basecamp.name, 'Basecamp', basecamp.id));
    }
    pickups.forEach((p, i) => {
        container.appendChild(createPointCard('pickup', 'P' + (i + 1), p.name, 'Pickup', p.id));
    });
    deliveries.forEach((d, i) => {
        const owner = pickups.find(p => p.id === d.ownerId);
        const meta = owner ? 'Delivery from ' + owner.name : 'Delivery';
        container.appendChild(createPointCard('delivery', 'D' + (i + 1), d.name, meta, d.id));
    });
}

function createPointCard(type, badge, name, meta, id) {
    const div = document.createElement('div');
    div.className = 'point-item';
    div.innerHTML = `
        <div class="point-icon ${type}">${badge}</div>
        <div class="point-info">
            <div class="point-name">${name}</div>
            <div class="point-meta">${meta}</div>
        </div>
        <button class="point-remove" data-type="${type}" data-id="${id}" title="Remove">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
    `;
    div.querySelector('.point-remove').addEventListener('click', (e) => {
        e.stopPropagation();
        removePoint(type, id);
    });
    // Click to fly to point
    div.addEventListener('click', () => {
        const p = type === 'basecamp' ? basecamp :
                  type === 'pickup' ? pickups.find(x => x.id === id) :
                  deliveries.find(x => x.id === id);
        if (p) map.flyTo([p.lat, p.lng], 16, { duration: 0.5 });
    });
    return div;
}

function removePoint(type, id) {
    if (type === 'basecamp' && basecamp?.id === id) {
        map.removeLayer(basecamp.marker);
        basecamp = null;
    } else if (type === 'pickup') {
        const idx = pickups.findIndex(p => p.id === id);
        if (idx !== -1) {
            map.removeLayer(pickups[idx].marker);
            pickups.splice(idx, 1);
            // Remove associated deliveries
            deliveries.filter(d => d.ownerId === id).forEach(d => map.removeLayer(d.marker));
            deliveries = deliveries.filter(d => d.ownerId !== id);
        }
    } else if (type === 'delivery') {
        const idx = deliveries.findIndex(d => d.id === id);
        if (idx !== -1) {
            map.removeLayer(deliveries[idx].marker);
            deliveries.splice(idx, 1);
        }
    }
    updatePointsList();
}

// ---------------------------------------------------------------------------
// POI Search
// ---------------------------------------------------------------------------
function showSearchResults() {
    const floatSearch = document.getElementById('floatSearch');
    if (floatSearch) floatSearch.classList.remove('collapsed');
}

function startHideTimer() {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => {
        const floatSearch = document.getElementById('floatSearch');
        const poiSearch = document.getElementById('poiSearch');
        // Only hide if search input is not focused
        if (floatSearch && document.activeElement !== poiSearch) {
            floatSearch.classList.add('collapsed');
        }
    }, 2000);
}

async function searchPoi() {
    const query = document.getElementById('poiSearch').value.trim();
    const category = document.getElementById('poiCategory').value;
    const container = document.getElementById('poiResults');

    const params = new URLSearchParams();
    if (query) params.set('q', query);
    if (category) params.set('category', category);

    try {
        const resp = await fetch('/poi-list?' + params.toString());
        const data = await resp.json();
        container.innerHTML = '';

        data.forEach(poi => {
            const div = document.createElement('div');
            div.className = 'poi-result-item';

            const tagLabel = poi.tag ? poi.tag.replace(/_/g, ' ') : '';
            div.innerHTML = `
                <div class="poi-result-info">
                    <div class="poi-result-name">${poi.name}</div>
                    <div class="poi-result-tag">${tagLabel}</div>
                </div>
                <div class="poi-add-group">
                    <button class="poi-add-btn poi-add-bc" title="Add as Basecamp">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
                    </button>
                    <button class="poi-add-btn poi-add-pickup" title="Add as Pickup">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="1" y="3" width="15" height="13" rx="2"/><polyline points="16 8 20 8 23 11 23 16 1 16"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>
                    </button>
                    <button class="poi-add-btn poi-add-delivery" title="Add as Delivery">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                    </button>
                </div>
            `;

            // Wire up each button
            const btns = div.querySelectorAll('.poi-add-btn');
            btns[0].addEventListener('click', (e) => { e.stopPropagation(); addPoiAs(poi, 'basecamp'); });
            btns[1].addEventListener('click', (e) => { e.stopPropagation(); addPoiAs(poi, 'pickup'); });
            btns[2].addEventListener('click', (e) => { e.stopPropagation(); addPoiAs(poi, 'delivery'); });

            container.appendChild(div);
        });
    } catch (err) {
        console.error('POI search failed:', err);
    }
}

function addPoi(poi) {
    addPoiAs(poi, currentMode);
}

function addPoiAs(poi, type) {
    const id = 'pt_' + (++idCounter);
    const lat = poi.lat, lng = poi.lng, name = poi.name;

    if (type === 'basecamp') {
        if (basecamp) map.removeLayer(basecamp.marker);
        const marker = createMarker(lat, lng, 'BC', 'basecamp', name);
        basecamp = { id, name, lat, lng, marker };
    } else if (type === 'pickup') {
        const marker = createMarker(lat, lng, 'P' + (pickups.length + 1), 'pickup', name);
        pickups.push({ id, name, lat, lng, marker });
    } else if (type === 'delivery') {
        if (pickups.length === 0) {
            showNotification('Add a pickup point first!', 'warning');
            return;
        }
        const owner = pickups[0];
        const marker = createMarker(lat, lng, 'D' + (deliveries.length + 1), 'delivery', name);
        deliveries.push({ id, name, lat, lng, marker, ownerId: owner.id });
    }

    map.flyTo([lat, lng], Math.max(map.getZoom(), 14), { duration: 0.5 });
    updatePointsList();
}

// ---------------------------------------------------------------------------
// Optimize
// ---------------------------------------------------------------------------
async function runOptimize() {
    if (!basecamp) return showNotification('Set a basecamp first!');
    if (pickups.length === 0) return showNotification('Add at least 1 pickup!');
    for (const p of pickups) {
        if (!deliveries.some(d => d.ownerId === p.id)) {
            return showNotification(`Pickup "${p.name}" needs at least 1 delivery target!`);
        }
    }

    const deliveryMap = {};
    pickups.forEach(p => { deliveryMap[p.id] = []; });
    deliveries.forEach(d => {
        deliveryMap[d.ownerId].push({ id: d.id, name: d.name, lat: d.lat, lng: d.lng });
    });

    const body = {
        basecamp: { name: basecamp.name, lat: basecamp.lat, lng: basecamp.lng },
        pickups: pickups.map(p => ({ id: p.id, name: p.name, lat: p.lat, lng: p.lng })),
        delivery_map: deliveryMap,
    };

    showLoading(true);
    try {
        const resp = await fetch('/optimize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) {
            const err = await resp.json();
            showNotification(err.error || 'Optimization failed');
            return;
        }
        const data = await resp.json();
        displayResults(data);
    } catch (err) {
        showNotification('Request failed: ' + err.message);
    } finally {
        showLoading(false);
    }
}

// ---------------------------------------------------------------------------
// Results display
// ---------------------------------------------------------------------------
function displayResults(data) {
    clearResults();

    // Metrics (inside steps panel footer)
    const distKm = data.best_dist_km.toFixed(1);
    document.getElementById('metricDist').textContent = distKm + ' km';
    const estMinutes = Math.round((data.best_dist_km / 25) * 60);
    const hrs = Math.floor(estMinutes / 60);
    const mins = estMinutes % 60;
    document.getElementById('metricTime').textContent = hrs > 0 ? `${hrs}h ${mins}m` : `${mins}m`;

    // Polyline
    routeLayer = L.polyline(data.polyline, {
        color: '#3B82F6',
        weight: 5,
        opacity: 0.85,
        lineJoin: 'round',
    }).addTo(map);

    // Result markers
    data.route.forEach(stop => {
        if (stop.type === 'basecamp_return') return;
        const marker = createMarker(stop.lat, stop.lng, String(stop.step), stop.type,
            `#${stop.step} ${stop.name}\n${stop.note}`);
        resultMarkers.push(marker);
    });

    map.fitBounds(routeLayer.getBounds(), { padding: [60, 60] });

    // Show steps panel, hide sidebar (only 1 window visible)
    document.getElementById('sidebar').style.display = 'none';
    document.getElementById('stepsPanel').style.display = 'block';
    document.getElementById('btnOptimize').style.display = 'none';

    const DESC = {
        basecamp: 'Start & return point',
        pickup: 'Pick up your order here',
        delivery: 'Drop your food here',
        basecamp_return: 'Route complete',
    };

    const table = document.getElementById('stopsTable');
    table.innerHTML = '';
    data.route.forEach(stop => {
        const row = document.createElement('div');
        row.className = 'stop-row';
        const isReturn = stop.type === 'basecamp_return';
        row.innerHTML = `
            <div class="stop-step ${isReturn ? 'basecamp_return' : stop.type}">${stop.step}</div>
            <div class="stop-text">
                <span class="stop-name">${stop.name}</span>
                <span class="stop-note">${DESC[stop.type] || ''}</span>
            </div>
        `;
        row.addEventListener('click', () => {
            map.flyTo([stop.lat, stop.lng], 16, { duration: 0.5 });
        });
        table.appendChild(row);
    });

    // Close sidebar on mobile after route
    if (window.innerWidth <= 768) {
        document.getElementById('sidebar').classList.remove('open');
    }
}

function clearResults() {
    if (routeLayer) { map.removeLayer(routeLayer); routeLayer = null; }
    resultMarkers.forEach(m => map.removeLayer(m));
    resultMarkers = [];
    document.getElementById('stopsTable').innerHTML = '';

    // Restore sidebar to edit mode
    document.getElementById('sidebar').style.display = '';
    document.getElementById('stepsPanel').style.display = 'none';
    document.getElementById('btnOptimize').style.display = '';
    setTimeout(() => map.invalidateSize(), 50);
}

// ---------------------------------------------------------------------------
// Loading
// ---------------------------------------------------------------------------
function showLoading(show) {
    document.getElementById('loadingOverlay').style.display = show ? 'flex' : 'none';
}

// ---------------------------------------------------------------------------
// Notification toast
// ---------------------------------------------------------------------------
function showNotification(msg, type = 'error') {
    const toast = document.createElement('div');
    toast.style.cssText = `
        position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
        padding: 12px 24px; border-radius: 8px; font-size: 14px; font-weight: 500;
        z-index: 9999; color: #fff; box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        animation: fadeInUp 0.3s ease;
        background: ${type === 'warning' ? '#F97316' : '#EF4444'};
    `;
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 3000);
}

// Fade-in animation
const style = document.createElement('style');
style.textContent = '@keyframes fadeInUp{from{opacity:0;transform:translateX(-50%) translateY(10px)}to{opacity:1;transform:translateX(-50%) translateY(0)}}';
document.head.appendChild(style);
