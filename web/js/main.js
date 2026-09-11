/* Application entry point: owns the interaction state and keeps the map,
 * stats table and chart in step with it.
 *
 * All computation happens here in the browser — the server only ever serves
 * static files. */

import { loadMeta, loadType, isLoaded, price, growth, growthByArea, priceByArea, annualise, coverage } from './data.js';
import { createMap } from './map-canvas.js';
import { createChart } from './chart.js';

const DEFAULT_AREA_CODE = 'K02000001';   // United Kingdom
const DEFAULT_START = '2005-01';
const THUMB = 16;                        // matches the slider thumb in style.css
const CTA_SEEN_KEY = 'ukhp.map-cta-seen';

const el = {
	startSlider: document.getElementById('start-month'),
	endSlider: document.getElementById('end-month'),
	startLabel: document.getElementById('start-label'),
	endLabel: document.getElementById('end-label'),
	rangeFill: document.getElementById('range-fill'),
	houseType: document.getElementById('house-type'),
	priceBasis: document.getElementById('price-basis'),
	areaSelect: document.getElementById('area-select'),
	mapModes: document.querySelectorAll('input[name="map-mode"]'),
	mapEl: document.getElementById('map'),
	headline: document.getElementById('headline'),
	headlineValue: document.getElementById('headline-value'),
	headlineLabel: document.getElementById('headline-label'),
	stats: document.querySelector('#stats tbody'),
	chart: document.getElementById('chart'),
	chartTitle: document.getElementById('chart-title'),
	mapStatus: document.getElementById('map-status'),
	mapCta: document.getElementById('map-cta'),
	headlineArea: document.getElementById('headline-area'),
	areaPanel: document.getElementById('area-panel'),
	legend: document.getElementById('legend'),
	legendTitle: document.getElementById('legend-title'),
	legendRamp: document.querySelector('.legend-ramp'),
	legendMin: document.getElementById('legend-min'),
	legendMax: document.getElementById('legend-max'),
	topbarMeta: document.getElementById('topbar-meta'),
	basisNote: document.getElementById('basis-note'),
};

// mapMode colours the map by change over the range ('change') or by the average
// price in the end month ('price'). It moves nothing else: the headline, stats
// and chart always describe the selected area over the whole range.
const state = { start: 0, end: 0, type: 0, real: true, area: 0, mapMode: 'change' };

let meta = null;
let mapView = null;
let chart = null;
let frame = null;

