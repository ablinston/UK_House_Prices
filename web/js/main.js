/* Application entry point: owns the interaction state and keeps the map,
 * stats table and chart in step with it.
 *
 * All computation happens here in the browser — the server only ever serves
 * static files. */

import { loadMeta, loadType, isLoaded, price, growth, growthByArea, annualise, coverage } from './data.js';
import { createMap } from './map.js';
import { createChart } from './chart.js';

const DEFAULT_AREA_CODE = 'E08000003';   // Manchester
const DEFAULT_START = '2005-01';
const THUMB = 16;                        // matches the slider thumb in style.css

const el = {
	startSlider: document.getElementById('start-month'),
	endSlider: document.getElementById('end-month'),
	startLabel: document.getElementById('start-label'),
	endLabel: document.getElementById('end-label'),
	rangeFill: document.getElementById('range-fill'),
	houseType: document.getElementById('house-type'),
	priceBasis: document.getElementById('price-basis'),
	areaSelect: document.getElementById('area-select'),
	headlineValue: document.getElementById('headline-value'),
	headlineLabel: document.getElementById('headline-label'),
	stats: document.querySelector('#stats tbody'),
	chart: document.getElementById('chart'),
	chartTitle: document.getElementById('chart-title'),
	mapStatus: document.getElementById('map-status'),
	legend: document.getElementById('legend'),
	legendMin: document.getElementById('legend-min'),
	legendMax: document.getElementById('legend-max'),
	topbarMeta: document.getElementById('topbar-meta'),
	basisNote: document.getElementById('basis-note'),
};

const state = { start: 0, end: 0, type: 0, real: true, area: 0 };

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
	const values = growthByArea(state.type, state.start, state.end, state.real);
	const bound = mapView.setValues(values);

	if (bound !== null) {
		el.legend.hidden = false;
		el.legendMin.textContent = formatPercent(-bound, 0);
		el.legendMax.textContent = formatPercent(bound, 0);
	}
}

function renderHeadline() {
	const loaded = isLoaded(state.type);
	const total = loaded ? growth(state.type, state.area, state.start, state.end, state.real) : NaN;

	el.headlineValue.className = `headline-value ${toneOf(total)}`;

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

/* ---------- interaction ---------- */

function setArea(area) {
	state.area = area;
	el.areaSelect.value = String(area);
	mapView.setSelected(area);
	renderAreaDetail();
}

function describeArea(area) {
	const value = growth(state.type, area, state.start, state.end, state.real);
	return `<b>${meta.areas[area].n}</b><br><span class="tip-value">${formatPercent(value)}</span>`;
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

function monthKey(index) {
	const [year, month] = meta.months.start.split('-').map(Number);
	const date = new Date(Date.UTC(year, month - 1 + index, 1));
	return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}`;
}

function populateControls() {
	el.houseType.innerHTML = meta.types
		.map((type, i) => `<option value="${i}">${typeLabel(type)}</option>`)
		.join('');

	el.areaSelect.innerHTML = meta.areas
		.map((area, i) => `<option value="${i}">${area.n}</option>`)
		.join('');

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

	const defaultArea = meta.areas.findIndex((area) => area.c === DEFAULT_AREA_CODE);
	state.area = defaultArea >= 0 ? defaultArea : 0;
	el.areaSelect.value = String(state.area);

	// Two genuinely different dates, so both are stated in full rather than
	// abbreviated to an ambiguous "updated": how far the price data runs, and
	// which month's money real prices are expressed in.
	el.topbarMeta.textContent = `House prices to ${meta.monthLabels[last]}`;
	el.basisNote.textContent =
		`House price data runs to ${meta.monthLabels[last]}. ` +
		`Real prices are shown in ${meta.cpiBase} money, the latest month of CPI data.`;
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
		loadType(i).then(renderAreaDetail);
	});
}

start().catch((error) => {
	console.error(error);
	el.mapStatus.innerHTML = '<span>Could not load the data. Please refresh to try again.</span>';
});
