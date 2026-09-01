/* Price history chart for the selected area — one line per housing type.
 * uPlot is small enough to vendor and redraws fast enough to follow the
 * date sliders without dropping frames. */

const SERIES_COLOURS = [
	'#1a1d24',  // Overall
	'#1b7837',  // Detached
	'#d95f02',  // SemiDetached
	'#7570b3',  // Terraced
	'#2166ac',  // Flat
];

const LABELS = {
	Overall: 'Overall',
	Detached: 'Detached',
	SemiDetached: 'Semi-detached',
	Terraced: 'Terraced',
	Flat: 'Flat',
};

export function formatPrice(value) {
	if (!Number.isFinite(value)) return '—';
	return '£' + Math.round(value).toLocaleString('en-GB');
}

function formatAxis(value) {
	if (!Number.isFinite(value)) return '';
	if (Math.abs(value) >= 1e6) return '£' + (value / 1e6).toFixed(1) + 'm';
	return '£' + Math.round(value / 1000) + 'k';
}

export function createChart(container, types) {
	let plot = null;
	let lastData = null;

	function size() {
		return {
			width: Math.max(container.clientWidth, 240),
			height: 260,
		};
	}

	const options = {
		...size(),
		cursor: { drag: { x: false, y: false } },
		legend: { live: true },
		scales: { x: { time: true } },
		axes: [
			{ grid: { stroke: '#eceef4' }, ticks: { stroke: '#d8dce6' } },
			{
				grid: { stroke: '#eceef4' },
				ticks: { stroke: '#d8dce6' },
				size: 58,
				values: (self, splits) => splits.map(formatAxis),
			},
		],
		series: [
			{ label: 'Date' },
			...types.map((type, i) => ({
				label: LABELS[type] || type,
				stroke: SERIES_COLOURS[i % SERIES_COLOURS.length],
				width: type === 'Overall' ? 2.2 : 1.4,
				dash: type === 'Overall' ? undefined : [4, 3],
				value: (self, raw) => formatPrice(raw),
				spanGaps: false,
			})),
		],
	};

	// Keep the plot matched to its container without a layout library
	const observer = new ResizeObserver(() => {
		if (plot) plot.setSize(size());
	});
	observer.observe(container);

	return {
		update(data) {
			lastData = data;
			if (plot) {
				plot.setData(data);
			} else {
				plot = new uPlot(options, data, container);
			}
		},

		redraw() {
			if (plot && lastData) plot.setData(lastData);
		},
	};
}