function formatPercent(value, digits = 1) {
	if (!Number.isFinite(value)) return '—';
	return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}%`;
}

function typeLabel(type) {
	return type === 'SemiDetached' ? 'Semi-detached' : type;
}

function toneOf(value) {
	if (!Number.isFinite(value)) return 'none';
	return value >= 0 ? 'up' : 'down';
}

function basisLabel() {
	const measure = state.mapMode === 'price' ? 'average price' : 'change';
	return `${state.real ? 'Real' : 'Nominal'} ${measure} · ${typeLabel(meta.types[state.type])}`;
}

/* Compact in the legend, where there is room for about six characters either
 * side of the ramp, and in full in the tooltip, where the exact figure is the
 * whole point of hovering. */
function formatMoney(value, compact = false) {
	if (!Number.isFinite(value)) return '—';
	if (!compact) return `£${Math.round(value).toLocaleString('en-GB')}`;
	if (value >= 1e6) return `£${(value / 1e6).toFixed(1)}m`;
	if (value >= 1e3) return `£${Math.round(value / 1e3)}k`;
	return `£${Math.round(value)}`;
}

/* Storage is unavailable in some privacy modes and throws rather than returning
 * nothing, and a prompt shown twice is a far smaller problem than a page that
 * fails to start. */
function ctaAlreadySeen() {
	try {
		return localStorage.getItem(CTA_SEEN_KEY) === '1';
	} catch (error) {
		return false;
	}
}

function retireCta() {
	if (el.mapCta.hidden) return;
	el.mapCta.hidden = true;
	try {
		localStorage.setItem(CTA_SEEN_KEY, '1');
	} catch (error) {
		/* it simply reappears next visit */
	}
}

/* ---------- rendering ---------- */

function renderRange() {
	el.startLabel.textContent = meta.monthLabels[state.start];
	el.endLabel.textContent = meta.monthLabels[state.end];

	// A native range thumb travels between its own half-widths, so the fill is
	// offset to match rather than sitting at a naive percentage.
	const last = Math.max(meta.nMonths - 1, 1);
	const from = (state.start / last) * 100;
	const to = (state.end / last) * 100;
	const span = to - from;

	el.rangeFill.style.left = `calc(${from}% + ${(0.5 - from / 100) * THUMB}px)`;
	el.rangeFill.style.width = `calc(${span}% - ${(span / 100) * THUMB}px)`;
}

function renderMap() {
	const showPrice = state.mapMode === 'price';
	const values = showPrice
		? priceByArea(state.type, state.end, state.real)
		: growthByArea(state.type, state.start, state.end, state.real);

	const domain = mapView.setValues(values, state.mapMode);

	// Named on the legend as well as in the panel, so the map still says what
	// it is measuring when it is the only thing on screen
	el.legendTitle.textContent = basisLabel();

	if (domain !== null) {
		// Both ends of both ramps are trimmed rather than true extremes, so the
		// labels read as the scale they are, not as the range of the data.
		el.legend.hidden = false;
		el.legendRamp.classList.toggle('is-sequential', showPrice);
		el.legendMin.textContent = showPrice
			? formatMoney(domain.lo, true)
			: formatPercent(domain.lo, 0);
		el.legendMax.textContent = showPrice
			? formatMoney(domain.hi, true)
			: formatPercent(domain.hi, 0);
	}
}

function renderHeadline() {
	const loaded = isLoaded(state.type);
	const total = loaded ? growth(state.type, state.area, state.start, state.end, state.real) : NaN;

	el.headlineValue.className = `headline-value ${toneOf(total)}`;
	el.headlineArea.textContent = meta.areas[state.area].n;

	const basis = state.real ? 'Real' : 'Nominal';
	const period = `${meta.monthLabels[state.start]} to ${meta.monthLabels[state.end]}`;

	if (Number.isFinite(total)) {
		el.headlineValue.textContent = formatPercent(total);
		el.headlineLabel.textContent =
			`${basis} change · ${typeLabel(meta.types[state.type])} · ${period}`;
		return;
	}

	// Explain the gap rather than showing a bare dash: Scotland and Northern
	// Ireland records begin well after those for England and Wales.
	el.headlineValue.textContent = loaded ? 'No data for this period' : 'Loading…';

	const span = loaded ? coverage(state.type, state.area) : null;
	el.headlineLabel.textContent = span
		? `${meta.areas[state.area].n} records run from ${meta.monthLabels[span.first]} to ${meta.monthLabels[span.last]}`
		: `${basis} change · ${typeLabel(meta.types[state.type])} · ${period}`;
}

function renderStats() {
	el.stats.innerHTML = meta.types.map((type, i) => {
		const loaded = isLoaded(i);
		const total = loaded ? growth(i, state.area, state.start, state.end, state.real) : NaN;
		const perYear = loaded ? annualise(total, state.start, state.end) : NaN;
		const tone = toneOf(total);
		const cell = (value) => (loaded ? formatPercent(value) : '…');

		return `<tr>
			<td>${typeLabel(type)}</td>
			<td class="${tone}">${cell(total)}</td>
			<td class="${tone}">${cell(perYear)}</td>
		</tr>`;
	}).join('');
}

function renderChart() {
	const length = state.end - state.start + 1;
	const xs = meta.monthTimes.slice(state.start, state.end + 1);

	const series = meta.types.map((type, i) => {
		const column = new Array(length).fill(null);
		if (!isLoaded(i)) return column;

		for (let month = state.start; month <= state.end; month++) {
			const value = price(i, state.area, month, state.real);
			column[month - state.start] = Number.isFinite(value) ? value : null;
		}
		return column;
	});

	chart.update([xs, ...series]);

	el.chartTitle.textContent =
		`Average ${state.real ? 'real' : 'nominal'} price · ${meta.areas[state.area].n}`;
}

/* Coalesce bursts of slider events into one paint. requestAnimationFrame is
 * paused in background tabs, so fall back to a timer when the page is hidden —
 * otherwise a site opened in a new tab renders nothing until it is focused. */
function schedule(work) {
	return document.hidden ? setTimeout(work, 0) : requestAnimationFrame(work);
}

function render() {
	if (frame) return;
	frame = schedule(() => {
		frame = null;
		renderRange();
		renderMap();
		renderHeadline();
		renderStats();
		renderChart();
	});
}

function renderAreaDetail() {
	renderHeadline();
	renderStats();
	renderChart();
}

/* The background housing types resolve independently, so their redraws are
 * coalesced the same way slider bursts are - two landing in one frame should
 * cost one repaint of the chart, not two. */
let detailFrame = null;

function scheduleAreaDetail() {
	if (detailFrame) return;
	detailFrame = schedule(() => {
		detailFrame = null;
		renderAreaDetail();
	});
}

/* ---------- interaction ---------- */

// The map is built before meta.json is awaited, so both of these — the only
// two entry points the map itself calls — can in principle fire before there
// is any metadata to read. In practice meta.json is long since in by the time
// the boundaries are loaded and hoverable, but neither should depend on that.

function setArea(area, fromMap = false) {
	if (!meta) return;
	state.area = area;
	el.areaSelect.value = String(area);
	// National and regional series have no polygon to outline
	mapView.setSelected(area < meta.geoAreas ? area : null);
	renderAreaDetail();

	if (!fromMap) return;

	retireCta();

	// On a phone the reading is below the map, so without this the tap can
	// look like it did nothing. The headline is the target rather than the
	// whole panel: the panel is taller than a phone screen, so scrolling that
	// into view would align its top and carry the map - and the area just
	// selected - clean off the screen. 'nearest' then does nothing at all when
	// the reading is already visible, which is the usual case on a wide one.
	el.headline.scrollIntoView({
		behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
		block: 'nearest',
	});

	el.areaPanel.classList.remove('is-updated');
	void el.areaPanel.offsetWidth;   // restart the animation on a repeat click
	el.areaPanel.classList.add('is-updated');
}

function describeArea(area) {
	if (!meta) return '';

	const reading = state.mapMode === 'price'
		? formatMoney(price(state.type, area, state.end, state.real))
		: formatPercent(growth(state.type, area, state.start, state.end, state.real));

	return `<b>${meta.areas[area].n}</b><br><span class="tip-value">${reading}</span>`;
}

/* The map is the one thing on the page whose meaning changes underneath the
 * reader, so its accessible name is kept in step with the toggle rather than
 * left at whatever it said when the page loaded. */
function applyMapMode() {
	el.mapEl.setAttribute('aria-label', state.mapMode === 'price'
		? 'Map of UK local authorities coloured by average house price'
		: 'Map of UK local authorities coloured by house price change');
}

function wireControls() {
	el.startSlider.addEventListener('input', () => {
		state.start = Math.min(Number(el.startSlider.value), state.end - 1);
		el.startSlider.value = String(state.start);
		render();
	});

	el.endSlider.addEventListener('input', () => {
		state.end = Math.max(Number(el.endSlider.value), state.start + 1);
		el.endSlider.value = String(state.end);
		render();
	});

	el.houseType.addEventListener('change', async () => {
		state.type = Number(el.houseType.value);
		await loadType(state.type);
		render();
	});

	el.priceBasis.addEventListener('change', () => {
		state.real = el.priceBasis.value === 'real';
		render();
	});

	el.areaSelect.addEventListener('change', () => {
		setArea(Number(el.areaSelect.value));
	});

	// Only the map changes, so this repaints it directly instead of going
	// through render() and rebuilding the chart and the table for nothing.
	for (const radio of el.mapModes) {
		radio.addEventListener('change', () => {
			if (!radio.checked) return;
			state.mapMode = radio.value;
			applyMapMode();
			renderMap();
		});
	}
}

/* ---------- startup ---------- */

function monthKey(index) {
	const [year, month] = meta.months.start.split('-').map(Number);
	const date = new Date(Date.UTC(year, month - 1 + index, 1));
	return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}`;
}

