/* The choropleth map, drawn on a 2D canvas.
 *
 * A drop-in replacement for map.js: same createMap() signature, same
 * { whenReady, setValues, setSelected } surface, same visual result. The
 * difference is that it carries no rendering library — map.js needs 784 KB of
 * MapLibre GL plus 64 KB of its stylesheet, and parsing that was the single
 * largest block of main-thread time on the page.
 *
 * That trade is only available because of what this map is not: there is no
 * basemap, no tile pyramid, no rotation and no pitch, and the whole of the UK
 * is 360 polygons totalling ~50k coordinate pairs. Canvas redraws that in a
 * few milliseconds, so the engine MapLibre exists to provide is not earning
 * its download here. The absence of a basemap is deliberate: it avoids both
 * the cost and the usage restrictions that come with third-party tiles.
 *
 * The design that makes it fast:
 *
 *   - Coordinates are projected to Web Mercator once, at load, into a Path2D
 *     per feature held in world pixels. Panning and zooming are then a
 *     setTransform() on those retained paths, so no path is ever rebuilt and
 *     no trigonometry runs per frame.
 *   - Hit testing is a bbox prefilter plus an even-odd ray cast in world
 *     space, which needs no second canvas and survives a view change without
 *     invalidation.
 *   - Colours are baked into a 256-entry ramp lookup whenever the values or
 *     the theme change, never interpolated per feature per frame.
 *
 * Colours still come from the CSS custom properties in css/style.css, so the
 * map follows the visitor's light/dark browser setting like the rest of the
 * page. */

const NO_DATA = -999;
const UK_BOUNDS = [[-8.8, 49.8], [2.1, 61.1]];
const FIT_PADDING = 24;

const MIN_ZOOM = 4;
const MAX_ZOOM = 11;

/* World coordinates are stored as pixels at REF_ZOOM rather than as a unit
 * square, so the per-frame scale factor stays near 1 and canvas line widths
 * (which are in user space, and so divided by that factor) stay comfortably
 * within single-precision range. */
const REF_ZOOM = 12;
const WORLD = 512 * 2 ** REF_ZOOM;
const MAX_LAT = 85.0511287798;

const RAMP_STEPS = 256;

/* The average-price map reuses the same ramp as the change map by normalising
 * into [0, 1] instead of [-1, 1], so it runs mid -> positive: one sequential
 * ramp, no second set of colours and no second lookup. It starts a little way
 * along that run rather than at pure mid, because at mid the cheapest areas are
 * nearly indistinguishable from the flat no-data fill. */
const SEQ_FLOOR = 0.15;

/* Widths in CSS pixels, matching the line-width paint properties map.js sets */
const OUTLINE_WIDTH = 0.5;
const HOVER_WIDTH = 1.4;
const SELECTED_WIDTH = 2.4;

const LABEL_PADDING = 2;      // text-padding
const LABEL_MAX_EMS = 8;      // text-max-width
const LABEL_OFFSET_EMS = 0.5; // text-radial-offset
const HALO_WIDTH = 1.4;       // text-halo-width
const LABEL_ANCHORS = ['top', 'bottom', 'left', 'right'];

/* Ceilings on a flick: a pointer sampled a fraction of a millisecond apart
 * yields a velocity that means nothing physical, and an uncapped one sends the
 * map sliding to its pan limit from the smallest gesture. */
const MIN_SAMPLE_MS = 8;
const MAX_FLING = 3;   // CSS pixels per millisecond

/* A finger never holds perfectly still, so a tap is allowed to wander this far
 * before it counts as a drag. HINT_SLOP is deliberately larger: the gesture
 * hint should only answer a real attempt to move the map. */
const TAP_SLOP = 10;
const HINT_SLOP = 14;
const TAP_TIMEOUT = 500;

/* A hard ceiling on how many labels are considered in one frame. The zoom
 * filter already keeps this far lower in practice; the cap only bounds the
 * cost of the collision pass if a future data refresh grows places.geojson. */
const MAX_LABEL_CANDIDATES = 400;

const IS_APPLE = typeof navigator !== 'undefined' && /Mac|iPhone|iPad|iPod/.test(navigator.platform || '');

/* ---------- projection ---------- */

function worldX(lon) {
	return ((lon + 180) / 360) * WORLD;
}

