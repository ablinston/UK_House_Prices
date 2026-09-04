/* The choropleth map: MapLibre GL with GeoJSON sources and no basemap tiles.
 *
 * Colours are driven entirely by feature-state, so recolouring is a per-feature
 * state update rather than a re-render of the geometry. The normalised value
 * `n` is clamped to [-1, 1]; NO_DATA sits far outside that range so the paint
 * expression can distinguish "no observation" from "no change".
 *
 * There is still no tile basemap, but the map is not left unlabelled either:
 * the local authority polygons draw the coastline for free, and places.geojson
 * adds city and town labels on top for orientation. Both the glyphs and the
 * place data are served from this origin, so the page depends on no external
 * tile service — see CLAUDE.md for why that constraint exists.
 *
 * Every colour is read from the CSS custom properties in css/style.css, so the
 * map follows the visitor's light/dark browser setting along with the rest of
 * the page. */

const NO_DATA = -999;
const UK_BOUNDS = [[-8.8, 49.8], [2.1, 61.1]];

/* Place labels are ranked 0 (biggest cities) to 4 (towns) by src/07. Revealing
 * a rank per zoom level keeps the national view readable: at the opening zoom
 * only the couple of dozen largest cities are eligible, and MapLibre's own
 * collision detection thins even those where they crowd. */
const PLACE_RANK_FOR_ZOOM = ['step', ['zoom'], 0, 6, 1, 7, 2, 8, 3, 9, 4];
const PLACE_FILTER = ['<=', ['get', 'r'], PLACE_RANK_FOR_ZOOM];

function cssVar(name, fallback) {
	const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
	return value || fallback;
}

function palette() {
	return {
		water: cssVar('--map-water', '#e4eaf1'),
		line: cssVar('--map-line', 'rgba(255,255,255,0.6)'),
		nodata: cssVar('--map-nodata', '#dde2e9'),
		negative: cssVar('--ramp-neg', '#be123c'),
		mid: cssVar('--ramp-mid', '#f8fafc'),
		positive: cssVar('--ramp-pos', '#0f766e'),
		hover: cssVar('--text', '#0d1117'),
		selected: cssVar('--accent-bright', '#2563eb'),
		place: cssVar('--map-place', '#333b49'),
		placeHalo: cssVar('--map-place-halo', 'rgba(255,255,255,0.85)'),
	};
}

function fillColour(colours) {
	return [
		'case',
		['<', ['coalesce', ['feature-state', 'n'], NO_DATA], -90], colours.nodata,
		[
			'interpolate', ['linear'],
			['coalesce', ['feature-state', 'n'], 0],
			-1, colours.negative,
			0, colours.mid,
			1, colours.positive,
		],
	];
}