/* "Click any area" is wrong advice on a phone. The media query gets it right
 * up front for phones and tablets; the touch listener then catches anything it
 * misjudged - a laptop with a touchscreen reports a fine pointer, and its owner
 * should still be told to tap once they have actually touched the screen. */
function useTapWording() {
	for (const node of document.querySelectorAll('.pointer-verb')) node.textContent = 'Tap';
}

function applyPointerVerb() {
	if (window.matchMedia('(pointer: coarse)').matches) {
		useTapWording();
		return;
	}
	window.addEventListener('touchstart', useTapWording, { once: true, passive: true });
}

function populateControls() {
	el.houseType.innerHTML = meta.types
		.map((type, i) => `<option value="${i}">${typeLabel(type)}</option>`)
		.join('');

	// Grouped so the series without a boundary read as a different kind of
	// thing from the local authorities, rather than as odd entries in an
	// otherwise alphabetical list
	const option = (area, i) => `<option value="${i}">${area.n}</option>`;
	const localAuthorities = meta.areas.slice(0, meta.geoAreas);
	const aggregates = meta.areas.slice(meta.geoAreas);

	el.areaSelect.innerHTML =
		(aggregates.length
			? `<optgroup label="Nations, regions &amp; counties">` +
			  aggregates.map((a, k) => option(a, meta.geoAreas + k)).join('') +
			  `</optgroup>`
			: '') +
		`<optgroup label="Local authorities">` +
		localAuthorities.map(option).join('') +
		`</optgroup>`;

	const last = meta.nMonths - 1;
	for (const slider of [el.startSlider, el.endSlider]) {
		slider.min = '0';
		slider.max = String(last);
	}

	let defaultStart = 0;
	for (let i = 0; i <= last; i++) {
		if (monthKey(i) === DEFAULT_START) { defaultStart = i; break; }
	}

	state.start = defaultStart;
	state.end = last;
	el.startSlider.value = String(state.start);
	el.endSlider.value = String(state.end);

	// A county or region page hands its visitor over with ?area=E10000030 — the
	// ONS code rather than the name, because names collide: the West Midlands
	// is both a region and a county. An unrecognised code falls through to the
	// default, so a mistyped link still opens a working map rather than a blank
	// reading.
	const requested = new URLSearchParams(location.search).get('area');
	const wanted = requested ? meta.areas.findIndex((area) => area.c === requested) : -1;
	const defaultArea = meta.areas.findIndex((area) => area.c === DEFAULT_AREA_CODE);
	state.area = wanted >= 0 ? wanted : defaultArea >= 0 ? defaultArea : 0;
	el.areaSelect.value = String(state.area);

	// Browsers restore checked radios across a reload, so the toggle is read
	// rather than assumed — otherwise the map and the control disagree after
	// a refresh that puts the toggle back on "Average price".
	const checked = Array.from(el.mapModes).find((radio) => radio.checked);
	if (checked) state.mapMode = checked.value;
	applyMapMode();

	// Two genuinely different dates, so both are stated in full rather than
	// abbreviated to an ambiguous "updated": how far the price data runs, and
	// which month's money real prices are expressed in.
	el.topbarMeta.textContent = `House prices to ${meta.monthLabels[last]}`;
	el.basisNote.textContent =
		`House price data runs to ${meta.monthLabels[last]}, the most recent available — ` +
		`the Land Registry index lags a few months behind the present because of how long ` +
		`sales take to register. Real prices are shown in ${meta.cpiBase} money, the latest month of CPI data.`;
}

