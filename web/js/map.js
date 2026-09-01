/* The choropleth map: MapLibre GL with a GeoJSON source and no basemap tiles.
 *
 * Colours are driven entirely by feature-state, so recolouring is a per-feature
 * state update rather than a re-render of the geometry. The normalised value
 * `n` is clamped to [-1, 1]; NO_DATA sits far outside that range so the paint
 * expression can distinguish "no observation" from "no change". */

const NO_DATA = -999;
const UK_BOUNDS = [[-8.8, 49.8], [2.1, 61.1]];

const RAMP_NEGATIVE = '#9a0000';
const RAMP_MID = '#ffffff';
const RAMP_POSITIVE = '#085602';
const NO_DATA_FILL = '#e6e8ee';

/** Symmetric colour bound, ignoring the nine most extreme areas so that a
 *  handful of outliers don't flatten the rest of the map. Mirrors the original
 *  Shiny app's `MapValue.abs().nlargest(10).min()`. */
export function colourBound(values) {
	const magnitudes = [];
	for (const value of values) {
		if (Number.isFinite(value)) magnitudes.push(Math.abs(value));
	}
	if (magnitudes.length === 0) return 1;

	magnitudes.sort((a, b) => b - a);
	const bound = magnitudes[Math.min(9, magnitudes.length - 1)];
	return Math.max(bound, 0.1);
}

const style = {
	version: 8,
	sources: {
		lads: { type: 'geojson', data: 'data/lads.geojson' },
	},
	layers: [
		{
			id: 'background',
			type: 'background',
			paint: { 'background-color': '#dbe4ef' },
		},
		{
			id: 'lads-fill',
			type: 'fill',
			source: 'lads',
			paint: {
				'fill-color': [
					'case',
					['<', ['coalesce', ['feature-state', 'n'], NO_DATA], -90], NO_DATA_FILL,
					[
						'interpolate', ['linear'],
						['coalesce', ['feature-state', 'n'], 0],
						-1, RAMP_NEGATIVE,
						0, RAMP_MID,
						1, RAMP_POSITIVE,
					],
				],
				'fill-opacity': 0.9,
			},
		},
		{
			id: 'lads-outline',
			type: 'line',
			source: 'lads',
			paint: {
				'line-color': '#8a93a6',
				'line-width': 0.4,
				'line-opacity': 0.6,
			},
		},
		{
			id: 'lads-hover',
			type: 'line',
			source: 'lads',
			paint: {
				'line-color': '#1a1d24',
				'line-width': ['case', ['boolean', ['feature-state', 'hover'], false], 1.6, 0],
			},
		},
		{
			id: 'lads-selected',
			type: 'line',
			source: 'lads',
			paint: {
				'line-color': '#061567',
				'line-width': ['case', ['boolean', ['feature-state', 'selected'], false], 2.4, 0],
			},
		},
	],
};

export function createMap(container, { onSelect, describe }) {
	const map = new maplibregl.Map({
		container,
		style,
		bounds: UK_BOUNDS,
		fitBoundsOptions: { padding: 20 },
		minZoom: 4,
		maxZoom: 11,
		attributionControl: false,
		dragRotate: false,
		pitchWithRotate: false,
		touchZoomRotate: true,
	});

	map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
	map.touchZoomRotate.disableRotation();

	// Surface style/source failures rather than sitting on a blank canvas
	map.on('error', (event) => {
		const error = event && event.error ? event.error : event;
		console.error('Map error:', error && error.message ? error.message : error, error);
	});

	const tooltip = document.createElement('div');
	tooltip.className = 'map-tooltip';
	map.getContainer().appendChild(tooltip);

	let ready = false;
	let pendingValues = null;
	let hovered = null;
	let selected = null;
	const readyCallbacks = [];

	// setFeatureState throws until the source has loaded, so selection and
	// colouring are both held until then and replayed once the map is ready.
	function applySelected() {
		if (!ready || selected === null) return;
		map.setFeatureState({ source: 'lads', id: selected }, { selected: true });
	}

	function paint(values) {
		const bound = colourBound(values);

		for (let area = 0; area < values.length; area++) {
			const value = values[area];
			const normalised = Number.isFinite(value)
				? Math.max(-1, Math.min(1, value / bound))
				: NO_DATA;
			map.setFeatureState({ source: 'lads', id: area }, { n: normalised });
		}

		return bound;
	}

	function setHover(area) {
		if (hovered === area) return;
		if (hovered !== null) {
			map.setFeatureState({ source: 'lads', id: hovered }, { hover: false });
		}
		hovered = area;
		if (hovered !== null) {
			map.setFeatureState({ source: 'lads', id: hovered }, { hover: true });
		}
	}

	map.on('mousemove', 'lads-fill', (event) => {
		const feature = event.features && event.features[0];
		if (!feature) return;

		const area = feature.id;
		setHover(area);
		map.getCanvas().style.cursor = 'pointer';

		tooltip.innerHTML = describe(area);
		tooltip.style.left = `${event.point.x}px`;
		tooltip.style.top = `${event.point.y}px`;
		tooltip.classList.add('is-visible');
	});

	map.on('mouseleave', 'lads-fill', () => {
		setHover(null);
		map.getCanvas().style.cursor = '';
		tooltip.classList.remove('is-visible');
	});

	map.on('click', 'lads-fill', (event) => {
		const feature = event.features && event.features[0];
		if (feature) onSelect(feature.id);
	});

	function markReady() {
		if (ready) return;
		ready = true;

		map.off('sourcedata', checkReady);
		map.off('idle', checkReady);

		applySelected();

		let bound = null;
		if (pendingValues) {
			bound = paint(pendingValues);
			pendingValues = null;
		}

		while (readyCallbacks.length) readyCallbacks.shift()(bound);
	}

	function checkReady() {
		if (ready) return;
		// isSourceLoaded throws while the style is still parsing
		if (!map.isStyleLoaded()) return;
		if (!map.isSourceLoaded('lads')) return;
		markReady();
	}

	// Registered up front: callers may attach whenReady() after an await, by
	// which point 'load' may already have fired and would never fire again.
	map.on('load', checkReady);
	map.on('sourcedata', checkReady);
	map.on('idle', checkReady);

	return {
		map,

		/** Runs once the geometry is loaded and feature-state will stick. */
		whenReady(callback) {
			if (ready) callback(null);
			else readyCallbacks.push(callback);
		},

		/** Recolour every area. Returns the colour bound, or null if not ready. */
		setValues(values) {
			if (!ready) {
				pendingValues = values;
				return null;
			}
			return paint(values);
		},

		setSelected(area) {
			if (ready && selected !== null) {
				map.setFeatureState({ source: 'lads', id: selected }, { selected: false });
			}
			selected = area;
			applySelected();
		},
	};
}
