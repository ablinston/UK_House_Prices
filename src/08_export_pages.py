exec(open('global.py').read())


####################
# Build a static page for every area that has no boundary on the map
#
# Written to web/house-prices/:
#   index.html          the UK, and the directory of everywhere else
#   <slug>/index.html   one per country, region and county
#
# These are read by a search engine before they are read by anyone else. The
# map answers 'how have prices changed' brilliantly and says nothing a crawler
# can index, so the site has one rankable URL and no way to appear for the
# thousands of searches the data already answers. A page per area is the fix.
#
# The figures come out of web/data rather than out of the parquet, so a page
# and the tool it links into cannot disagree - a visitor who reads 'down 7% in
# real terms' and then sees something else on the map has been told a lie by
# one of the two, and there would be no way to tell which.

print('Step 08: Export area pages')

OUT_DIR = 'web/house-prices'
SITE = 'https://realhouseprices.uk'

# Horizons shown in the change table, as (label, months back). 'None' means the
# area's own first observation, which is January 1995 for everywhere here.
#
# These are the windows people actually search on - '[county] house prices last
# 10 years' is a live suggestion, '[county] house prices since 2007' returns no
# suggestions at all. An earlier version of this file quoted September 2007 as
# 'the peak' on every page, which was a national figure borrowed for areas it
# did not describe: only three of the forty-three peak that month in real terms,
# and the UK itself peaks in 2021. Each area's own peak is computed below.
HORIZONS = [('1 year', 12),
            ('5 years', 60),
            ('10 years', 120),
            ('15 years', 180),
            (None, None)]          # open ended: back to this series' own start

# The window every area is ranked and compared over. It has to be the same one
# for everybody or the ranking compares different decades with each other.
COMMON_WINDOW = 120

# Which tier a series belongs to, read off the ONS code. Used for the heading,
# the directory grouping, and for ranking an area against its own kind rather
# than against everything on the site at once.
TIERS = {'K02': 'the United Kingdom',
         'E92': 'country', 'W92': 'country', 'S92': 'country', 'N92': 'country',
         'E12': 'region',
         'E10': 'county', 'E11': 'county', 'E13': 'county'}


####################
# Load the exported data back in

meta = j.load(open('web/data/meta.json'))

scale = meta['scale']
areas = meta['areas']
geo_areas = meta['geoAreas']
n_areas = len(areas)
n_months = meta['months']['count']
types = meta['types']

cpi = np.array(meta['cpi'], dtype = np.float64)
base = np.array(meta['base'], dtype = np.float64)

matrix = np.zeros((len(types), n_areas, n_months), dtype = np.uint16)
for t in range(len(types)):
    raw = open(f'web/data/prices-{t}.bin', 'rb').read()
    matrix[t] = np.frombuffer(raw, dtype = '<u2').reshape(n_areas, n_months)

# Absolute prices, with the missing-data sentinel turned into NaN so that it
# propagates through every ratio below instead of quietly reading as zero
nominal = base[:, :, None] * matrix / scale
nominal[matrix == 0] = np.nan

# Deflated to the month step 06 rebased the CPI series on - the latest month of
# CPI data, which is 'cpiBase' - by dividing straight through, as data.js does.
# An earlier version re-based on the last month of price data instead, which
# runs a month behind the CPI, so every real price here sat a fraction of a
# percent away from the same price on the map. The two have to agree.
real = nominal / cpi[None, None, :]
CPI_BASE = meta['cpiBase']

start_year, start_month = (int(v) for v in meta['months']['start'].split('-'))
month_labels = []
for i in range(n_months):
    total = start_year * 12 + (start_month - 1) + i
    month_labels.append(f'{total // 12}-{total % 12 + 1:02d}')

MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
               'August', 'September', 'October', 'November', 'December']


def month_index(label):
    return month_labels.index(label)


def pretty_month(label):
    year, month = label.split('-')
    return f'{MONTH_NAMES[int(month) - 1]} {year}'


LATEST = n_months - 1
LATEST_LABEL = pretty_month(month_labels[LATEST])
FIRST_LABEL = pretty_month(month_labels[0])


####################
# Small helpers

def slugify(name):
    out = []
    for ch in name.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in ' -/':
            out.append('-')
    # Collapse the runs a name like 'Armagh City, Banbridge and Craigavon' makes
    slug = '-'.join(part for part in ''.join(out).split('-') if part)
    return slug


