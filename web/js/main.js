/* Application entry point: owns the interaction state and keeps the map,
 * stats table and chart in step with it.
 *
 * All computation happens here in the browser — the server only ever serves
 * static files. */

import { loadMeta, getMeta, loadType, isLoaded, price, growth, growthByArea, annualise } from './data.js';
import { createMap } from './map.js';
import { createChart, formatPrice } from './chart.js';

const DEFAULT_AREA_CODE = 'S12000036';   // City of Edinburgh
const DEFAULT_START = '2005-01';

const el = {
	startSlider: document.getElementById('start-month'),
	endSlider: document.getElementById('end-month'),
	startLabel: document.getElementById('start-label'),
	endLabel: document.getElementById('end-label'),
	houseType: document.getElementById('house-type'),
	priceBasis: document.getElementById('price-basis'),
	areaSelect: document.getElementById('area-select'),
	stats: document.querySelector('#stats tbody'),
	chart: document.getElementById('chart'),
	chartTitle: document.getElementById('chart-title'),
	mapStatus: document.getElementById('map-status'),
	legend: document.getElementById('legend'),
	legendMin: document.getElementById('legend-min'),
	legendMax: document.getElementById('legend-max'),
	basisNote: document.getElementById('basis-note'),
};

const state = {
	start: 0,
	end: 0,
	type: 0,
	real: true,
	area: 0,
};

let meta = null;
let mapView = null;
let chart = null;
let frame = null;

function formatPercent(value, digits = 1) {
	if (!Number.isFinite(value)) return '—';
	return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}%`;
}

/* ---------- rendering ---------- */

function renderLabels() {
	el.startLabel.textContent = meta.monthLabels[state.start];
	el.endLabel.textContent = meta.monthLabels[state.end];
}

function renderMap() {
	const values = growthByArea(state.type, state.start, state.end, state.real);
	const bound = mapView.setValues(values);

	if (bound !== null) {
		el.legend.hidden = false;
		el.legendMin.textContent = formatPercent(-bound, 0);
		el.legendMax.textContent = formatPercent(bound, 0);
	}
}

function renderStats() {
	const rows = meta.types.map((type, i) => {
		const loaded = isLoaded(i);
		const total = loaded ? growth(i, state.area, state.start, state.end, state.real) : NaN;
		const perYear = loaded ? annualise(total, state.start, state.end) : NaN;

		const cls = !Number.isFinite(total) ? 'none' : total >= 0 ? 'up' : 'down';
		const label = type === 'SemiDetached' ? 'Semi-detached' : type;
		const cell = (value) => (loaded ? formatPercent(value) : '…');

		return `<tr>
			<td>${label}</td>
			<td class="${cls}">${cell(total)}</td>
			<td class="${cls}">${cell(perYear)}</td>
		</tr>`;
	});

	el.stats.innerHTML = rows.join('');
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

	const basis = state.real ? 'real' : 'nominal';
	el.chartTitle.textContent =
		`Average ${basis} house price in ${meta.areas[state.area].n}`;
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
		renderLabels();
		renderMap();
		renderStats();
		renderChart();
	});
}

/* ---------- interaction ---------- */

function setArea(area) {
	state.area = area;
	el.areaSelect.value = String(area);
	mapView.setSelected(area);
	renderStats();
	renderChart();
}

function describeArea(area) {
	const value = growth(state.type, area, state.start, state.end, state.real);
	return `<b>${meta.areas[area].n}</b><br>${formatPercent(value)}`;
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
}

/* ---------- startup ---------- */

function populateControls() {
	el.houseType.innerHTML = meta.types
		.map((type, i) => {
			const label = type === 'SemiDetached' ? 'Semi-detached' : type;
			return `<option value="${i}">${label}</option>`;
		})
		.join('');

	el.areaSelect.innerHTML = meta.areas
		.map((area, i) => `<option value="${i}">${area.n}</option>`)
		.join('');

	const last = meta.nMonths - 1;
	for (const slider of [el.startSlider, el.endSlider]) {
		slider.min = '0';
		slider.max = String(last);
	}

	const defaultStart = meta.monthLabels.findIndex((_, i) => {
		const [year, month] = meta.months.start.split('-').map(Number);
		const d = new Date(Date.UTC(year, month - 1 + i, 1));
		return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}` === DEFAULT_START;
	});

	state.start = defaultStart >= 0 ? defaultStart : 0;
	state.end = last;
	el.startSlider.value = String(state.start);
	el.endSlider.value = String(state.end);

	const defaultArea = meta.areas.findIndex((area) => area.c === DEFAULT_AREA_CODE);
	state.area = defaultArea >= 0 ? defaultArea : 0;
	el.areaSelect.value = String(state.area);

	el.basisNote.textContent =
		`Real prices are expressed in ${meta.cpiBase} money. Data last updated ${meta.generated}.`;
}

async function start() {
	meta = await loadMeta();
	populateControls();

	chart = createChart(el.chart, meta.types);
	mapView = createMap('map', { onSelect: setArea, describe: describeArea });

	// The selected housing type first, so the map is usable as early as possible
	await loadType(state.type);

	mapView.whenReady(() => {
		el.mapStatus.hidden = true;
		mapView.setSelected(state.area);
		render();
	});

	wireControls();
	render();

	// The remaining types stream in behind the first paint; each one fills in
	// another line on the chart and another row of the stats table.
	meta.types.forEach((_, i) => {
		if (i === state.type) return;
		loadType(i).then(() => {
			renderStats();
			renderChart();
		});
	});
}

start().catch((error) => {
	console.error(error);
	el.mapStatus.textContent = 'Could not load the data. Please refresh to try again.';
});
