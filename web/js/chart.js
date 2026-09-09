/* Price history chart for the selected area — one line per housing type.
 * uPlot is small enough to vendor and redraws fast enough to follow the
 * date sliders without dropping frames.
 *
 * Series colours come from the --series-N CSS tokens so the chart matches the
 * active theme; on a theme change the plot is rebuilt, since uPlot bakes series
 * strokes in at construction. */

const LABELS = {
	Overall: 'Overall',
	Detached: 'Detached',
	SemiDetached: 'Semi-detached',
	Terraced: 'Terraced',
	Flat: 'Flat',
};

function cssVar(name, fallback) {
	const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
	return value || fallback;
}

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
		return { width: Math.max(container.clientWidth, 240), height: 250 };
	}

	function buildOptions() {
		const grid = cssVar('--border', '#e5e8ee');
		const tick = cssVar('--border-strong', '#d4dae3');
		const label = cssVar('--text-subtle', '#868e9d');

		return {
			...size(),
			cursor: { drag: { x: false, y: false }, points: { size: 6 } },
			legend: { live: true },
			scales: { x: { time: true } },
			axes: [
				{
					stroke: label,
					grid: { stroke: grid, width: 1 },
					ticks: { stroke: tick, width: 1 },
					font: '11px Inter, system-ui, sans-serif',
				},
				{
					stroke: label,
					grid: { stroke: grid, width: 1 },
					ticks: { stroke: tick, width: 1 },
					size: 56,
					font: '11px Inter, system-ui, sans-serif',
					values: (self, splits) => splits.map(formatAxis),
				},
			],
			series: [
				{ label: 'Date' },
				...types.map((type, i) => ({
					label: LABELS[type] || type,
					stroke: cssVar(`--series-${i}`, '#2563eb'),
					width: type === 'Overall' ? 2.2 : 1.3,
					dash: type === 'Overall' ? undefined : [4, 3],
					value: (self, raw) => formatPrice(raw),
					points: { show: false },
					spanGaps: false,
				})),
			],
		};
	}

	function build(data) {
		if (plot) plot.destroy();
		plot = new uPlot(buildOptions(), data, container);
	}

	const observer = new ResizeObserver(() => {
		if (plot) plot.setSize(size());
	});
	observer.observe(container);

	// uPlot cannot restyle in place, so rebuild when the theme flips
	window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
		if (lastData) build(lastData);
	});

	return {
		update(data) {
			lastData = data;
			if (plot) plot.setData(data);
			else build(data);
		},
	};
}