def esc(text):
    return (str(text).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


def money(value):
    return '-' if not np.isfinite(value) else f'£{round(value):,}'


def pct(value, places = 1):
    if not np.isfinite(value):
        return '-'
    return f'{value:+.{places}f}%'


def change(series, area, frm, to):
    """Percentage change between two months, or NaN if either is missing."""
    a, b = series[area, frm], series[area, to]
    if not np.isfinite(a) or not np.isfinite(b) or a == 0:
        return float('nan')
    return (b / a - 1) * 100


def tier_of(code):
    return TIERS.get(code[:3], 'area')


def first_observation(area, t):
    """The first month this area has a price for this housing type.

    Not always the start of the axis. Northern Ireland, Scotland and the UK
    itself publish an overall index back to 1995 but no breakdown by property
    type until 2004 or 2005. Reading the open-ended row off month zero anyway
    printed 'Since 1995, from January 1995' above a pair of dashes, which reads
    as a page that is broken rather than as data nobody ever collected.
    """
    observed = np.flatnonzero(np.isfinite(nominal[t][area]))
    return int(observed[0]) if observed.size else None


def plural(word, count = 2):
    """'county' to 'counties', 'region' to 'regions'."""
    if count == 1:
        return word
    return word[:-1] + 'ies' if word.endswith('y') else word + 's'


def type_label(t):
    """'SemiDetached' is how the Land Registry columns are spelled, and is not
    how anyone says it."""
    return 'Semi-detached' if types[t] == 'SemiDetached' else types[t]


def real_peak(area, t = 0):
    """The month this area's real prices were highest, and how far below it
    they are now.

    Worth saying per area rather than per country: 'when did house prices peak'
    is a question people ask, and the honest answer is different in Surrey
    (2016) from the South East (2021) from the North East (2007). Nobody else
    publishes it area by area, which is most of why it is here.
    """
    series = real[t][area]
    if np.all(np.isnan(series)):
        return None
    at = int(np.nanargmax(series))
    latest = series[LATEST]
    if not np.isfinite(latest) or not np.isfinite(series[at]) or series[at] == 0:
        return None
    return at, (latest / series[at] - 1) * 100


def located(area):
    """Where the area is, said in full.

    Every English county on this site shares its name with somewhere abroad -
    Surrey and Kent have Canadian namesakes, Essex has one in Ontario and
    another in Vermont - and Google's own suggestions for 'house prices in
    surrey' are split between them. Naming the country in the copy, and the UK
    in the title, is what settles which one the page is about.
    """
    name = areas[area]['n']
    tier = tier_of(areas[area]['c'])
    if tier == 'county':
        return f'{name}, England'
    if tier == 'region':
        return (f'the {name} of England' if name.endswith('Region')
                else f'the {name} region of England')
    return name


####################
# Which areas get a page

# The local authorities are deliberately left out of this first batch. County
# and region names are what people actually type - 'house prices in Surrey', not
# 'house prices in Mole Valley' - and the portals have those town and postcode
# queries sewn up while leaving counties almost untouched. Forty-odd substantial
# pages also cannot be mistaken for the bulk-generated location pages Google
# demotes, which 360 of them could be before the template has proved itself.
page_areas = list(range(geo_areas, n_areas))

uk_area = next(i for i in page_areas if areas[i]['c'] == 'K02000001')
page_areas.remove(uk_area)

slugs = {}
for i in page_areas:
    slug = slugify(areas[i]['n'])
    if slug in slugs.values():
        raise SystemExit(f'  slug collision on {slug!r} - two areas would share a URL')
    slugs[i] = slug

groups = [('Countries', [i for i in page_areas if tier_of(areas[i]['c']) == 'country']),
          ('Regions of England', [i for i in page_areas if tier_of(areas[i]['c']) == 'region']),
          ('Counties', [i for i in page_areas if tier_of(areas[i]['c']) == 'county'])]

print(f'  {len(page_areas) + 1} pages: the UK, '
      + ', '.join(f'{len(members)} {title.lower()}' for title, members in groups))


####################
# The pieces every page is built from

def head(title, description, path, heading):
    """The document head, down to the opening of the article.

    Every page carries the same canonical, Open Graph and breadcrumb treatment;
    the only thing that varies is the area, so it is built once here rather than
    drifting between 43 copies.
    """
    url = f'{SITE}{path}'
    crumbs = [{'@type': 'ListItem', 'position': 1, 'name': 'Real House Prices',
               'item': f'{SITE}/'},
              {'@type': 'ListItem', 'position': 2, 'name': 'House prices by area',
               'item': f'{SITE}/house-prices/'}]
    if path != '/house-prices/':
        crumbs.append({'@type': 'ListItem', 'position': 3, 'name': heading,
                       'item': url})

    breadcrumb = j.dumps({'@context': 'https://schema.org',
                          '@type': 'BreadcrumbList',
                          'itemListElement': crumbs}, indent = 2)

    return f'''<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<link rel="canonical" href="{url}">
<meta name="description" content="{esc(description)}">
<meta name="color-scheme" content="light dark">

<meta property="og:type" content="article">
<meta property="og:url" content="{url}">
<meta property="og:site_name" content="Real House Prices">
<meta property="og:locale" content="en_GB">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta name="twitter:card" content="summary_large_image">

<link rel="preload" href="/vendor/fonts/inter-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/css/style.css">

<script type="application/ld+json">
{breadcrumb}
</script>
</head>
<body>

<header class="topbar">
  <div class="topbar-inner">
    <a class="brand" href="/">
      <span class="brand-mark" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 20h18"></path>
          <path d="M6 20V11l6-5 6 5v9"></path>
          <path d="M10 20v-5h4v5"></path>
        </svg>
      </span>
      <span class="brand-text">
        <span class="brand-name">RealHousePrices.uk</span>
        <span class="brand-sub">Local house prices</span>
      </span>
    </a>
    <div class="topbar-right">
      <nav class="topbar-nav"><a href="/house-prices/">House prices by area</a></nav>
    </div>
  </div>
</header>
'''


def footer():
    """The licence notice, which has to travel onto every page rather than sit
    on the homepage alone - the OGL and CC BY both require it wherever the data
    is shown, and these pages are where most people will meet it."""
    return f'''
<footer class="site-footer">
  <div class="footer-inner">
    <p>
      Contains HM Land Registry, ONS and OS data &copy; Crown copyright and database right 2025&ndash;2026.
      UK House Price Index produced by HM Land Registry, ONS, Registers of Scotland and
      Land &amp; Property Services Northern Ireland. Licensed under the
      <a href="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/" rel="noopener">Open Government Licence v3.0</a>.
    </p>
    <p>Figures updated {esc(LATEST_LABEL)}. Inflation adjustment uses ONS CPI, all items.</p>
  </div>
</footer>

</body>
</html>
'''


def series_attr(values):
    """A series as one attribute value: whole pounds, comma separated, and an
    empty field where there is no observation. Read back by the hover readout
    and the data table, which is why it has to be the same numbers the lines
    were drawn from and not a second rendering of them."""
    return ','.join('' if not np.isfinite(v) else str(round(v)) for v in values)


def sparkline(area, t = 0):
    """Real and nominal average price, 1995 to the latest month.

    Drawn here rather than in the browser: the chart is the substance of the
    page, and a page whose substance arrives only after a script has run is a
    page Google may index without it. Colours come from the same tokens the rest
    of the site uses, so it follows the visitor's theme like everything else.

    The figures the lines were drawn from travel with the figure as attributes,
    so the script on the page can put a month's values under the pointer
    without a fetch and the data table can show exactly what was plotted.
    The legend doubles as the readout: with the script off it shows the latest
    month, which is a complete caption rather than an empty one.
    """
    W, H = 720, 260
    PAD_L, PAD_R, PAD_T, PAD_B = 58, 12, 14, 26

    series = {'real': real[t][area], 'nominal': nominal[t][area]}
    finite = np.concatenate([s[np.isfinite(s)] for s in series.values()])
    if not finite.size:
        return ''

    top = float(finite.max()) * 1.06
    plot_w = W - PAD_L - PAD_R
    plot_h = H - PAD_T - PAD_B

    def x(i):
        return PAD_L + (i / (n_months - 1)) * plot_w

    def y(v):
        return PAD_T + plot_h - (v / top) * plot_h

    paths = {}
    for key, values in series.items():
        points = [f'{x(i):.1f},{y(v):.1f}'
                  for i, v in enumerate(values) if np.isfinite(v)]
        paths[key] = 'M' + ' L'.join(points) if points else ''

    # Four gridlines, rounded to something a reader would actually say
    step = 10 ** (len(str(int(top // 4))) - 1)
    tick = max(step, round(top / 4 / step) * step)
    ticks = [t for t in np.arange(tick, top, tick)][:4]

    grid = ''.join(
        f'<line class="pg-grid" x1="{PAD_L}" x2="{W - PAD_R}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>'
        f'<text class="pg-tick" x="{PAD_L - 8}" y="{y(t) + 4:.1f}" text-anchor="end">'
        f'£{round(t / 1000):,}k</text>'
        for t in ticks)

    years = [i for i, label in enumerate(month_labels)
             if label.endswith('-01') and int(label[:4]) % 5 == 0]
    axis = ''.join(
        f'<text class="pg-tick" x="{x(i):.1f}" y="{H - 8}" text-anchor="middle">'
        f'{month_labels[i][:4]}</text>'
        for i in years)

    return f'''<figure class="pg-figure" data-label="{esc(type_label(t))}" data-start="{month_labels[0]}"
        data-real="{series_attr(series['real'])}" data-nominal="{series_attr(series['nominal'])}">
  <svg viewBox="0 0 {W} {H}" role="img" preserveAspectRatio="none"
       data-x0="{PAD_L}" data-x1="{W - PAD_R}"
       aria-label="Average {esc(type_label(t)).lower()} price in {esc(areas[area]['n'])}, real and nominal, {FIRST_LABEL} to {LATEST_LABEL}">
    {grid}{axis}
    <path class="pg-nominal" d="{paths['nominal']}" fill="none"/>
    <path class="pg-real" d="{paths['real']}" fill="none"/>
    <line class="pg-cursor" x1="{x(LATEST):.1f}" x2="{x(LATEST):.1f}" y1="{PAD_T}" y2="{H - PAD_B}" hidden/>
  </svg>
  <figcaption class="pg-legend">
    <span class="pg-key pg-key-real">In today's money
      <b class="pg-key-value" data-series="real">{money(series['real'][LATEST])}</b></span>
    <span class="pg-key pg-key-nominal">Cash price at the time
      <b class="pg-key-value" data-series="nominal">{money(series['nominal'][LATEST])}</b></span>
    <span class="pg-key-month">{esc(LATEST_LABEL)}</span>
  </figcaption>
</figure>'''


def horizon_rows(area, t = 0):
    start = first_observation(area, t)
    rows = []
    for label, back in HORIZONS:
        if back is None:
            if start is None or start >= LATEST - 12:
                continue          # nothing to say beyond the windows above
            frm = start
            label = f'Since {month_labels[frm][:4]}'
        else:
            frm = LATEST - back
        if frm < 0 or (start is not None and frm < start):
            continue
        rows.append((label, pretty_month(month_labels[frm]),
                     change(real[t], area, frm, LATEST),
                     change(nominal[t], area, frm, LATEST)))
    return rows


def verdict(area, t = 0):
    """A sentence saying what the numbers mean, so the page states something
    rather than only displaying something. Assembled from the figures, so it
    restates itself on every refresh instead of going stale."""
    name = areas[area]['n']
    window = LATEST - COMMON_WINDOW
    r = change(real[t], area, window, LATEST)
    n = change(nominal[t], area, window, LATEST)
    years = COMMON_WINDOW // 12
    what = 'home' if t == 0 else f'{type_label(t).lower()} home'

    if not np.isfinite(r) or not np.isfinite(n):
        return (f'{esc(name)} has no complete {what} series over the last '
                f'{years} years.')

    if r < 0:
        opening = (f'Over the last {years} years the average {what} in {esc(name)} '
                   f'has lost <b>{abs(r):.1f}%</b> of its value in real terms, even '
                   f'though the cash price is <b>{n:.1f}% higher</b>.')
    else:
        opening = (f'Over the last {years} years the average {what} in {esc(name)} '
                   f'has gained <b>{r:.1f}%</b> in real terms, on a cash price '
                   f'<b>{n:.1f}% higher</b>.')

    peak = real_peak(area, t)
    if not peak:
        return opening

    at, gap = peak
    if at >= LATEST - 2:
        return opening + (f' Prices there have never been higher in real terms '
                          f'than they are now.')
    return opening + (f' Adjusted for inflation, {what} prices in {esc(name)} peaked in '
                      f'<b>{pretty_month(month_labels[at])}</b> and are '
                      f'<b>{abs(gap):.1f}% below</b> that today.')


def ranking(area, t = 0):
    """Where this area sits among its own kind over the common window.

    Ranking on each area's own peak would compare 2016 with 2022 and call the
    result an ordering, so this uses the same span of months for everybody.
    """
    tier = tier_of(areas[area]['c'])
    peers = [i for i in page_areas if tier_of(areas[i]['c']) == tier]
    if len(peers) < 3:
        return None

    window = LATEST - COMMON_WINDOW
    scored = [(change(real[t], i, window, LATEST), i) for i in peers]
    scored = [(v, i) for v, i in scored if np.isfinite(v)]
    scored.sort(reverse = True)
    order = [i for _, i in scored]
    if area not in order:
        return None
    return order.index(area) + 1, len(order), tier


####################
# The pieces both pages are built from

# Lifted out of the two page builders rather than written once in each. They
# were duplicated, and the transposed change table went into one copy and not
# the other - which is exactly the kind of drift that only shows up when someone
# notices the two pages disagree about what a table looks like.

def type_blocks(area, render):
    """One block per housing type, all in the markup, only the first shown.

    The dropdown toggles between them rather than fetching or rebuilding
    anything, which keeps three things true at once: the page is complete with
    JavaScript switched off, a crawler reads every type rather than only the
    default, and switching is instant because nothing has to be computed. The
    cost is a larger file, which gzip takes most of back - these blocks are
    mostly digits.
    """
    return ''.join(
        f'<div class="pg-type" data-type="{t}"{"" if t == 0 else " hidden"}>'
        f'{render(t)}</div>'
        for t in range(len(types)))


def type_picker():
    options = ''.join(f'<option value="{t}">{esc(type_label(t))}</option>'
                      for t in range(len(types)))
    return (f'<div class="pg-picker">'
            f'<label for="housing-type">Property type</label>'
            f'<div class="select-wrap"><select id="housing-type">{options}</select>'
            f'</div></div>')


def data_toggle():
    """'Show chart data' and the empty region it fills. The table itself is built by
    the script from the figures' attributes rather than written here: with all
    five types it would be four thousand cells of hidden markup on every page,
    for a thing most readers never open. Hidden until the script unhides it,
    since with JavaScript off there is nothing to build the table from and a
    button that does nothing is worse than none. 'data-base' is the month real
    prices are quoted in, which the table heading says in full."""
    return (f'<div class="pg-data">'
            f'<button type="button" class="pg-data-toggle" aria-expanded="false" '
            f'aria-controls="price-data" data-base="{esc(CPI_BASE)}" hidden>Show chart data</button>'
            f'<div class="pg-table-wrap pg-data-table" id="price-data" hidden></div>'
            f'</div>')


def type_script():
    """Three things, none of which the page needs to be complete.

    The select only decides which type is on show; every type is already in the
    markup, so with JavaScript off it does nothing and the page stays on
    Overall. The hover readout puts the month under the pointer into the legend,
    which otherwise keeps showing the latest month. And 'Show chart data' lays the
    numbers carried on the selected type's figure out as a table, latest month
    first, rebuilt if the type changes while it is open.
    """
    return '''
<script>
(function () {
  var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
    'August', 'September', 'October', 'November', 'December'];

  function money(v) { return v === '' ? '-' : '£' + Number(v).toLocaleString('en-GB'); }

  function monthName(start, i) {
    var parts = start.split('-');
    var total = Number(parts[0]) * 12 + (Number(parts[1]) - 1) + i;
    return MONTHS[total % 12] + ' ' + Math.floor(total / 12);
  }

  var select = document.getElementById('housing-type');
  var blocks = document.querySelectorAll('.pg-type');
  var rows = document.querySelectorAll('[data-type-row]');
  var figures = Array.prototype.slice.call(document.querySelectorAll('.pg-figure'));

  /* Hovering the chart. The x axis is linear in month index and the SVG is
   * stretched to fit its box, so the month under the pointer is a proportion of
   * the plot width and nothing more; the values come off the figure's own
   * attributes. A mouse leaving the chart puts the latest month back; a finger
   * lifting off leaves its month showing, since there is nothing else on a
   * phone to hold the readout on. */
  figures.forEach(function (figure) {
    var svg = figure.querySelector('svg');
    var cursor = svg.querySelector('.pg-cursor');
    var real = figure.dataset.real.split(',');
    var nominal = figure.dataset.nominal.split(',');
    var out = {
      real: figure.querySelector('[data-series="real"]'),
      nominal: figure.querySelector('[data-series="nominal"]'),
      month: figure.querySelector('.pg-key-month')
    };
    var x0 = Number(svg.dataset.x0);
    var x1 = Number(svg.dataset.x1);
    var width = svg.viewBox.baseVal.width;
    var last = real.length - 1;

    function show(i) {
      out.month.textContent = monthName(figure.dataset.start, i);
      out.real.textContent = money(real[i]);
      out.nominal.textContent = money(nominal[i]);
      var x = (x0 + (i / last) * (x1 - x0)).toFixed(1);
      cursor.setAttribute('x1', x);
      cursor.setAttribute('x2', x);
      figure.classList.toggle('is-hover', i !== last);
    }

    function track(event) {
      var box = svg.getBoundingClientRect();
      var vx = ((event.clientX - box.left) / box.width) * width;
      var i = Math.round(((vx - x0) / (x1 - x0)) * last);
      show(Math.max(0, Math.min(last, i)));
    }

    svg.addEventListener('pointerdown', track);
    svg.addEventListener('pointermove', track);
    svg.addEventListener('pointerleave', function (event) {
      if (event.pointerType !== 'touch') show(last);
    });
  });

  /* The data table, for whichever type is on show. Latest month first, since
   * that is the end anyone opening it is looking for. */
  var toggle = document.querySelector('.pg-data-toggle');
  var table = document.getElementById('price-data');

  function figureFor(type) {
    var block = document.querySelector('.pg-type[data-type="' + type + '"] .pg-figure');
    return block || null;
  }

  function renderTable() {
    var figure = figureFor(select ? select.value : '0');
    if (!figure) { table.innerHTML = ''; return; }
    var real = figure.dataset.real.split(',');
    var nominal = figure.dataset.nominal.split(',');
    var body = '';
    for (var i = real.length - 1; i >= 0; i--) {
      if (real[i] === '' && nominal[i] === '') continue;
      body += '<tr><th scope="row">' + monthName(figure.dataset.start, i) + '</th>' +
        '<td class="pg-num">' + money(nominal[i]) + '</td>' +
        '<td class="pg-num">' + money(real[i]) + '</td></tr>';
    }
    table.innerHTML = '<table class="pg-table"><caption class="visually-hidden">Average ' +
      figure.dataset.label.toLowerCase() + ' price by month</caption>' +
      '<thead><tr><th scope="col">Month</th><th scope="col" class="pg-num">Cash price</th>' +
      '<th scope="col" class="pg-num">In ' + toggle.dataset.base + ' money</th></tr></thead>' +
      '<tbody>' + body + '</tbody></table>';
  }

  if (toggle && table && figures.length) {
    toggle.hidden = false;
    toggle.addEventListener('click', function () {
      var open = table.hidden;
      if (open) renderTable();
      table.hidden = !open;
      toggle.setAttribute('aria-expanded', String(open));
      toggle.textContent = open ? 'Hide chart data' : 'Show chart data';
    });
  }

  if (select) {
    select.addEventListener('change', function () {
      var chosen = select.value;
      for (var i = 0; i < blocks.length; i++) {
        blocks[i].hidden = blocks[i].dataset.type !== chosen;
      }
      for (var k = 0; k < rows.length; k++) {
        rows[k].classList.toggle('pg-row-on', rows[k].dataset.typeRow === chosen);
      }
      if (table && !table.hidden) renderTable();
    });
  }
})();
</script>
'''


def tiles(area, t):
    window = LATEST - COMMON_WINDOW
    years = COMMON_WINDOW // 12
    own = change(real[t], area, window, LATEST)
    peak = real_peak(area, t)
    third = ''
    if peak and peak[0] < LATEST - 2:
        third = (f'<div class="pg-stat">'
                 f'<span class="pg-stat-label">Below its '
                 f'{esc(pretty_month(month_labels[peak[0]]))} peak</span>'
                 f'<span class="pg-stat-value pg-down">{pct(peak[1])}</span>'
                 f'</div>')
    return (f'<div class="pg-headline">'
            f'<div class="pg-stat">'
            f'<span class="pg-stat-label">Average price, {esc(LATEST_LABEL)}</span>'
            f'<span class="pg-stat-value">{money(nominal[t][area][LATEST])}</span>'
            f'</div>'
            f'<div class="pg-stat">'
            f'<span class="pg-stat-label">Real change, {years} years</span>'
            f'<span class="pg-stat-value {"pg-down" if own < 0 else "pg-up"}">'
            f'{pct(own)}</span></div>{third}</div>')


def prose(area, t, where = None):
    start = first_observation(area, t)
    if start is None or not np.isfinite(nominal[t][area][LATEST]):
        return (f'<p class="pg-standfirst">No {esc(type_label(t).lower())} price '
                f'series is published for {esc(areas[area]["n"])}.</p>')
    return (f'<p class="pg-standfirst">The average '
            f'{"house" if t == 0 else type_label(t).lower()} price '
            f'{where or ("in " + esc(located(area)) + ("," if "," in located(area) else ""))} is '
            f'{money(nominal[t][area][LATEST])} as of {esc(LATEST_LABEL)}. '
            f'This is what they have cost since '
            f'{esc(pretty_month(month_labels[start or 0]))}, in '
            f"today's money rather than in the cash prices of the day.</p>"
            f'<p class="pg-verdict">{verdict(area, t)}</p>')


# Periods across the columns rather than down the rows, so the two things a
# reader is here to compare - real against cash - sit one above the other for
# every window at once instead of being read in pairs down a list.
def horizons(area, t, name):
    spans = horizon_rows(area, t)
    if not spans:
        return ('<p class="pg-note">No price history for '
                f'{esc(type_label(t).lower())} homes in {esc(name)}.</p>')

    head_cells = ''.join(
        f'<th scope="col" class="pg-num">{esc(label)}'
        f'<span class="pg-from">from {esc(frm)}</span></th>'
        for label, frm, _, _ in spans)
    real_cells = ''.join(
        f'<td class="pg-num {"pg-down" if r < 0 else "pg-up"}">{pct(r)}</td>'
        for _, _, r, _ in spans)
    cash_cells = ''.join(f'<td class="pg-num pg-muted">{pct(n)}</td>'
                         for _, _, _, n in spans)

    return (f'<div class="pg-table-wrap"><table class="pg-table pg-wide">'
            f'<caption class="visually-hidden">Change in average '
            f'{esc(type_label(t).lower())} price in {esc(name)}</caption>'
            f'<thead><tr><th scope="col"><span class="visually-hidden">'
            f'Measure</span></th>{head_cells}</tr></thead>'
            f'<tbody>'
            f'<tr><th scope="row">In real terms</th>{real_cells}</tr>'
            f'<tr><th scope="row">In cash terms</th>{cash_cells}</tr>'
            f'</tbody></table></div>')


####################
# The area page

def area_page(area):
    name = areas[area]['n']
    tier = tier_of(areas[area]['c'])
    slug = slugs[area]
    path = f'/house-prices/{slug}/'
    window = LATEST - COMMON_WINDOW
    years = COMMON_WINDOW // 12

    # '{name} house prices' is the head term and goes first. 'UK' is not filler
    # here: it is what separates this Surrey from the one in British Columbia.
    # The long names fall back to the shorter modifier rather than being cut off
    # mid-phrase in the result.
    title = f'{name} House Prices, Adjusted for Inflation | UK'
    if len(title) > 60:
        title = f'{name} House Prices in Real Terms | UK'

    # Descriptions do not rank, they win the click - so this is where the other
    # things people actually type go: 'average house price in ...', 'last 10
    # years', and the graph, which is a suggestion against almost every county.
    description = (f'Average house prices in {name}: the real-terms change over '
                   f'1, 5 and 10 years, and the full history since '
                   f'{FIRST_LABEL[-4:]} in one graph. Land Registry data.')

    def context(t):
        rank = ranking(area, t)
        line = ''
        if rank:
            position, total, tier_name = rank
            line = (f'<p class="pg-rank">Ranked <b>{position} of {total}</b> '
                    f'{esc(plural(tier_name, total))} by real-terms change over '
                    f'the last {years} years, best first.</p>')

        uk = change(real[t], uk_area, window, LATEST)
        own = change(real[t], area, window, LATEST)
        versus = ''
        if np.isfinite(uk) and np.isfinite(own):
            gap = own - uk
            versus = (f'<p>Against the UK as a whole, which is {pct(uk)} in real '
                      f'terms over the same period, {esc(name)} is '
                      f'<b>{abs(gap):.1f} points '
                      f'{"ahead" if gap > 0 else "behind"}</b>.</p>')
        return line + versus

    # The comparison table stays whole whatever is selected - its job is to put
    # the types beside each other - but the selected row is marked so the
    # dropdown and the table never look like they disagree.
    def type_row(t):
        moved = change(real[t], area, window, LATEST)
        on = ' class="pg-row-on"' if t == 0 else ''
        return (f'<tr data-type-row="{t}"{on}>'
                f'<th scope="row">{esc(type_label(t))}</th>'
                f'<td class="pg-num">{money(nominal[t][area][LATEST])}</td>'
                f'<td class="pg-num {"pg-down" if moved < 0 else "pg-up"}">'
                f'{pct(moved)}</td></tr>')

    type_rows = ''.join(type_row(t) for t in range(len(types)))

    siblings = [i for i in page_areas
                if tier_of(areas[i]['c']) == tier and i != area]
    sibling_links = ''.join(
        f'<li><a href="/house-prices/{slugs[i]}/">{esc(areas[i]["n"])}</a></li>'
        for i in sorted(siblings, key = lambda i: areas[i]['n']))

    return head(title, description, path, f'{name} house prices') + f'''
<main class="pg">
  <nav class="pg-crumbs" aria-label="Breadcrumb">
    <a href="/">Home</a> <span aria-hidden="true">/</span>
    <a href="/house-prices/">House prices by area</a> <span aria-hidden="true">/</span>
    <span aria-current="page">{esc(name)}</span>
  </nav>

  <h1>{esc(name)} house prices, adjusted for inflation</h1>

  {type_picker()}
  {type_blocks(area, lambda t: tiles(area, t))}
  {type_blocks(area, lambda t: sparkline(area, t))}
  {data_toggle()}
  {type_blocks(area, lambda t: prose(area, t))}

  <h2>How {esc(name)} house prices have changed</h2>
  {type_blocks(area, lambda t: horizons(area, t, name))}

  <h2>By property type</h2>
  <div class="pg-table-wrap">
    <table class="pg-table">
      <caption class="visually-hidden">Average price and real-terms change by property type</caption>
      <thead><tr><th scope="col">Type</th><th scope="col" class="pg-num">Average price</th>
        <th scope="col" class="pg-num">Real change, {years} years</th></tr></thead>
      <tbody>{type_rows}</tbody>
    </table>
  </div>

  <h2>{esc(name)} in context</h2>
  {type_blocks(area, context)}

  <p class="pg-cta">
    <a class="pg-button" href="/?area={esc(areas[area]['c'])}">Compare {esc(name)} with every local authority</a>
  </p>

  <h2>Other {esc(plural(tier, len(siblings)))}</h2>
  <ul class="pg-siblings">{sibling_links}</ul>
</main>
{type_script()}
''' + footer()


####################
# The index, which doubles as the UK's own page

def index_page():
    area = uk_area
    window = LATEST - COMMON_WINDOW
    years = COMMON_WINDOW // 12

    title = 'UK House Prices by Area, Adjusted for Inflation'
    description = ('House prices by county, region and country, adjusted for '
                   'inflation. Average prices and the real-terms change since '
                   '1995, from Land Registry data.')

    def directory(t):
        out = ''
        for heading, members in groups:
            if not members:
                continue
            items = ''.join(
                f'<li><a href="/house-prices/{slugs[i]}/">{esc(areas[i]["n"])}</a>'
                f'<span class="pg-dir-value '
                f'{"pg-down" if change(real[t], i, window, LATEST) < 0 else "pg-up"}">'
                f'{pct(change(real[t], i, window, LATEST), 0)}</span></li>'
                for i in sorted(members, key = lambda i: areas[i]['n']))
            out += (f'<h3 class="pg-dir-head">{esc(heading)}</h3>'
                    f'<ul class="pg-directory">{items}</ul>')
        return out

    return head(title, description, '/house-prices/', 'House prices by area') + f'''
<main class="pg">
  <nav class="pg-crumbs" aria-label="Breadcrumb">
    <a href="/">Home</a> <span aria-hidden="true">/</span>
    <span aria-current="page">House prices by area</span>
  </nav>

  <h1>UK house prices by area, adjusted for inflation</h1>

  {type_picker()}
  {type_blocks(area, lambda t: tiles(area, t))}
  {type_blocks(area, lambda t: sparkline(area, t))}
  {data_toggle()}
  {type_blocks(area, lambda t: prose(area, t, where = 'across the UK'))}

  <h2>How UK house prices have changed</h2>
  {type_blocks(area, lambda t: horizons(area, t, 'the UK'))}

  {rankings_directory()}

  <h2>Every area</h2>
  <p class="pg-note">The percentage beside each area is its real-terms change
     over the last {years} years, for the property type selected above.</p>
  {type_blocks(area, directory)}

  <p class="pg-cta">
    <a class="pg-button" href="/">Explore every local authority on the map</a>
  </p>
</main>
{type_script()}
''' + footer()


####################
# The ranking pages

# Four lists of the local authorities: the cheapest, the dearest, the fastest
# rising and the hardest falling. The searches these answer carry no horizon -
# 'where are house prices rising fastest in uk', 'biggest house price falls
# uk', 'cheapest house prices uk' - so the choice of window is ours, and the
# URLs carry none either, so that the pages accumulate standing rather than
# being replaced by a dated one each year.
#
# The movement pages rank on five years in real terms. Twelve months is the
# number every monthly bulletin and every newspaper table already publishes,
# and at district level it is noisy and revised for months afterwards - a
# ranking on it would reshuffle every refresh, led by the City of London and
# the Isles of Scilly. Five years is what nobody publishes by district, is
# stable enough to be believed, and is where inflation and cash growth have
# pulled furthest apart. One and ten years sit alongside as columns, so the
# page still answers the reader who wants last year without being about it.
#
# 'cheapest' and 'most expensive' are separate pages rather than two ends of
# one: a list search is won by a title that matches it, and a page called
# 'cheapest and most expensive' half-matches both.

RANK_WINDOW = 60          # the headline window, in months
RANK_COLUMNS = [('1 year', 12), ('5 years', 60), ('10 years', 120)]
TOP_N = 25                # the national list - the 'list' headings below say it in words
SECTION_N = 10            # each country, and London

MAP_DIR = f'{OUT_DIR}/maps'
MAP_W = 520               # the natural width of the map image, in CSS pixels
RAMP_BINS = 32
SEQ_FLOOR = 0.15          # as in map-canvas.js: prices start a little way up the ramp

lads = list(range(geo_areas))

RANK_SECTIONS = [('England', lambda c: c[0] == 'E'),
                 ('Scotland', lambda c: c[0] == 'S'),
                 ('Wales', lambda c: c[0] == 'W'),
                 ('Northern Ireland', lambda c: c[0] == 'N'),
                 ('London', lambda c: c[:3] == 'E09')]

RANKINGS = [
    {'slug': 'cheapest', 'section': 'Cheapest areas in {name}', 'list': 'The 25 cheapest areas', 'metric': 'price', 'reverse': False,
     'title': 'Cheapest House Prices in the UK, {year}: Every Area Ranked',
     'h1': 'Cheapest house prices in the UK',
     'description': ('The cheapest places to buy a house in the UK: every local '
                     'authority ranked by average price in {month}, with the '
                     'real-terms change over five years.')},
    {'slug': 'most-expensive', 'section': 'Most expensive areas in {name}', 'list': 'The 25 most expensive areas', 'metric': 'price', 'reverse': True,
     'title': 'Most Expensive House Prices in the UK, {year}: Areas Ranked',
     'h1': 'Most expensive house prices in the UK',
     'description': ('The most expensive places to buy a house in the UK: every '
                     'local authority ranked by average price in {month}, with the '
                     'real-terms change over five years.')},
    {'slug': 'rising-fastest', 'section': 'Rising fastest in {name}', 'list': 'The 25 fastest-rising areas', 'metric': 'change', 'reverse': True,
     'title': 'Where House Prices Are Rising Fastest in the UK, {year}',
     'h1': 'Where house prices are rising fastest in the UK',
     'description': ('The UK areas where house prices have risen most over five '
                     'years, adjusted for inflation: a map and every local '
                     'authority ranked, to {month}.')},
    {'slug': 'falling-most', 'section': 'Biggest falls in {name}', 'list': 'The 25 biggest falls', 'metric': 'change', 'reverse': False,
     'title': 'Where House Prices Have Fallen Most in the UK, {year}',
     'h1': 'Where house prices have fallen most in the UK',
     'description': ('The UK areas where house prices have fallen most over five '
                     'years once inflation is counted: a map and every local '
                     'authority ranked, to {month}.')},
]


def area_link(i):
    """An area's own page where it has one, and the map with it selected where
    it does not. The local authorities have no pages yet, so today this is the
    map for every row; the day step 08 writes them, the rows link there with no
    change here."""
    if i in slugs:
        return f'/house-prices/{slugs[i]}/'
    return f'/?area={areas[i]["c"]}'


def latest_price(t, i):
    return nominal[t][i][LATEST]


def window_change(series, i, back):
    return change(series, i, LATEST - back, LATEST)


def ranked(t, metric, reverse):
    """Every local authority with a figure, best first for the page in hand."""
    scored = []
    for i in lads:
        value = (latest_price(t, i) if metric == 'price'
                 else window_change(real[t], i, RANK_WINDOW))
        if np.isfinite(value):
            scored.append((value, i))
    scored.sort(key = lambda pair: pair[0], reverse = reverse)
    return scored


####################
# The map image

# Drawn here as a standalone SVG rather than by the canvas on the homepage:
# these pages have no script worth loading a renderer for, and an image is
# indexed, cached across the four pages and painted before any script runs.
# The geometry is the same boundaries the map uses, projected once and
# thinned to the resolution the image is shown at - a coastline drawn to the
# nearest quarter of a pixel is a file three times the size for nothing anyone
# could see. Colours come from the same tokens as the app, read out of the
# stylesheet, with both themes carried inside the file: an image cannot see
# the page's CSS, so it brings its own copy and switches on the same query.

def css_tokens():
    """The :root tokens for each theme, read straight from the stylesheet so
    the image and the app cannot drift apart."""
    css = open('web/css/style.css', encoding = 'utf-8').read()
    dark_at = css.index('@media (prefers-color-scheme: dark)')

    def block(text):
        body = text[text.index(':root {') + 7:]
        body = body[:body.index('\n}')]
        return dict(re.findall(r'(--[\w-]+):\s*([^;]+);', body))

    return block(css[:dark_at]), block(css[dark_at:])


def parse_colour(text):
    text = text.strip()
    if text.startswith('#'):
        return tuple(int(text[k:k + 2], 16) for k in (1, 3, 5))
    return tuple(int(float(v)) for v in re.findall(r'[\d.]+', text)[:3])


def ramp_colours(tokens):
    """The diverging ramp as RAMP_BINS hex colours, blended in sRGB the way
    map-canvas.js blends it."""
    neg, mid, pos = (parse_colour(tokens[k]) for k in ('--ramp-neg', '--ramp-mid', '--ramp-pos'))

    def mix(a, b, f):
        return '#' + ''.join(f'{round(a[k] + (b[k] - a[k]) * f):02x}' for k in range(3))

    out = []
    for b in range(RAMP_BINS):
        pos_t = (b / (RAMP_BINS - 1)) * 2 - 1
        out.append(mix(neg, mid, pos_t + 1) if pos_t < 0 else mix(mid, pos, pos_t))
    return out


def project_boundaries():
    """Every area's outline as an SVG path in image coordinates, keyed by area
    index. Web Mercator, as on the map, at twice the shown resolution so the
    coordinates can be whole numbers - relative moves in integers are what
    keep the file small."""
    geo = j.load(open('web/data/lads.geojson', encoding = 'utf-8'))

    def mercator(lon, lat):
        return lon, math.degrees(math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))

    rings = {}
    for feature in geo['features']:
        geometry = feature['geometry']
        polys = (geometry['coordinates'] if geometry['type'] == 'MultiPolygon'
                 else [geometry['coordinates']])
        rings[feature['id']] = [[mercator(x, y) for x, y in ring]
                                for poly in polys for ring in poly]

    xs = [x for area in rings.values() for ring in area for x, _ in ring]
    ys = [y for area in rings.values() for ring in area for _, y in ring]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    scale = MAP_W * 2 / (x1 - x0)
    height = math.ceil((y1 - y0) * scale)

    def path(area_rings):
        d = []
        for ring in area_rings:
            kept = []
            for x, y in ring:
                px = round((x - x0) * scale)
                py = round((y1 - y) * scale)
                # Two image units is one shown pixel; a point that close to
                # the last kept one draws nothing
                if not kept or abs(px - kept[-1][0]) + abs(py - kept[-1][1]) >= 2:
                    kept.append((px, py))
            if len(kept) < 3:
                continue
            moves = ' '.join(f'{bx - ax} {by - ay}' for (ax, ay), (bx, by) in zip(kept, kept[1:]))
            d.append(f'M{kept[0][0]} {kept[0][1]}l{moves}z')
        return ''.join(d)

    return {area: path(area_rings) for area, area_rings in rings.items()}, MAP_W * 2, height


LIGHT_TOKENS, DARK_TOKENS = css_tokens()
LIGHT_RAMP, DARK_RAMP = ramp_colours(LIGHT_TOKENS), ramp_colours(DARK_TOKENS)
MAP_PATHS, MAP_VW, MAP_VH = project_boundaries()


def colour_bound(values):
    """The tenth largest absolute change, as on the map, so a handful of
    extreme districts do not flatten the rest of the country to one tint."""
    magnitudes = sorted((abs(v) for v in values if np.isfinite(v)), reverse = True)
    if not magnitudes:
        return 1.0
    return max(magnitudes[min(9, len(magnitudes) - 1)], 0.1)


def price_bounds(values):
    """Nine trimmed from each end, as on the map: Kensington and Chelsea alone
    sits high enough to leave every other area the same pale tint."""
    finite = sorted(v for v in values if np.isfinite(v))
    trim = min(9, len(finite) // 20)
    lo, hi = finite[trim], finite[-1 - trim]
    return lo, (hi if hi > lo else lo + 1)


def choropleth(values, mode, path):
    """Write the map for one set of values, and return the ramp's domain so the
    legend on the page can say what the ends mean."""
    if mode == 'price':
        lo, hi = price_bounds(values)
    else:
        bound = colour_bound(values)
        lo, hi = -bound, bound

    def bin_of(value):
        if not np.isfinite(value):
            return 'n'
        if mode == 'price':
            normalised = SEQ_FLOOR + (1 - SEQ_FLOOR) * min(max((value - lo) / (hi - lo), 0), 1)
        else:
            normalised = min(max(value / hi, -1), 1)
        return f'c{round((normalised + 1) / 2 * (RAMP_BINS - 1))}'

    def rules(tokens, ramp):
        return (f'.n{{fill:{tokens["--map-nodata"]}}}'
                f'path{{stroke:{tokens["--map-line"]}}}'
                + ''.join(f'.c{b}{{fill:{ramp[b]}}}' for b in range(RAMP_BINS)))

    style = (f'path{{stroke-width:1;stroke-linejoin:round}}'
             f'{rules(LIGHT_TOKENS, LIGHT_RAMP)}'
             f'@media (prefers-color-scheme: dark){{{rules(DARK_TOKENS, DARK_RAMP)}}}')

    paths = ''.join(f'<path class="{bin_of(values[i])}" d="{MAP_PATHS[i]}"/>'
                    for i in lads if MAP_PATHS.get(i))

    write(path, f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {MAP_VW} {MAP_VH}">'
                f'<style>{style}</style>{paths}</svg>\n')
    return lo, hi


def map_figure(t, metric):
    """The map and its legend. The legend is HTML rather than part of the
    image, so it is set in the page's own type and follows its theme."""
    if metric == 'price':
        values = [latest_price(t, i) for i in lads]
        name = f'price-{t}.svg'
        lo, hi = choropleth(values, 'price', f'{MAP_DIR}/{name}')
        alt = (f'Map of UK local authorities shaded by average '
               f'{type_label(t).lower()} price, {LATEST_LABEL}')
        legend = (f'<span class="pg-map-end">{money(lo)}</span>'
                  f'<span class="legend-ramp is-sequential"></span>'
                  f'<span class="pg-map-end">{money(hi)}</span>')
        what = f'Average {type_label(t).lower()} price, {LATEST_LABEL}'
    else:
        values = [window_change(real[t], i, RANK_WINDOW) for i in lads]
        name = f'change-{RANK_WINDOW // 12}y-{t}.svg'
        lo, hi = choropleth(values, 'change', f'{MAP_DIR}/{name}')
        alt = (f'Map of UK local authorities shaded by real-terms change in '
               f'average {type_label(t).lower()} price over the five years to {LATEST_LABEL}')
        legend = (f'<span class="pg-map-end">{pct(lo, 0)}</span>'
                  f'<span class="legend-ramp"></span>'
                  f'<span class="pg-map-end">{pct(hi, 0)}</span>')
        what = (f'Real-terms change in average {type_label(t).lower()} price, '
                f'{pretty_month(month_labels[LATEST - RANK_WINDOW])} to {LATEST_LABEL}')

    return (f'<figure class="pg-map">'
            f'<img src="/house-prices/maps/{name}" width="{MAP_W}" height="{MAP_VH // 2}" '
            f'alt="{esc(alt)}" loading="lazy" decoding="async">'
            f'<figcaption><span class="pg-map-what">{esc(what)}</span>'
            f'<span class="pg-map-scale">{legend}</span>'
            f'<span class="pg-map-nodata"><span class="legend-swatch"></span>No data</span>'
            f'</figcaption></figure>')


####################
# The ranking tables

def rank_table(t, rows, metric, caption, start_rank = 1):
    if metric == 'price':
        head_cells = ('<th scope="col" class="pg-num">Average price</th>'
                      + ''.join(f'<th scope="col" class="pg-num">Real change<span class="pg-from">{esc(label)}</span></th>'
                                for label, _ in RANK_COLUMNS[1:]))
    else:
        head_cells = ('<th scope="col" class="pg-num">Real change<span class="pg-from">5 years</span></th>'
                      '<th scope="col" class="pg-num">Cash change<span class="pg-from">5 years</span></th>'
                      + ''.join(f'<th scope="col" class="pg-num">Real change<span class="pg-from">{esc(label)}</span></th>'
                                for label, back in RANK_COLUMNS if back != RANK_WINDOW))

    def num(value, muted = False):
        tone = 'pg-muted' if muted else ('pg-down' if value < 0 else 'pg-up')
        return f'<td class="pg-num {tone}">{pct(value)}</td>'

    body = ''
    for n, (value, i) in enumerate(rows, start = start_rank):
        if metric == 'price':
            cells = (f'<td class="pg-num">{money(value)}</td>'
                     + ''.join(num(window_change(real[t], i, back)) for _, back in RANK_COLUMNS[1:]))
        else:
            cells = (num(value)
                     + num(window_change(nominal[t], i, RANK_WINDOW), muted = True)
                     + ''.join(num(window_change(real[t], i, back))
                               for _, back in RANK_COLUMNS if back != RANK_WINDOW))
        body += (f'<tr><td class="pg-rank-n">{n}</td>'
                 f'<th scope="row"><a href="{area_link(i)}">{esc(areas[i]["n"])}</a></th>'
                 f'{cells}</tr>')

    return (f'<div class="pg-table-wrap"><table class="pg-table pg-ranking">'
            f'<caption class="visually-hidden">{esc(caption)}</caption>'
            f'<thead><tr><th scope="col"><span class="visually-hidden">Rank</span></th>'
            f'<th scope="col">Area</th>{head_cells}</tr></thead>'
            f'<tbody>{body}</tbody></table></div>')


def rank_prose(spec, t, rows):
    """What the list says, in a sentence or two, assembled from the figures so
    it is never a month behind the table below it."""
    what = 'home' if t == 0 else f'{type_label(t).lower()} home'
    top_value, top = rows[0]
    top_name = esc(areas[top]['n'])
    uk_price = latest_price(t, uk_area)

    if spec['metric'] == 'price':
        other_value, other = rows[-1]
        other_name = esc(areas[other]['n'])
        if spec['slug'] == 'cheapest':
            first = (f'The cheapest place to buy a {what} in the UK is <b>{top_name}</b>, '
                     f'where the average costs <b>{money(top_value)}</b> as of {esc(LATEST_LABEL)} - '
                     f'{top_value / uk_price * 100:.0f}% of the UK average of {money(uk_price)}. ')
            second = (f'The dearest, {other_name}, costs {other_value / top_value:.1f} times as much.')
        else:
            first = (f'The most expensive place to buy a {what} in the UK is <b>{top_name}</b>, '
                     f'where the average costs <b>{money(top_value)}</b> as of {esc(LATEST_LABEL)} - '
                     f'{top_value / uk_price:.1f} times the UK average of {money(uk_price)}. ')
            second = (f'The cheapest, {other_name}, is {money(other_value)}; '
                      f'{top_name} costs {top_value / other_value:.1f} times as much.')
        return f'<p class="pg-verdict">{first}{second}</p>'

    since = esc(pretty_month(month_labels[LATEST - RANK_WINDOW]))
    cash = window_change(nominal[t], top, RANK_WINDOW)
    ups = sum(1 for v, _ in rows if v > 0)
    downs = len(rows) - ups
    uk = window_change(real[t], uk_area, RANK_WINDOW)

    if spec['slug'] == 'rising-fastest':
        first = (f'Over the five years from {since}, the average {what} rose most in real terms '
                 f'in <b>{top_name}</b>: <b>{pct(top_value)}</b> after inflation, on a cash rise '
                 f'of {pct(cash)}. ')
    else:
        cash_clause = (f'even though the cash price rose {pct(cash)}' if cash > 0
                       else f'on a cash fall of {pct(cash)}')
        first = (f'Over the five years from {since}, the average {what} fell most in real terms '
                 f'in <b>{top_name}</b>: <b>{pct(top_value)}</b> after inflation, {cash_clause}. ')
    second = (f'Of the {len(rows)} local authorities with a figure, <b>{ups}</b> are up in real '
              f'terms over those five years and <b>{downs}</b> are down; the UK as a whole is '
              f'{pct(uk)}.')
    return f'<p class="pg-verdict">{first}{second}</p>'


def ranking_page(spec):
    slug = spec['slug']
    path = f'/house-prices/{slug}/'
    year = LATEST_LABEL[-4:]
    title = spec['title'].format(year = year)
    description = spec['description'].format(month = LATEST_LABEL)
    metric = spec['metric']

    def body(t):
        rows = ranked(t, metric, spec['reverse'])
        if not rows:
            return (f'<p class="pg-note">No {esc(type_label(t).lower())} price series '
                    f'is published for enough areas to rank.</p>')

        out = rank_prose(spec, t, rows)
        out += map_figure(t, metric)
        out += f'<h2>{esc(spec["list"])}</h2>'
        out += rank_table(t, rows[:TOP_N], metric,
                          f'{spec["h1"]} by {type_label(t).lower()} price, top {TOP_N}')

        for name, member in RANK_SECTIONS:
            subset = [(v, i) for v, i in rows if member(areas[i]['c'])][:SECTION_N]
            if len(subset) < 3:
                continue
            # 'cheapest areas in london' is the phrase, so the heading says it
            heading = spec['section'].format(name = name)
            out += f'<h2>{esc(heading)}</h2>'
            out += rank_table(t, subset, metric, f'{heading}, {type_label(t).lower()} price')
        return out

    others = ''.join(
        f'<li><a href="/house-prices/{other["slug"]}/">{esc(other["h1"])}</a></li>'
        for other in RANKINGS if other['slug'] != slug)

    basis = ('Prices are the Land Registry average for each local authority in '
             f'{esc(LATEST_LABEL)}.' if metric == 'price' else
             f'Real terms means in {esc(CPI_BASE)} money: the cash change less CPI '
             f'inflation over the same five years. Areas are local authorities; the '
             f'national and regional averages are not ranked.')

    return head(title, description, path, spec['h1']) + f'''
<main class="pg">
  <nav class="pg-crumbs" aria-label="Breadcrumb">
    <a href="/">Home</a> <span aria-hidden="true">/</span>
    <a href="/house-prices/">House prices by area</a> <span aria-hidden="true">/</span>
    <span aria-current="page">{esc(spec['h1'])}</span>
  </nav>

  <h1>{esc(spec['h1'])}, {esc(year)}</h1>
  <p class="pg-standfirst">Every local authority in the UK, ranked from Land Registry
     data to {esc(LATEST_LABEL)}. {basis}</p>

  {type_picker()}
  {type_blocks(None, body)}

  <p class="pg-cta">
    <a class="pg-button" href="/">Explore every area on the interactive map</a>
  </p>

  <h2>Other rankings</h2>
  <ul class="pg-siblings">{others}</ul>
</main>
{type_script()}
''' + footer()


def rankings_directory():
    """The links from the index, above the areas."""
    items = ''.join(f'<li><a href="/house-prices/{spec["slug"]}/">{esc(spec["h1"])}</a></li>'
                    for spec in RANKINGS)
    return f'<h2>Rankings</h2><ul class="pg-siblings pg-rankings">{items}</ul>'


####################
# Write

def write(path, html):
    os.makedirs(os.path.dirname(path), exist_ok = True)
    with open(path, 'w', encoding = 'utf-8') as f:
        f.write(html)


write(f'{OUT_DIR}/index.html', index_page())
for i in page_areas:
    write(f'{OUT_DIR}/{slugs[i]}/index.html', area_page(i))
for spec in RANKINGS:
    write(f'{OUT_DIR}/{spec["slug"]}/index.html', ranking_page(spec))

# A boundary reorganisation renames areas, and a renamed area leaves its old
# page sitting in the tree. Nothing here would overwrite it, so it would be
# committed and deployed for ever, frozen at whatever the figures were the month
# the name changed - a page that is wrong and has no way of ever being corrected.
wanted = {slugs[i] for i in page_areas} | {spec['slug'] for spec in RANKINGS} | {'maps'}
stale = sorted(name for name in os.listdir(OUT_DIR)
               if os.path.isdir(f'{OUT_DIR}/{name}') and name not in wanted)

for name in stale:
    for root, dirs, files in os.walk(f'{OUT_DIR}/{name}', topdown = False):
        for f in files:
            os.remove(os.path.join(root, f))
        os.rmdir(root)

if stale:
    print(f'  removed {len(stale)} page(s) for areas that no longer exist: '
          + ', '.join(stale[:5]))


####################
# Tell the app which areas have a page

# The map offers a link through to an area's page, and it reads the list from
# here rather than working the URL out from the name. Two slug rules that have
# to agree - one in Python, one in JavaScript - would agree right up until a
# name arrived with an apostrophe in it, and then the link would 404 silently
# for that one area. This way the app links to a page when the page exists and
# says nothing when it does not, and the local authority pages will start
# working the day they are generated without a line of JavaScript changing.
pages = {areas[i]['c']: f'/house-prices/{slugs[i]}/' for i in page_areas}
pages[areas[uk_area]['c']] = '/house-prices/'

with open('web/data/pages.json', 'w', encoding = 'utf-8') as f:
    j.dump(pages, f, separators = (',', ':'), sort_keys = True)


####################
# Sitemap

# Owned by this step rather than by step 06, because this is the step that knows
# what pages exist. 'lastmod' tracks the data the pages are built from, so it
# stays honest without anyone having to remember it.
urls = ([f'{SITE}/', f'{SITE}/house-prices/']
        + [f'{SITE}/house-prices/{spec["slug"]}/' for spec in RANKINGS]
        + [f'{SITE}/house-prices/{slugs[i]}/' for i in page_areas])

entries = ''.join(f'  <url>\n'
                  f'    <loc>{url}</loc>\n'
                  f'    <lastmod>{meta["generated"]}</lastmod>\n'
                  f'    <changefreq>monthly</changefreq>\n'
                  f'  </url>\n'
                  for url in urls)

with open('web/sitemap.xml', 'w', encoding = 'utf-8') as f:
    f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + entries +
            '</urlset>\n')


####################
# Report what was written

total = sum(os.path.getsize(os.path.join(root, name))
            for root, _, files in os.walk(OUT_DIR) for name in files)

print(f'  wrote {len(page_areas) + 1} area pages and {len(RANKINGS)} rankings '
      f'to {OUT_DIR} ({total / 1024:.0f} KB)')
print(f'  wrote web/sitemap.xml ({len(urls)} URLs)')
print(f'  wrote web/data/pages.json ({len(pages)} areas)')