function worldY(lat) {
	const clamped = Math.max(-MAX_LAT, Math.min(MAX_LAT, lat));
	const sin = Math.sin((clamped * Math.PI) / 180);
	return (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * WORLD;
}

function clamp(value, min, max) {
	return value < min ? min : value > max ? max : value;
}

/* ---------- colour ---------- */

/* Round-tripping a colour through fillStyle is how any CSS colour the browser
 * understands gets normalised to #rrggbb or rgba(...), which saves parsing the
 * long tail of colour syntaxes by hand. */
function parseColour(ctx, value, fallback) {
	ctx.fillStyle = '#000000';
	try {
		ctx.fillStyle = value;
	} catch (error) {
		ctx.fillStyle = fallback;
	}
	const normalised = ctx.fillStyle;

	if (normalised[0] === '#') {
		const hex = normalised.slice(1);
		const wide = hex.length >= 6;
		const part = (i) => parseInt(wide ? hex.slice(i * 2, i * 2 + 2) : hex[i] + hex[i], 16);
		return [part(0), part(1), part(2), 1];
	}

	const numbers = normalised.slice(normalised.indexOf('(') + 1, normalised.lastIndexOf(')')).split(',');
	return [
		parseFloat(numbers[0]) || 0,
		parseFloat(numbers[1]) || 0,
		parseFloat(numbers[2]) || 0,
		numbers.length > 3 ? parseFloat(numbers[3]) : 1,
	];
}

function mix(from, to, t) {
	const channel = (i) => Math.round(from[i] + (to[i] - from[i]) * t);
	const alpha = from[3] + (to[3] - from[3]) * t;
	return `rgba(${channel(0)},${channel(1)},${channel(2)},${alpha})`;
}

/* The diverging ramp, flattened to a lookup so colouring an area is an array
 * index rather than an interpolation. Mirrors the 'interpolate' expression in
 * map.js, which likewise blends in sRGB component space. */
function buildRamp(ctx, colours) {
	const negative = parseColour(ctx, colours.negative, '#be123c');
	const middle = parseColour(ctx, colours.mid, '#f8fafc');
	const positive = parseColour(ctx, colours.positive, '#0f766e');

	const ramp = new Array(RAMP_STEPS);
	for (let i = 0; i < RAMP_STEPS; i++) {
		const t = (i / (RAMP_STEPS - 1)) * 2 - 1;
		ramp[i] = t < 0 ? mix(negative, middle, t + 1) : mix(middle, positive, t);
	}
	return ramp;
}

function palette(element) {
	// One style resolution, read ten times — rather than ten separate
	// getComputedStyle calls for the same element
	const style = getComputedStyle(element);
	const token = (name, fallback) => style.getPropertyValue(name).trim() || fallback;

	return {
		water: token('--map-water', '#e4eaf1'),
		line: token('--map-line', 'rgba(255,255,255,0.6)'),
		nodata: token('--map-nodata', '#dde2e9'),
		negative: token('--ramp-neg', '#be123c'),
		mid: token('--ramp-mid', '#f8fafc'),
		positive: token('--ramp-pos', '#0f766e'),
		hover: token('--text', '#0d1117'),
		selected: token('--accent-bright', '#2563eb'),
		place: token('--map-place', '#333b49'),
		placeHalo: token('--map-place-halo', 'rgba(255,255,255,0.85)'),
	};
}

/* ---------- geometry ---------- */

function ringsOf(geometry) {
	if (!geometry) return [];
	if (geometry.type === 'Polygon') return geometry.coordinates;
	if (geometry.type === 'MultiPolygon') {
		const rings = [];
		for (const polygon of geometry.coordinates) rings.push(...polygon);
		return rings;
	}
	return [];
}

/* One feature becomes one Path2D in world pixels, holes included. Filling it
 * even-odd means the winding order of the source rings does not matter, and
 * the hit test below uses the same rule so the two always agree. */
function buildFeature(feature) {
	const path = new Path2D();
	const rings = [];

	let minX = Infinity;
	let minY = Infinity;
	let maxX = -Infinity;
	let maxY = -Infinity;

	for (const ring of ringsOf(feature.geometry)) {
		if (!ring || ring.length < 3) continue;

		const flat = new Float64Array(ring.length * 2);
		for (let i = 0; i < ring.length; i++) {
			const x = worldX(ring[i][0]);
			const y = worldY(ring[i][1]);
			flat[i * 2] = x;
			flat[i * 2 + 1] = y;

			if (x < minX) minX = x;
			if (x > maxX) maxX = x;
			if (y < minY) minY = y;
			if (y > maxY) maxY = y;

			if (i === 0) path.moveTo(x, y);
			else path.lineTo(x, y);
		}
		path.closePath();
		rings.push(flat);
	}

	if (!rings.length) return null;
	return { id: feature.id, path, rings, minX, minY, maxX, maxY };
}

/* Even-odd ray cast across every ring of the feature at once, which handles
 * multipolygons and holes without tracking which is which. */
function containsPoint(feature, x, y) {
	if (x < feature.minX || x > feature.maxX || y < feature.minY || y > feature.maxY) return false;

	let inside = false;
	for (const ring of feature.rings) {
		for (let i = 0, j = ring.length - 2; i < ring.length; j = i, i += 2) {
			const yi = ring[i + 1];
			const yj = ring[j + 1];
			if ((yi > y) === (yj > y)) continue;

			const xi = ring[i];
			const xj = ring[j];
			if (x < xi + ((y - yi) / (yj - yi)) * (xj - xi)) inside = !inside;
		}
	}
	return inside;
}

/* ---------- place labels ---------- */

/* Mirrors the ['step', ['zoom'], 0, 6, 1, 7, 2, 8, 3, 9, 4] filter in map.js:
 * only the largest cities are eligible at national zoom, towns appear as the
 * view tightens. */
function rankCutoff(zoom) {
	if (zoom < 6) return 0;
	if (zoom < 7) return 1;
	if (zoom < 8) return 2;
	if (zoom < 9) return 3;
	return 4;
}

function interpolate(zoom, stops) {
	if (zoom <= stops[0][0]) return stops[0][1];
	for (let i = 1; i < stops.length; i++) {
		const [z1, v1] = stops[i];
		if (zoom > z1) continue;
		const [z0, v0] = stops[i - 1];
		return v0 + ((v1 - v0) * (zoom - z0)) / (z1 - z0);
	}
	return stops[stops.length - 1][1];
}

const labelSize = (zoom) => interpolate(zoom, [[4, 9.5], [8, 11.5], [11, 13]]);
const dotRadius = (zoom) => interpolate(zoom, [[4, 1.4], [9, 2.6]]);

function overlaps(a, b) {
	return !(a.x1 <= b.x0 || a.x0 >= b.x1 || a.y1 <= b.y0 || a.y0 >= b.y1);
}

/* ---------- public API ---------- */

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

/** Low and high ends of the average-price ramp, trimming the nine most extreme
 *  areas at each end for the same reason colourBound does. Prices are far more
 *  skewed than changes are: Kensington and Chelsea alone sits high enough above
 *  the rest of the country to flatten every other area to the same pale tint. */
export function priceBounds(values) {
	const finite = [];
	for (const value of values) {
		if (Number.isFinite(value)) finite.push(value);
	}
	if (finite.length === 0) return null;

	finite.sort((a, b) => a - b);
	// Nine each end at the 360 areas the data actually has, but scaled down for
	// a short list: trimming nine from each end of twenty would leave the ramp
	// spanning the middle two areas alone.
	const trim = Math.min(9, Math.floor(finite.length / 20));
	const lo = finite[trim];
	const hi = finite[finite.length - 1 - trim];

	return hi > lo ? { lo, hi } : { lo, hi: lo + 1 };
}

export function createMap(container, { onSelect, describe, onContextLost }) {
	const root = typeof container === 'string' ? document.getElementById(container) : container;

	const canvas = document.createElement('canvas');
	canvas.className = 'map-canvas';
	root.appendChild(canvas);
	const ctx = canvas.getContext('2d');

	if (!root.hasAttribute('tabindex')) root.setAttribute('tabindex', '0');

	const tooltip = document.createElement('div');
	tooltip.className = 'map-tooltip';
	root.appendChild(tooltip);

	const hint = document.createElement('div');
	hint.className = 'map-gesture-hint';
	root.appendChild(hint);

	const controls = buildControls();
	root.appendChild(controls.element);

	let colours = palette(document.documentElement);
	let ramp = buildRamp(ctx, colours);

	let features = [];
	let featureById = [];
	let places = [];
	let fillStyles = [];
	let bounds = null;

	let width = 0;
	let height = 0;
	let dpr = 1;

	let zoom = MIN_ZOOM;
	let centre = { x: worldX(0), y: worldY(54) };
	let fitted = false;
	// { values, mode } — the mode is kept alongside so a theme change repaints
	// the map the reader is actually looking at, not always the change ramp
	let lastValues = null;
	let lastLabelSize = 0;

	let ready = false;
	let pending = null;          // { values, mode } held until the geometry loads
	let lastDomain = null;
	let hovered = null;
	let selected = null;
	const readyCallbacks = [];

	let frame = null;
	let animation = null;
	let hintTimer = null;
	const textCache = new Map();

	/* ---------- sizing and drawing ---------- */

	function measure() {
		const rect = root.getBoundingClientRect();
		const nextWidth = Math.max(1, Math.round(rect.width));
		const nextHeight = Math.max(1, Math.round(rect.height));
		const nextDpr = Math.min(window.devicePixelRatio || 1, 2);

		if (nextWidth === width && nextHeight === height && nextDpr === dpr) return false;

		width = nextWidth;
		height = nextHeight;
		dpr = nextDpr;
		canvas.width = Math.round(width * dpr);
		canvas.height = Math.round(height * dpr);
		canvas.style.width = `${width}px`;
		canvas.style.height = `${height}px`;
		return true;
	}

	const scaleAt = (z) => 2 ** (z - REF_ZOOM);

	function toScreen(x, y, k) {
		return { x: (x - centre.x) * k + width / 2, y: (y - centre.y) * k + height / 2 };
	}

	function toWorld(px, py) {
		const k = scaleAt(zoom);
		return { x: (px - width / 2) / k + centre.x, y: (py - height / 2) / k + centre.y };
	}

	/* Keep the data in view. MapLibre would happily let the UK be dragged off
	 * into empty space, which with no basemap underneath leaves nothing at all
	 * on screen and no obvious way back. */
	function clampCentre() {
		if (!bounds) return;
		const k = scaleAt(zoom);
		const marginX = (width / 2 / k) * 0.75;
		const marginY = (height / 2 / k) * 0.75;
		centre.x = clamp(centre.x, bounds.minX - marginX, bounds.maxX + marginX);
		centre.y = clamp(centre.y, bounds.minY - marginY, bounds.maxY + marginY);
	}

	function invalidate() {
		if (frame !== null) return;
		frame = requestAnimationFrame(() => {
			frame = null;
			draw();
		});
	}

	function draw() {
		measure();
		clampCentre();

		const k = scaleAt(zoom);

		ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
		ctx.fillStyle = colours.water;
		ctx.fillRect(0, 0, width, height);

		if (!features.length) return;

		const halfW = width / 2 / k;
		const halfH = height / 2 / k;
		const viewMinX = centre.x - halfW;
		const viewMaxX = centre.x + halfW;
		const viewMinY = centre.y - halfH;
		const viewMaxY = centre.y + halfH;

		const visible = [];
		for (const feature of features) {
			if (feature.maxX < viewMinX || feature.minX > viewMaxX) continue;
			if (feature.maxY < viewMinY || feature.minY > viewMaxY) continue;
			visible.push(feature);
		}

		// Paths are held in world pixels, so the view is applied to the context
		// rather than to the geometry — nothing is rebuilt as the map moves.
		ctx.setTransform(k * dpr, 0, 0, k * dpr, (width / 2 - centre.x * k) * dpr, (height / 2 - centre.y * k) * dpr);

		for (const feature of visible) {
			ctx.fillStyle = fillStyles[feature.id] || colours.nodata;
			ctx.fill(feature.path, 'evenodd');
		}

		ctx.lineJoin = 'round';
		ctx.strokeStyle = colours.line;
		ctx.lineWidth = OUTLINE_WIDTH / k;
		for (const feature of visible) ctx.stroke(feature.path);

		// Drawn after every fill so a highlight is never painted over by a
		// neighbour, matching the layer order in map.js
		if (hovered !== null && featureById[hovered]) {
			ctx.strokeStyle = colours.hover;
			ctx.lineWidth = HOVER_WIDTH / k;
			ctx.stroke(featureById[hovered].path);
		}

		if (selected !== null && featureById[selected]) {
			ctx.strokeStyle = colours.selected;
			ctx.lineWidth = SELECTED_WIDTH / k;
			ctx.stroke(featureById[selected].path);
		}

		ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
		drawPlaces(k);
	}

	function textLayout(name, size, maxWidth) {
		const key = `${size}|${name}`;
		const cached = textCache.get(key);
		if (cached) return cached;

		const words = name.split(' ');
		const lines = [];
		let line = '';

		for (const word of words) {
			const candidate = line ? `${line} ${word}` : word;
			if (line && ctx.measureText(candidate).width > maxWidth) {
				lines.push(line);
				line = word;
			} else {
				line = candidate;
			}
		}
		if (line) lines.push(line);

		let widest = 0;
		for (const entry of lines) widest = Math.max(widest, ctx.measureText(entry).width);

		const layout = { lines, width: widest, height: lines.length * size * 1.2 };
		textCache.set(key, layout);
		return layout;
	}

	function drawPlaces(k) {
		if (!places.length) return;

		const cutoff = rankCutoff(zoom);
		// Quantised so a continuous zoom reuses measurements instead of
		// producing a new cache key on every frame
		const size = Math.round(labelSize(zoom) * 2) / 2;
		const radius = dotRadius(zoom);

		if (size !== lastLabelSize) {
			textCache.clear();
			lastLabelSize = size;
		}

		ctx.font = `${size}px Inter, system-ui, sans-serif`;
		ctx.textAlign = 'center';
		ctx.textBaseline = 'top';

		const candidates = [];
		for (const place of places) {
			if (place.rank > cutoff) continue;
			const point = toScreen(place.x, place.y, k);
			if (point.x < -80 || point.x > width + 80 || point.y < -40 || point.y > height + 40) continue;
			candidates.push({ place, x: point.x, y: point.y });
			if (candidates.length >= MAX_LABEL_CANDIDATES) break;
		}
		if (!candidates.length) return;

		// Population order, so the bigger settlement wins a collision
		candidates.sort((a, b) => a.place.sort - b.place.sort);

		ctx.fillStyle = colours.place;
		ctx.strokeStyle = colours.placeHalo;
		ctx.lineWidth = 0.8;
		for (const candidate of candidates) {
			ctx.beginPath();
			ctx.arc(candidate.x, candidate.y, radius, 0, Math.PI * 2);
			ctx.globalAlpha = 0.8;
			ctx.fill();
			ctx.globalAlpha = 1;
			ctx.stroke();
		}

		// Dots are reserved first so a label never lands on top of one
		const boxes = candidates.map((candidate) => ({
			x0: candidate.x - radius - 1,
			y0: candidate.y - radius - 1,
			x1: candidate.x + radius + 1,
			y1: candidate.y + radius + 1,
		}));

		const offset = size * LABEL_OFFSET_EMS;

		for (const candidate of candidates) {
			const layout = textLayout(candidate.place.name, size, size * LABEL_MAX_EMS);
			const halfW = layout.width / 2;
			const halfH = layout.height / 2;

			// Trying the other side of the dot before giving up places
			// noticeably more labels at national zoom, where the likes of
			// Glasgow and Edinburgh sit close enough to fight over the space
			let chosen = null;
			for (const anchor of LABEL_ANCHORS) {
				let cx = candidate.x;
				let cy = candidate.y;

				if (anchor === 'top') cy = candidate.y + offset + halfH;
				else if (anchor === 'bottom') cy = candidate.y - offset - halfH;
				else if (anchor === 'left') cx = candidate.x + offset + halfW;
				else cx = candidate.x - offset - halfW;

				const box = {
					x0: cx - halfW - LABEL_PADDING,
					y0: cy - halfH - LABEL_PADDING,
					x1: cx + halfW + LABEL_PADDING,
					y1: cy + halfH + LABEL_PADDING,
				};

				let blocked = false;
				for (const other of boxes) {
					if (overlaps(box, other)) { blocked = true; break; }
				}
				if (blocked) continue;

				chosen = { box, cx, top: cy - halfH, layout };
				break;
			}

			if (!chosen) continue;
			boxes.push(chosen.box);

			ctx.strokeStyle = colours.placeHalo;
			ctx.lineWidth = HALO_WIDTH * 2;
			ctx.fillStyle = colours.place;

			let y = chosen.top;
			for (const line of chosen.layout.lines) {
				ctx.strokeText(line, chosen.cx, y);
				ctx.fillText(line, chosen.cx, y);
				y += size * 1.2;
			}
		}
	}

	/* ---------- state ---------- */

	function ensureFit() {
		if (fitted || !bounds) return;
		measure();
		if (width <= 1 || height <= 1) return;
		fitted = true;
		fitBounds();
	}

	function fitBounds() {
		if (!bounds) return;
		measure();

		const west = worldX(UK_BOUNDS[0][0]);
		const east = worldX(UK_BOUNDS[1][0]);
		const north = worldY(UK_BOUNDS[1][1]);
		const south = worldY(UK_BOUNDS[0][1]);

		const usableW = Math.max(1, width - FIT_PADDING * 2);
		const usableH = Math.max(1, height - FIT_PADDING * 2);
		const k = Math.min(usableW / (east - west), usableH / (south - north));

		zoom = clamp(REF_ZOOM + Math.log2(k), MIN_ZOOM, MAX_ZOOM);
		centre = { x: (west + east) / 2, y: (north + south) / 2 };
	}

	/* Returns the domain the values were scaled against, which is what the
	 * legend is labelled from: symmetric about zero for the change map, and the
	 * trimmed price range for the average-price map. Both end up indexing the
	 * same 256-entry ramp — 'price' simply never reaches its negative half. */
	function paint(values, mode) {
		const sequential = mode === 'price';
		const domain = sequential
			? priceBounds(values) || { lo: 0, hi: 1 }
			: (() => {
				const bound = colourBound(values);
				return { lo: -bound, hi: bound };
			})();

		const span = domain.hi - domain.lo;
		const nodata = colours.nodata;

		for (let area = 0; area < values.length; area++) {
			const value = values[area];
			if (!Number.isFinite(value)) {
				fillStyles[area] = nodata;
				continue;
			}

			const normalised = sequential
				? SEQ_FLOOR + (1 - SEQ_FLOOR) * clamp((value - domain.lo) / span, 0, 1)
				: clamp(value / domain.hi, -1, 1);

			fillStyles[area] = ramp[Math.round(((normalised + 1) / 2) * (RAMP_STEPS - 1))];
		}

		lastDomain = { mode, lo: domain.lo, hi: domain.hi };
		invalidate();
		return lastDomain;
	}

	function markReady() {
		if (ready) return;
		ready = true;

		let domain = null;
		if (pending) {
			domain = paint(pending.values, pending.mode);
			pending = null;
		}
		invalidate();

		while (readyCallbacks.length) readyCallbacks.shift()(domain);
	}

	function setHover(area) {
		if (hovered === area) return;
		hovered = area;
		invalidate();
	}

	/* ---------- loading ---------- */

	async function load() {
		const response = await fetch('data/lads.geojson');
		if (!response.ok) throw new Error(`lads.geojson: ${response.status}`);
		const collection = await response.json();

		let minX = Infinity;
		let minY = Infinity;
		let maxX = -Infinity;
		let maxY = -Infinity;

		for (const feature of collection.features) {
			const built = buildFeature(feature);
			if (!built) continue;
			features.push(built);
			featureById[built.id] = built;

			if (built.minX < minX) minX = built.minX;
			if (built.maxX > maxX) maxX = built.maxX;
			if (built.minY < minY) minY = built.minY;
			if (built.maxY > maxY) maxY = built.maxY;
		}

		bounds = { minX, minY, maxX, maxY };
		ensureFit();
		markReady();
	}

	/* Labels are a bonus, never a blocker: a failure here costs the place names
	 * but must not stop the choropleth appearing. */
	async function loadPlaces() {
		try {
			const response = await fetch('data/places.geojson');
			if (!response.ok) throw new Error(`places.geojson: ${response.status}`);
			const collection = await response.json();

			places = collection.features.map((feature) => ({
				x: worldX(feature.geometry.coordinates[0]),
				y: worldY(feature.geometry.coordinates[1]),
				name: feature.properties.n,
				rank: feature.properties.r,
				sort: feature.properties.s,
			}));
			invalidate();
		} catch (error) {
			console.error('Place labels unavailable:', error && error.message ? error.message : error);
		}
	}

	load().catch((error) => {
		console.error('Map error:', error && error.message ? error.message : error);
		if (onContextLost) onContextLost();
	});

	// Deferred behind the boundaries: the choropleth is the thing worth
	// showing first, and the labels are useless without it anyway.
	if ('requestIdleCallback' in window) requestIdleCallback(() => loadPlaces(), { timeout: 2000 });
	else setTimeout(loadPlaces, 300);

	/* ---------- animation ---------- */

	function stopAnimation() {
		if (animation !== null) {
			cancelAnimationFrame(animation);
			animation = null;
		}
	}

	function zoomAbout(target, px, py) {
		const next = clamp(target, MIN_ZOOM, MAX_ZOOM);
		const before = toWorld(px, py);
		zoom = next;
		const k = scaleAt(zoom);
		centre.x = before.x - (px - width / 2) / k;
		centre.y = before.y - (py - height / 2) / k;
		clampCentre();
		invalidate();
	}

	function animateZoom(target, px, py) {
		stopAnimation();
		const from = zoom;
		const to = clamp(target, MIN_ZOOM, MAX_ZOOM);
		if (Math.abs(to - from) < 0.001) return;

		const started = performance.now();
		const duration = 260;

		const step = (now) => {
			const t = Math.min(1, (now - started) / duration);
			const eased = 1 - (1 - t) ** 3;
			zoomAbout(from + (to - from) * eased, px, py);
			animation = t < 1 ? requestAnimationFrame(step) : null;
		};
		animation = requestAnimationFrame(step);
	}

	function glide(vx, vy) {
		stopAnimation();
		let lastTime = performance.now();
		let speedX = clamp(vx, -MAX_FLING, MAX_FLING);
		let speedY = clamp(vy, -MAX_FLING, MAX_FLING);

		const step = (now) => {
			const dt = Math.min(64, now - lastTime);
			lastTime = now;

			const k = scaleAt(zoom);
			centre.x -= (speedX * dt) / k;
			centre.y -= (speedY * dt) / k;

			const decay = 0.92 ** (dt / 16);
			speedX *= decay;
			speedY *= decay;

			clampCentre();
			invalidate();

			animation = Math.hypot(speedX, speedY) > 0.02 ? requestAnimationFrame(step) : null;
		};
		animation = requestAnimationFrame(step);
	}

	/* ---------- interaction ---------- */

	function showHint(message) {
		if (hint.classList.contains('is-visible') && hint.textContent === message) return;
		hint.textContent = message;
		hint.classList.add('is-visible');
		clearTimeout(hintTimer);
		hintTimer = setTimeout(() => hint.classList.remove('is-visible'), 1400);
	}

	function featureAt(px, py) {
		const point = toWorld(px, py);
		for (const feature of features) {
			if (containsPoint(feature, point.x, point.y)) return feature.id;
		}
		return null;
	}

	function localPoint(event) {
		const rect = canvas.getBoundingClientRect();
		return { x: event.clientX - rect.left, y: event.clientY - rect.top };
	}

	/* Pointer events carry the mouse and the pen only. Touch is handled through
	 * touch events below, and the two must not be mixed: `touch-action: pan-y`
	 * lets the browser scroll the page with one finger, and the instant it
	 * starts it cancels every pointer in the gesture — so a second finger
	 * arriving after that would find the first one already gone, and a pinch
	 * could never assemble. Touch events also carry `event.touches`, which is
	 * authoritative, rather than a list we would have to keep in step. */
	const isTouch = (event) => event.pointerType === 'touch';

	let drag = null;
	let moved = false;

	canvas.addEventListener('pointerdown', (event) => {
		if (isTouch(event)) return;

		stopAnimation();
		try {
			canvas.setPointerCapture(event.pointerId);
		} catch (error) {
			/* the pointer is already gone; the drag still works without it */
		}
		moved = false;

		const point = localPoint(event);
		drag = { x: point.x, y: point.y, vx: 0, vy: 0, time: performance.now() };
		canvas.style.cursor = 'grabbing';
	});

	canvas.addEventListener('pointermove', (event) => {
		if (isTouch(event)) return;
		const point = localPoint(event);

		if (drag) {
			const k = scaleAt(zoom);
			const dx = point.x - drag.x;
			const dy = point.y - drag.y;
			if (Math.abs(dx) > 2 || Math.abs(dy) > 2) moved = true;

			centre.x -= dx / k;
			centre.y -= dy / k;

			const now = performance.now();
			const elapsed = Math.max(MIN_SAMPLE_MS, now - drag.time);
			drag.vx = clamp(dx / elapsed, -MAX_FLING, MAX_FLING);
			drag.vy = clamp(dy / elapsed, -MAX_FLING, MAX_FLING);
			drag.x = point.x;
			drag.y = point.y;
			drag.time = now;

			clampCentre();
			invalidate();
			return;
		}

		const area = featureAt(point.x, point.y);
		setHover(area);
		canvas.style.cursor = area === null ? '' : 'pointer';

		if (area === null) {
			tooltip.classList.remove('is-visible');
			return;
		}

		// Rebuilt every move, not only when the area changes: the reading it
		// shows depends on the date range and housing type, which the visitor
		// can change without the pointer ever leaving the area.
		tooltip.innerHTML = describe(area);
		tooltip.style.left = `${point.x}px`;
		tooltip.style.top = `${point.y}px`;
		tooltip.classList.add('is-visible');
	});

	function endPointer(event) {
		try {
			if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
		} catch (error) {
			/* nothing to release */
		}

		if (drag) {
			const idle = performance.now() - drag.time > 120;
			const speed = Math.hypot(drag.vx, drag.vy);
			if (!idle && speed > 0.08) glide(drag.vx, drag.vy);
			drag = null;
			canvas.style.cursor = '';
		}
	}

	canvas.addEventListener('pointerup', (event) => {
		if (isTouch(event)) return;
		const wasMoved = moved;
		endPointer(event);

		if (wasMoved) return;
		const point = localPoint(event);
		const area = featureAt(point.x, point.y);
		if (area !== null) onSelect(area);
	});

	canvas.addEventListener('pointercancel', (event) => {
		if (isTouch(event)) return;
		endPointer(event);
	});

	canvas.addEventListener('pointerleave', () => {
		if (drag) return;
		setHover(null);
		tooltip.classList.remove('is-visible');
		canvas.style.cursor = '';
	});

	// Cooperative gestures: a bare scroll belongs to the page, so the map only
	// zooms with a modifier held. A trackpad pinch already arrives as a wheel
	// event with ctrlKey set, so it keeps working untouched.
	canvas.addEventListener('wheel', (event) => {
		if (!event.ctrlKey && !event.metaKey) {
			showHint(`Use ${IS_APPLE ? '⌘' : 'ctrl'} + scroll to zoom the map`);
			return;
		}
		event.preventDefault();
		stopAnimation();

		const point = localPoint(event);
		const scale = event.deltaMode === 1 ? 20 : event.deltaMode === 2 ? height : 1;
		zoomAbout(zoom - (event.deltaY * scale) / 220, point.x, point.y);
	}, { passive: false });

	/* ---------- touch ---------- */

	let pinch = null;
	let tap = null;
	let hinted = false;

	function touchPoint(touch) {
		const rect = canvas.getBoundingClientRect();
		return { x: touch.clientX - rect.left, y: touch.clientY - rect.top };
	}

	function pinchOf(event) {
		const a = touchPoint(event.touches[0]);
		const b = touchPoint(event.touches[1]);
		return {
			x: (a.x + b.x) / 2,
			y: (a.y + b.y) / 2,
			// Floored so a two-finger pan with the fingers together cannot
			// divide by zero on the next move
			distance: Math.max(1, Math.hypot(a.x - b.x, a.y - b.y)),
		};
	}

	canvas.addEventListener('touchstart', (event) => {
		hinted = false;
		if (event.touches.length === 0) return;

		if (event.touches.length < 2) {
			const point = touchPoint(event.touches[0]);
			tap = { x: point.x, y: point.y, time: performance.now(), moved: false };
			return;
		}

		// Claims the gesture before the browser can decide it is a page scroll.
		// Once it has decided, touchmove stops being cancelable and preventing
		// the default there does nothing at all.
		event.preventDefault();
		stopAnimation();
		pinch = { ...pinchOf(event), vx: 0, vy: 0, time: performance.now() };
		tap = null;
	}, { passive: false });

	canvas.addEventListener('touchmove', (event) => {
		if (event.touches.length >= 2) {
			event.preventDefault();

			const next = pinchOf(event);
			if (!pinch) {
				pinch = { ...next, vx: 0, vy: 0, time: performance.now() };
				return;
			}

			// Pan by how far the midpoint travelled, then zoom about where it
			// now is. Applied incrementally rather than against the start of
			// the gesture, so hitting a zoom limit does not bank up a jump.
			const k = scaleAt(zoom);
			const dx = next.x - pinch.x;
			const dy = next.y - pinch.y;
			centre.x -= dx / k;
			centre.y -= dy / k;
			zoomAbout(zoom + Math.log2(next.distance / pinch.distance), next.x, next.y);

			const now = performance.now();
			const elapsed = Math.max(MIN_SAMPLE_MS, now - pinch.time);
			pinch = {
				...next,
				vx: clamp(dx / elapsed, -MAX_FLING, MAX_FLING),
				vy: clamp(dy / elapsed, -MAX_FLING, MAX_FLING),
				time: now,
			};
			return;
		}

		if (!tap || event.touches.length === 0) return;

		const point = touchPoint(event.touches[0]);
		const dx = point.x - tap.x;
		const dy = point.y - tap.y;
		if (Math.abs(dx) > TAP_SLOP || Math.abs(dy) > TAP_SLOP) tap.moved = true;

		// Only explain the gesture when the finger was heading sideways. A
		// vertical swipe is a page scroll, the page scrolling is exactly what
		// should happen, and throwing an overlay across the map every time one
		// passes over it is noise rather than help. Once per touch, at most.
		if (!hinted && Math.abs(dx) > HINT_SLOP && Math.abs(dx) > Math.abs(dy)) {
			hinted = true;
			showHint('Use two fingers to move the map');
		}
	}, { passive: false });

	function endTouch(event) {
		if (pinch && event.touches.length < 2) {
			const { vx, vy, time } = pinch;
			pinch = null;
			if (performance.now() - time < 120 && Math.hypot(vx, vy) > 0.08) glide(vx, vy);
		}

		if (event.touches.length > 0) return;

		const finished = tap;
		tap = null;
		hinted = false;

		// A tap selects, the same as a click does. MapLibre raised a click for
		// this and the area panel is otherwise only reachable by dropdown.
		if (event.type !== 'touchend' || !finished || finished.moved) return;
		if (performance.now() - finished.time > TAP_TIMEOUT) return;

		const area = featureAt(finished.x, finished.y);
		if (area !== null) onSelect(area);
	}

	canvas.addEventListener('touchend', endTouch);
	canvas.addEventListener('touchcancel', endTouch);

	canvas.addEventListener('dblclick', (event) => {
		event.preventDefault();
		const point = localPoint(event);
		animateZoom(zoom + 1, point.x, point.y);
	});

	root.addEventListener('keydown', (event) => {
		const step = event.shiftKey ? 200 : 80;
		const k = scaleAt(zoom);
		let handled = true;

		switch (event.key) {
			case 'ArrowLeft': centre.x -= step / k; break;
			case 'ArrowRight': centre.x += step / k; break;
			case 'ArrowUp': centre.y -= step / k; break;
			case 'ArrowDown': centre.y += step / k; break;
			case '+':
			case '=': animateZoom(zoom + 1, width / 2, height / 2); return;
			case '-':
			case '_': animateZoom(zoom - 1, width / 2, height / 2); return;
			default: handled = false;
		}

		if (!handled) return;
		event.preventDefault();
		clampCentre();
		invalidate();
	});

	controls.zoomIn.addEventListener('click', () => animateZoom(zoom + 1, width / 2, height / 2));
	controls.zoomOut.addEventListener('click', () => animateZoom(zoom - 1, width / 2, height / 2));

	/* The opening fit needs a laid-out element, and ResizeObserver is what
	 * reports one. Later resizes hold the current centre and zoom instead, so
	 * a panel reflow never throws away where the visitor had navigated to. */
	new ResizeObserver(() => {
		if (!measure()) return;
		ensureFit();
		invalidate();
	}).observe(root);

	window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
		colours = palette(document.documentElement);
		ramp = buildRamp(ctx, colours);
		textCache.clear();
		// Areas hold a resolved colour string, so the ramp has to be reapplied
		if (ready && lastValues) paint(lastValues.values, lastValues.mode);
		invalidate();
	});

	return {
		/** Runs once the geometry is loaded and colours will stick. */
		whenReady(callback) {
			if (ready) callback(lastDomain);
			else readyCallbacks.push(callback);
		},

		/** Recolour every area. `mode` is 'change' for the diverging ramp about
		 *  zero, or 'price' for the sequential one. Returns the domain the
		 *  values were scaled against, or null if the geometry is not in yet. */
		setValues(values, mode = 'change') {
			lastValues = { values, mode };
			if (!ready) {
				pending = { values, mode };
				return null;
			}
			return paint(values, mode);
		},

		setSelected(area) {
			selected = area;
			invalidate();
		},
	};
}

function buildControls() {
	const element = document.createElement('div');
	element.className = 'map-ctrl';

	const button = (label, symbol) => {
		const node = document.createElement('button');
		node.type = 'button';
		node.setAttribute('aria-label', label);
		node.textContent = symbol;
		element.appendChild(node);
		return node;
	};

	return {
		element,
		zoomIn: button('Zoom in', '+'),
		zoomOut: button('Zoom out', '−'),
	};
}
