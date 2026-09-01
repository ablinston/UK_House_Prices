/* Loading and decoding of the exported price data.
 *
 * Prices are stored per housing type as a uint16 matrix of [area][month],
 * holding an index relative to that area's first observation (x meta.scale).
 * 0 marks a missing observation. Absolute prices are recovered as
 *   base[type][area] * index / scale
 * and deflated by the CPI series when real prices are requested. */

const MISSING = 0;

let meta = null;
const matrices = [];   // type index -> Uint16Array
const inflight = [];   // type index -> Promise

/** Build the month axis from the compact {start, count} representation. */
function buildMonths(start, count) {
	const [year, month] = start.split('-').map(Number);
	const times = new Array(count);
	const labels = new Array(count);

	for (let i = 0; i < count; i++) {
		const d = new Date(Date.UTC(year, month - 1 + i, 1));
		times[i] = d.getTime() / 1000;                       // uPlot wants seconds
		labels[i] = d.toLocaleDateString('en-GB', {
			month: 'short', year: 'numeric', timeZone: 'UTC',
		});
	}

	return { times, labels };
}

export async function loadMeta() {
	const response = await fetch('data/meta.json');
	if (!response.ok) throw new Error(`meta.json: ${response.status}`);

	meta = await response.json();
	meta.nAreas = meta.areas.length;
	meta.nMonths = meta.months.count;

	const { times, labels } = buildMonths(meta.months.start, meta.nMonths);
	meta.monthTimes = times;
	meta.monthLabels = labels;

	return meta;
}

export function getMeta() {
	return meta;
}

/** Fetch one housing type's matrix, de-duplicating concurrent requests. */
export function loadType(type) {
	if (matrices[type]) return Promise.resolve(matrices[type]);

	if (!inflight[type]) {
		inflight[type] = fetch(`data/prices-${type}.bin`)
			.then((response) => {
				if (!response.ok) throw new Error(`prices-${type}.bin: ${response.status}`);
				return response.arrayBuffer();
			})
			.then((buffer) => {
				matrices[type] = new Uint16Array(buffer);
				return matrices[type];
			});
	}

	return inflight[type];
}

export function isLoaded(type) {
	return Boolean(matrices[type]);
}

function rawIndex(type, area, month) {
	const matrix = matrices[type];
	if (!matrix) return MISSING;
	return matrix[area * meta.nMonths + month];
}

/** Absolute price for one area/month, or NaN when not recorded. */
export function price(type, area, month, real) {
	const index = rawIndex(type, area, month);
	if (index === MISSING) return NaN;

	let value = meta.base[type][area] * index / meta.scale;
	if (real) value /= meta.cpi[month];
	return value;
}

/** Percentage price change between two months, or NaN when either is missing.
 *  The base price cancels out, so this works directly on the stored indices. */
export function growth(type, area, start, end, real) {
	const from = rawIndex(type, area, start);
	const to = rawIndex(type, area, end);
	if (from === MISSING || to === MISSING) return NaN;

	let ratio = to / from;
	if (real) ratio *= meta.cpi[start] / meta.cpi[end];
	return (ratio - 1) * 100;
}

/** Growth for every area at once — the array the choropleth is built from. */
export function growthByArea(type, start, end, real) {
	const values = new Float64Array(meta.nAreas);
	for (let area = 0; area < meta.nAreas; area++) {
		values[area] = growth(type, area, start, end, real);
	}
	return values;
}

/** First and last months for which an area has an observation, or null if it
 *  has none at all. Scotland and Northern Ireland start well after England and
 *  Wales, so this is what explains an empty reading rather than a broken one. */
export function coverage(type, area) {
	const matrix = matrices[type];
	if (!matrix) return null;

	const offset = area * meta.nMonths;
	let first = -1;
	let last = -1;

	for (let month = 0; month < meta.nMonths; month++) {
		if (matrix[offset + month] !== MISSING) {
			if (first < 0) first = month;
			last = month;
		}
	}

	return first < 0 ? null : { first, last };
}

/** Convert a total percentage change into an annualised rate.
 *  Mirrors the original Shiny app, which measured years as days / 365. */
export function annualise(total, startMonth, endMonth) {
	const days = (meta.monthTimes[endMonth] - meta.monthTimes[startMonth]) / 86400;
	const years = days / 365;
	if (!Number.isFinite(total) || years <= 0) return NaN;
	return ((total / 100 + 1) ** (1 / years) - 1) * 100;
}