function buildStyle(colours) {
	return {
		version: 8,
		// Self-hosted so no tile service is involved. Only the 0-255 range is
		// committed, which covers every name in places.geojson; src/07 warns if
		// a data refresh ever introduces a character beyond it.
		glyphs: 'vendor/fonts/glyphs/{fontstack}/{range}.pbf',
		sources: {
			lads: { type: 'geojson', data: 'data/lads.geojson' },
			places: { type: 'geojson', data: 'data/places.geojson' },
		},
		layers: [
			{
				id: 'background',
				type: 'background',
				paint: { 'background-color': colours.water },
			},
			{
				id: 'lads-fill',
				type: 'fill',
				source: 'lads',
				paint: { 'fill-color': fillColour(colours), 'fill-opacity': 1 },
			},
			{
				id: 'lads-outline',
				type: 'line',
				source: 'lads',
				paint: { 'line-color': colours.line, 'line-width': 0.5 },
			},
			{
				id: 'lads-hover',
				type: 'line',
				source: 'lads',
				paint: {
					'line-color': colours.hover,
					'line-width': ['case', ['boolean', ['feature-state', 'hover'], false], 1.4, 0],
				},
			},
			{
				id: 'lads-selected',
				type: 'line',
				source: 'lads',
				paint: {
					'line-color': colours.selected,
					'line-width': ['case', ['boolean', ['feature-state', 'selected'], false], 2.4, 0],
				},
			},
			// Places sit above the choropleth. Underneath a fill they would be
			// invisible without making the fill translucent, which would distort
			// the very colours the map exists to show; a halo does the job of
			// keeping them legible over any part of the ramp instead.
			{
				id: 'places-dot',
				type: 'circle',
				source: 'places',
				filter: PLACE_FILTER,
				paint: {
					'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 1.4, 9, 2.6],
					'circle-color': colours.place,
					'circle-opacity': 0.8,
					'circle-stroke-width': 0.8,
					'circle-stroke-color': colours.placeHalo,
				},
			},
			{
				id: 'places-label',
				type: 'symbol',
				source: 'places',
				filter: PLACE_FILTER,
				layout: {
					'text-field': ['get', 'n'],
					'text-font': ['NotoSans-Regular'],
					'text-size': ['interpolate', ['linear'], ['zoom'], 4, 9.5, 8, 11.5, 11, 13],
					// Letting MapLibre try the other side of the dot before it
					// gives up places noticeably more labels at national zoom,
					// where the likes of Glasgow and Edinburgh sit close enough
					// to fight over the same space
					'text-variable-anchor': ['top', 'bottom', 'left', 'right'],
					'text-radial-offset': 0.5,
					'text-justify': 'auto',
					'text-padding': 2,
					'text-max-width': 8,
					// Population order, so the bigger settlement wins a collision
					'symbol-sort-key': ['get', 's'],
				},
				paint: {
					'text-color': colours.place,
					'text-halo-color': colours.placeHalo,
					'text-halo-width': 1.4,
					'text-halo-blur': 0.2,
				},
			},
		],
	};
}

/** Symmetric colour bound, ignoring the nine most extreme areas so that a
 *  handful of outliers don't flatten the rest of the map. Mirrors the original
 *  `MapValue.abs().nlargest(10).min()`. */
export function colourBound(values) {
	const magnitudes = [];
	for (const value of values) {
		if (Number.isFinite(value)) magnitudes.push(Math.abs(value));
	}
	if (magnitudes.length === 0) return 1;

	magnitudes.sort((a, b) => b - a);
	return Math.max(magnitudes[Math.min(9, magnitudes.length - 1)], 0.1);
}

export function createMap(container, { onSelect, describe, onContextLost }) {
	const map = new maplibregl.Map({
		container,
		style: buildStyle(palette()),
		bounds: UK_BOUNDS,
		fitBoundsOptions: { padding: 24 },
		minZoom: 4,
		maxZoom: 11,
		attributionControl: false,
		dragRotate: false,
		pitchWithRotate: false,
		cooperativeGestures: true,
	});

	map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
	map.touchZoomRotate.disableRotation();

	map.on('error', (event) => {
		const error = event && event.error ? event.error : event;
		console.error('Map error:', error && error.message ? error.message : error);
	});

	// A browser can drop a WebGL context at any time — a GPU driver reset, or
	// simply too many map tabs open, since contexts are limited per process.
	// Without this the page sits on "Loading map" forever with no explanation.
	map.on('webglcontextlost', () => {
		console.error('WebGL context lost; the map cannot continue.');
		if (onContextLost) onContextLost();
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

	// Follow the browser theme without reloading the geometry
	window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
		if (!map.isStyleLoaded()) return;
		const colours = palette();
		map.setPaintProperty('background', 'background-color', colours.water);
		map.setPaintProperty('lads-fill', 'fill-color', fillColour(colours));
		map.setPaintProperty('lads-outline', 'line-color', colours.line);
		map.setPaintProperty('lads-hover', 'line-color', colours.hover);
		map.setPaintProperty('lads-selected', 'line-color', colours.selected);
		map.setPaintProperty('places-dot', 'circle-color', colours.place);
		map.setPaintProperty('places-dot', 'circle-stroke-color', colours.placeHalo);
		map.setPaintProperty('places-label', 'text-color', colours.place);
		map.setPaintProperty('places-label', 'text-halo-color', colours.placeHalo);
	});

	map.on('mousemove', 'lads-fill', (event) => {
		const feature = event.features && event.features[0];
		if (!feature) return;

		setHover(feature.id);
		map.getCanvas().style.cursor = 'pointer';

		tooltip.innerHTML = describe(feature.id);
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
