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
            ('3 years', 36),
            ('5 years', 60),
            ('10 years', 120),
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

# Deflated to the latest month, which is what 'in today's money' means here
real = nominal / (cpi[None, None, :] / cpi[-1])

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
        <span class="brand-sub">Local authority price changes</span>
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


def sparkline(area, t = 0):
    """Real and nominal average price, 1995 to the latest month.

    Drawn here rather than in the browser: the chart is the substance of the
    page, and a page whose substance arrives only after a script has run is a
    page Google may index without it. Colours come from the same tokens the rest
    of the site uses, so it follows the visitor's theme like everything else.
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

    return f'''<figure class="pg-figure">
  <svg viewBox="0 0 {W} {H}" role="img" preserveAspectRatio="none"
       aria-label="Average {esc(type_label(t)).lower()} price in {esc(areas[area]['n'])}, real and nominal, {FIRST_LABEL} to {LATEST_LABEL}">
    {grid}{axis}
    <path class="pg-nominal" d="{paths['nominal']}" fill="none"/>
    <path class="pg-real" d="{paths['real']}" fill="none"/>
  </svg>
  <figcaption class="pg-legend">
    <span class="pg-key pg-key-real">In today's money</span>
    <span class="pg-key pg-key-nominal">Cash price at the time</span>
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
# The area page

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

    def tiles(t):
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

    def prose(t):
        return (f'<p class="pg-standfirst">The average '
                f'{"house" if t == 0 else type_label(t).lower()} price in '
                f'{esc(located(area))}{"," if "," in located(area) else ""} is '
                f'{money(nominal[t][area][LATEST])} as of {esc(LATEST_LABEL)}. '
                f'This is what they have cost there since '
                f'{esc(pretty_month(month_labels[first_observation(area, t) or 0]))}, '
                f"in today's money rather than in the cash prices of the day.</p>"
                f'<p class="pg-verdict">{verdict(area, t)}</p>')

    # Periods across the columns rather than down the rows, so the two things a
    # reader is here to compare - real against cash - sit one above the other
    # for every window at once instead of being read in pairs down a list.
    def horizons(t):
        spans = horizon_rows(area, t)
        if not spans:
            return ('<p class="pg-note">No price history for '
                    f'{esc(type_label(t).lower())} homes in {esc(name)}.</p>')

        head_cells = ''.join(
            f'<th scope="col">{esc(label)}'
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

    def context(t):
        rank = ranking(area, t)
        line = ''
        if rank:
            position, total, tier_name = rank
            line = (f'<p class="pg-rank">Ranked <b>{position} of {total}</b> '
                    f'{esc(tier_name)}{"" if tier_name.endswith("y") else "s"} '
                    f'by real-terms change over the last {years} years, '
                    f'best first.</p>').replace('countys', 'counties')

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

    options = ''.join(f'<option value="{t}">{esc(type_label(t))}</option>'
                      for t in range(len(types)))

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

  <div class="pg-picker">
    <label for="housing-type">Property type</label>
    <div class="select-wrap"><select id="housing-type">{options}</select></div>
  </div>

  {type_blocks(area, tiles)}
  {type_blocks(area, lambda t: sparkline(area, t))}
  {type_blocks(area, prose)}

  <h2>How {esc(name)} house prices have changed</h2>
  {type_blocks(area, horizons)}

  <h2>By property type</h2>
  <div class="pg-table-wrap">
    <table class="pg-table">
      <caption class="visually-hidden">Average price and real-terms change by property type</caption>
      <thead><tr><th scope="col">Type</th><th scope="col">Average price</th>
        <th scope="col">Real change, {years} years</th></tr></thead>
      <tbody>{type_rows}</tbody>
    </table>
  </div>

  <h2>{esc(name)} in context</h2>
  {type_blocks(area, context)}

  <p class="pg-cta">
    <a class="pg-button" href="/?area={esc(areas[area]['c'])}">See {esc(name)} on the map</a>
  </p>

  <h2>Other {esc(tier)}{"" if tier.endswith('y') else "s"}</h2>
  <ul class="pg-siblings">{sibling_links}</ul>
</main>

<!-- Every type is already in the markup above; this only decides which one is
     on show. With JavaScript off the select does nothing and the page stays on
     Overall, which is a complete page rather than a broken one. -->
<script>
(function () {{
  var select = document.getElementById('housing-type');
  if (!select) return;
  var blocks = document.querySelectorAll('.pg-type');
  var rows = document.querySelectorAll('[data-type-row]');
  select.addEventListener('change', function () {{
    var chosen = select.value;
    for (var i = 0; i < blocks.length; i++) {{
      blocks[i].hidden = blocks[i].dataset.type !== chosen;
    }}
    for (var k = 0; k < rows.length; k++) {{
      rows[k].classList.toggle('pg-row-on', rows[k].dataset.typeRow === chosen);
    }}
  }});
}})();
</script>
'''.replace('Other countys', 'Other counties') + footer()


####################
# The index, which doubles as the UK's own page

def index_page():
    area = uk_area
    window = LATEST - COMMON_WINDOW
    years = COMMON_WINDOW // 12
    own_real = change(real[0], area, window, LATEST)

    peak = real_peak(area)
    peak_tile = ''
    if peak and peak[0] < LATEST - 2:
        peak_tile = f'''<div class="pg-stat">
      <span class="pg-stat-label">Below its {esc(pretty_month(month_labels[peak[0]]))} peak</span>
      <span class="pg-stat-value pg-down">{pct(peak[1])}</span>
    </div>'''

    title = 'UK House Prices by Area, Adjusted for Inflation'
    description = ('House prices by county, region and country, adjusted for '
                   'inflation. Average prices and the real-terms change since '
                   '1995, from Land Registry data.')

    rows = ''.join(
        f'<tr><th scope="row">{esc(label)}<span class="pg-from">from {esc(frm)}</span></th>'
        f'<td class="pg-num {"pg-down" if r < 0 else "pg-up"}">{pct(r)}</td>'
        f'<td class="pg-num pg-muted">{pct(n)}</td></tr>'
        for label, frm, r, n in horizon_rows(area))

    directory = ''
    for heading, members in groups:
        if not members:
            continue
        items = ''.join(
            f'<li><a href="/house-prices/{slugs[i]}/">{esc(areas[i]["n"])}</a>'
            f'<span class="pg-dir-value {"pg-down" if change(real[0], i, window, LATEST) < 0 else "pg-up"}">'
            f'{pct(change(real[0], i, window, LATEST), 0)}</span></li>'
            for i in sorted(members, key = lambda i: areas[i]['n']))
        directory += (f'<h2>{esc(heading)}</h2>'
                      f'<ul class="pg-directory">{items}</ul>')

    return head(title, description, '/house-prices/', 'House prices by area') + f'''
<main class="pg">
  <nav class="pg-crumbs" aria-label="Breadcrumb">
    <a href="/">Home</a> <span aria-hidden="true">/</span>
    <span aria-current="page">House prices by area</span>
  </nav>

  <h1>UK house prices by area, adjusted for inflation</h1>

  <div class="pg-headline">
    <div class="pg-stat">
      <span class="pg-stat-label">UK average price, {esc(LATEST_LABEL)}</span>
      <span class="pg-stat-value">{money(nominal[0][area][LATEST])}</span>
    </div>
    <div class="pg-stat">
      <span class="pg-stat-label">Real change, {years} years</span>
      <span class="pg-stat-value {"pg-down" if own_real < 0 else "pg-up"}">{pct(own_real)}</span>
    </div>
    {peak_tile}
  </div>

  {sparkline(area)}

  <p class="pg-standfirst">The average house price across the UK is
     {money(nominal[0][area][LATEST])} as of {esc(LATEST_LABEL)}. This is what
     homes have cost since {FIRST_LABEL}, in today's money rather than in the
     cash prices of the day.</p>

  <p class="pg-verdict">{verdict(area)}</p>

  <h2>How UK prices have changed</h2>
  <div class="pg-table-wrap">
    <table class="pg-table">
      <caption class="visually-hidden">Change in the UK average house price</caption>
      <thead><tr><th scope="col">Period</th><th scope="col">In real terms</th>
        <th scope="col">In cash terms</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>

  <p class="pg-note">The percentage beside each area below is its real-terms
     change over the last {years} years.</p>

  {directory}

  <p class="pg-cta">
    <a class="pg-button" href="/">Explore every local authority on the map</a>
  </p>
</main>
''' + footer()


####################
# Write

def write(path, html):
    os.makedirs(os.path.dirname(path), exist_ok = True)
    with open(path, 'w', encoding = 'utf-8') as f:
        f.write(html)


write(f'{OUT_DIR}/index.html', index_page())
for i in page_areas:
    write(f'{OUT_DIR}/{slugs[i]}/index.html', area_page(i))


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
urls = [f'{SITE}/', f'{SITE}/house-prices/'] + [f'{SITE}/house-prices/{slugs[i]}/'
                                                for i in page_areas]

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

print(f'  wrote {len(page_areas) + 1} pages to {OUT_DIR} ({total / 1024:.0f} KB)')
print(f'  wrote web/sitemap.xml ({len(urls)} URLs)')
print(f'  wrote web/data/pages.json ({len(pages)} areas)')
