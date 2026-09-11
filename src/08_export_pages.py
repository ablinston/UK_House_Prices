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

# The peak the whole real-terms story hangs off. Nominal prices passed it years
# ago nearly everywhere; real prices have not, in most of the country.
PEAK = '2007-09'

# Horizons shown in the change table, as (label, months back). 'None' means the
# area's own first observation, which is January 1995 for everywhere here.
HORIZONS = [('1 year', 12),
            ('5 years', 60),
            ('10 years', 120),
            ('Since the 2007 peak', PEAK),
            ('Since 1995', None)]

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


def sparkline(area):
    """Real and nominal average price, 1995 to the latest month.

    Drawn here rather than in the browser: the chart is the substance of the
    page, and a page whose substance arrives only after a script has run is a
    page Google may index without it. Colours come from the same tokens the rest
    of the site uses, so it follows the visitor's theme like everything else.
    """
    W, H = 720, 260
    PAD_L, PAD_R, PAD_T, PAD_B = 58, 12, 14, 26

    series = {'real': real[0][area], 'nominal': nominal[0][area]}
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
       aria-label="Average price in {esc(areas[area]['n'])}, real and nominal, {FIRST_LABEL} to {LATEST_LABEL}">
    {grid}{axis}
    <path class="pg-nominal" d="{paths['nominal']}" fill="none"/>
    <path class="pg-real" d="{paths['real']}" fill="none"/>
  </svg>
  <figcaption class="pg-legend">
    <span class="pg-key pg-key-real">In today's money</span>
    <span class="pg-key pg-key-nominal">Cash price at the time</span>
  </figcaption>