async function start() {
	// Neither the map nor the price matrix needs the metadata, and between them
	// they are much the largest downloads on the page — lads.geojson alone is
	// bigger than everything else in data/ put together. Starting them here
	// rather than after the await means they are in flight alongside
	// meta.json instead of queueing behind its round trip.
	mapView = createMap('map', {
		onSelect: (area) => setArea(area, true),
		describe: describeArea,
		onContextLost: () => {
			el.mapStatus.hidden = false;
			el.mapStatus.innerHTML =
				'<span>The map display was interrupted. Refresh the page to restore it.</span>';
		},
	});

	// The selected housing type first, so the map is usable as early as possible
	const pricesReady = loadType(state.type);
	// Awaited below; this only stops the browser reporting an unhandled
	// rejection in the window before that await is reached.
	pricesReady.catch(() => {});

	applyPointerVerb();

	meta = await loadMeta();
	populateControls();

	chart = createChart(el.chart, meta.types);

	await pricesReady;

	mapView.whenReady(() => {
		el.mapStatus.hidden = true;
		mapView.setSelected(state.area < meta.geoAreas ? state.area : null);
		// Held back until there is a map to point at
		if (!ctaAlreadySeen()) el.mapCta.hidden = false;
		render();
	});

	wireControls();
	render();

	// The remaining types stream in behind the first paint; each one fills in
	// another line on the chart and another row of the stats table. Held back
	// to an idle callback because they are 1.1 MB between them and nothing on
	// screen is waiting on them: letting the main thread and the connection go
	// quiet first is what lets the page settle, and the page settling is what
	// ends the window Total Blocking Time is measured over.
	const loadRemaining = () => {
		meta.types.forEach((_, i) => {
			if (i === state.type) return;
			loadType(i).then(scheduleAreaDetail).catch((error) => console.error(error));
		});
	};

	if ('requestIdleCallback' in window) requestIdleCallback(loadRemaining, { timeout: 2500 });
	else setTimeout(loadRemaining, 500);
}

start().catch((error) => {
	console.error(error);
	el.mapStatus.innerHTML = '<span>Could not load the data. Please refresh to try again.</span>';
});