</figure>'''


def horizon_rows(area):
    rows = []
    for label, back in HORIZONS:
        if back is None:
            frm = 0
        elif isinstance(back, str):
            frm = month_index(back)
        else:
            frm = LATEST - back
        if frm < 0:
            continue
        rows.append((label, pretty_month(month_labels[frm]),
                     change(real[0], area, frm, LATEST),
                     change(nominal[0], area, frm, LATEST)))
    return rows


def verdict(area):
    """One sentence saying what the numbers mean, so the page states something
    rather than only displaying something. Assembled from the figures, so it
    restates itself on every refresh instead of going stale."""
    name = areas[area]['n']
    peak = month_index(PEAK)
    r = change(real[0], area, peak, LATEST)
    n = change(nominal[0], area, peak, LATEST)

    if not np.isfinite(r) or not np.isfinite(n):
        return f'{esc(name)} has a full monthly price history from {FIRST_LABEL}.'

    if r < 0:
        return (f'The average home in {esc(name)} costs <b>{abs(r):.1f}% less</b> '
                f'in real terms than at the {pretty_month(PEAK)} peak, even though '
                f'the cash price is <b>{n:.1f}% higher</b>.')
    return (f'The average home in {esc(name)} is worth <b>{r:.1f}% more</b> in real '
            f'terms than at the {pretty_month(PEAK)} peak, on a cash price '
            f'<b>{n:.1f}% higher</b>.')


def ranking(area):
    """Where this area sits among its own kind since the 2007 peak."""
    tier = tier_of(areas[area]['c'])
    peers = [i for i in page_areas if tier_of(areas[i]['c']) == tier]
    if len(peers) < 3:
        return None

    peak = month_index(PEAK)
    scored = [(change(real[0], i, peak, LATEST), i) for i in peers]
    scored = [(v, i) for v, i in scored if np.isfinite(v)]
    scored.sort(reverse = True)
    order = [i for _, i in scored]
    if area not in order:
        return None
    return order.index(area) + 1, len(order), tier


####################
# The area page

def area_page(area):
    name = areas[area]['n']
    tier = tier_of(areas[area]['c'])
    slug = slugs[area]
    path = f'/house-prices/{slug}/'

    title = f'{name} House Prices Adjusted for Inflation'
    if len(title) + 20 <= 60:
        title += ' | Real House Prices'

    description = (f'House prices in {name} adjusted for inflation. Average prices '
                   f'and the real-terms change from {FIRST_LABEL[-4:]} to '
                   f'{LATEST_LABEL}, from Land Registry data.')

    rows = ''.join(
        f'<tr><th scope="row">{esc(label)}<span class="pg-from">from {esc(frm)}</span></th>'
        f'<td class="pg-num {"pg-down" if r < 0 else "pg-up"}">{pct(r)}</td>'
        f'<td class="pg-num pg-muted">{pct(n)}</td></tr>'
        for label, frm, r, n in horizon_rows(area))

    peak = month_index(PEAK)
    type_rows = ''.join(
        f'<tr><th scope="row">{esc("Semi-detached" if t == "SemiDetached" else t)}</th>'
        f'<td class="pg-num">{money(nominal[i][area][LATEST])}</td>'
        f'<td class="pg-num {"pg-down" if change(real[i], area, peak, LATEST) < 0 else "pg-up"}">'
        f'{pct(change(real[i], area, peak, LATEST))}</td></tr>'
        for i, t in enumerate(types))

    rank = ranking(area)
    rank_line = ''
    if rank:
        position, total, tier_name = rank
        rank_line = (f'<p class="pg-rank">Ranked <b>{position} of {total}</b> '
                     f'{esc(tier_name)}{"" if tier_name.endswith("y") else "s"} '
                     f'by real-terms change since the {pretty_month(PEAK)} peak, '
                     f'best first.</p>').replace('countys', 'counties')

    uk_real = change(real[0], uk_area, peak, LATEST)
    own_real = change(real[0], area, peak, LATEST)
    versus = ''
    if np.isfinite(uk_real) and np.isfinite(own_real):
        gap = own_real - uk_real
        versus = (f'<p>Against the UK as a whole, which is {pct(uk_real)} in real '
                  f'terms over the same period, {esc(name)} is '
                  f'<b>{abs(gap):.1f} points {"ahead" if gap > 0 else "behind"}</b>.</p>')

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
  <p class="pg-standfirst">What homes have cost in {esc(name)} since {FIRST_LABEL},
     in today's money. Figures to {esc(LATEST_LABEL)}.</p>

  <div class="pg-headline">
    <div class="pg-stat">
      <span class="pg-stat-label">Average price, {esc(LATEST_LABEL)}</span>
      <span class="pg-stat-value">{money(nominal[0][area][LATEST])}</span>
    </div>
    <div class="pg-stat">
      <span class="pg-stat-label">Real change since the peak</span>
      <span class="pg-stat-value {"pg-down" if own_real < 0 else "pg-up"}">{pct(own_real)}</span>
    </div>
  </div>

  <p class="pg-verdict">{verdict(area)}</p>

  {sparkline(area)}

  <h2>How prices have changed</h2>
  <div class="pg-table-wrap">
    <table class="pg-table">
      <caption class="visually-hidden">Change in average house price in {esc(name)}</caption>
      <thead><tr><th scope="col">Period</th><th scope="col">In real terms</th>
        <th scope="col">In cash terms</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>

  <h2>By property type</h2>
  <div class="pg-table-wrap">
    <table class="pg-table">
      <caption class="visually-hidden">Average price and real-terms change by property type</caption>
      <thead><tr><th scope="col">Type</th><th scope="col">Average price</th>
        <th scope="col">Real change since 2007</th></tr></thead>
      <tbody>{type_rows}</tbody>
    </table>
  </div>

  <h2>{esc(name)} in context</h2>
  {rank_line}
  {versus}

  <p class="pg-cta">
    <a class="pg-button" href="/?area={esc(areas[area]['c'])}">See {esc(name)} on the map</a>
  </p>

  <h2>Other {esc(tier)}{"" if tier.endswith('y') else "s"}</h2>
  <ul class="pg-siblings">{sibling_links}</ul>
</main>
'''.replace('Other countys', 'Other counties') + footer()


####################
# The index, which doubles as the UK's own page

def index_page():
    area = uk_area
    peak = month_index(PEAK)
    own_real = change(real[0], area, peak, LATEST)

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
            f'<span class="pg-dir-value {"pg-down" if change(real[0], i, peak, LATEST) < 0 else "pg-up"}">'
            f'{pct(change(real[0], i, peak, LATEST), 0)}</span></li>'
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
  <p class="pg-standfirst">What homes have cost across the UK since {FIRST_LABEL},
     in today's money. Figures to {esc(LATEST_LABEL)}.</p>

  <div class="pg-headline">
    <div class="pg-stat">
      <span class="pg-stat-label">UK average price, {esc(LATEST_LABEL)}</span>
      <span class="pg-stat-value">{money(nominal[0][area][LATEST])}</span>
    </div>
    <div class="pg-stat">
      <span class="pg-stat-label">Real change since the peak</span>
      <span class="pg-stat-value {"pg-down" if own_real < 0 else "pg-up"}">{pct(own_real)}</span>
    </div>
  </div>

  <p class="pg-verdict">{verdict(area)}</p>

  {sparkline(area)}

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
     change since the {pretty_month(PEAK)} peak.</p>

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
