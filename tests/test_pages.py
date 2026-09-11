"""The generated pages in web/house-prices, checked as published files.

Step 08 writes 43 pages from the same web/data the map reads, and they are
committed and deployed exactly as written - there is no renderer between the
generator and the visitor to catch a mistake on the way. What can go wrong is
quiet rather than loud: a page whose figures no longer agree with the tool it
links into, a link to an area that was renamed out from under it, a chart whose
path came out empty because a series was missing. None of that raises anything
in step 08; all of it is visible here.

These run against the files rather than by re-running the generator, for the
same reason the rest of the suite reads web/data: what matters before a push is
whether the payload is sound, not whether the code that wrote it still runs.
"""

import json
import re

import numpy as np
import pytest

from conftest import ROOT

PAGES = ROOT / 'web' / 'house-prices'
SITEMAP = ROOT / 'web' / 'sitemap.xml'
HOMEPAGE = ROOT / 'web' / 'index.html'
PAGE_MAP = ROOT / 'web' / 'data' / 'pages.json'
SITE = 'https://realhouseprices.uk'

# Google truncates a title around 60 characters and a description around 160.
# Past those the tail is dropped from the result, which is only a problem when
# the part that matters was in it - hence a ceiling rather than a target.
MAX_TITLE = 62
MAX_DESCRIPTION = 165

# A price that has drifted from the exported matrix means the page and the map
# are telling a visitor two different things. Rounding to the pound is the only
# difference either should ever have.
PRICE_TOLERANCE = 1.0


def _read(path):
    return path.read_text(encoding = 'utf-8')


@pytest.fixture(scope = 'session')
def pages():
    if not PAGES.exists():
        pytest.skip('web/house-prices is absent - run step 08')
    found = {p.parent.name if p.parent != PAGES else '': _read(p)
             for p in PAGES.glob('**/index.html')}
    assert found, 'no pages found in web/house-prices'
    return found


@pytest.fixture(scope = 'session')
def sitemap_urls():
    if not SITEMAP.exists():
        pytest.skip('web/sitemap.xml is absent - run step 08')
    return re.findall(r'<loc>([^<]+)</loc>', _read(SITEMAP))


####################
# Shape


def test_every_page_has_exactly_one_h1(pages):
    """A page with two h1s has no top level, and one with none has no subject.

    The homepage went without one for its whole life, which is what kept it
    from ranking for anything at all - not a mistake worth repeating 43 times.
    """
    wrong = {slug: len(re.findall(r'<h1[ >]', html))
             for slug, html in pages.items()
             if len(re.findall(r'<h1[ >]', html)) != 1}
    assert not wrong, f'pages without exactly one h1: {wrong}'


def test_every_page_has_a_title_and_description(pages):
    missing = [slug for slug, html in pages.items()
               if not re.search(r'<title>.+?</title>', html, re.S)
               or not re.search(r'<meta name="description" content=".+?">', html, re.S)]
    assert not missing, f'pages missing a title or description: {missing}'


def test_titles_and_descriptions_fit_the_result(pages):
    """Long enough to be dropped mid-phrase is long enough to be worth seeing."""
    long_titles, long_descriptions = [], []
    for slug, html in pages.items():
        title = re.search(r'<title>(.*?)</title>', html, re.S).group(1)
        desc = re.search(r'<meta name="description" content="(.*?)">', html, re.S).group(1)
        if len(title) > MAX_TITLE:
            long_titles.append((slug, len(title)))
        if len(' '.join(desc.split())) > MAX_DESCRIPTION:
            long_descriptions.append((slug, len(desc)))
    assert not long_titles, f'titles past {MAX_TITLE} characters: {long_titles}'
    assert not long_descriptions, (
        f'descriptions past {MAX_DESCRIPTION} characters: {long_descriptions}')


def test_every_page_is_its_own_canonical(pages):
    """A canonical pointing anywhere but at the page itself hands the ranking
    to whatever it points at, which is the one way to make 43 pages count as
    one."""
    wrong = []
    for slug, html in pages.items():
        canonical = re.search(r'<link rel="canonical" href="([^"]+)">', html)
        expected = f'{SITE}/house-prices/' + (f'{slug}/' if slug else '')
        if not canonical or canonical.group(1) != expected:
            wrong.append((slug, canonical.group(1) if canonical else None))
    assert not wrong, f'pages whose canonical is not their own URL: {wrong}'


def test_no_chart_came_out_empty(pages):
    """An area with no series draws a path with no 'd', which renders as a
    blank box rather than as an error - invisible unless it is looked for."""
    empty = [slug for slug, html in pages.items()
             if 'pg-real' in html and re.search(r'class="pg-real" d=""', html)]
    assert not empty, f'pages with an empty chart: {empty}'

    missing = [slug for slug, html in pages.items() if 'pg-real' not in html]
    assert not missing, f'pages with no chart at all: {missing}'


def test_the_licence_notice_travels_onto_every_page(pages):
    """OGL v3.0 requires attribution wherever the data is shown, and these
    pages are where most people will meet it rather than the homepage."""
    bare = [slug for slug, html in pages.items()
            if 'Open Government Licence' not in html
            or 'HM Land Registry' not in html]
    assert not bare, f'pages without the licence notice: {bare}'


####################
# Agreement with the data the map reads


def test_the_headline_price_matches_the_exported_matrix(pages, meta, prices):
    """The page and the map have to quote the same number.

    A visitor who reads a price here, clicks through to the map and sees a
    different one has been told a lie by one of the two, with nothing on either
    to say which. Both come from web/data, so they can only differ if step 08
    has drifted from what it decodes.
    """
    by_slug = {}
    for i, area in enumerate(meta['areas']):
        slug = re.sub(r'[^a-z0-9]+', '-', area['n'].lower()).strip('-')
        by_slug.setdefault(slug, i)
        if area['c'] == 'K02000001':
            by_slug[''] = i          # the index page is the UK's own page

    checked, wrong = 0, []
    for slug, html in pages.items():
        if slug not in by_slug:
            continue
        area = by_slug[slug]
        shown = re.search(r'<span class="pg-stat-value">£([\d,]+)</span>', html)
        if not shown:
            continue
        expected = prices[0][area][-1]
        if not np.isfinite(expected):
            continue
        checked += 1
        if abs(float(shown.group(1).replace(',', '')) - expected) > PRICE_TOLERANCE:
            wrong.append((slug, shown.group(1), round(expected)))

    assert checked, 'no page headline could be matched to an area'
    assert not wrong, f'pages quoting a price the matrix disagrees with: {wrong}'


def test_every_area_without_a_boundary_has_a_page(pages, meta):
    """The series that have no polygon are exactly the ones the map cannot
    show, so a page is the only way anyone reaches them."""
    slugs = set(pages)
    missing = []
    for area in meta['areas'][meta['geoAreas']:]:
        if area['c'] == 'K02000001':
            continue                  # the UK lives on the index page
        slug = re.sub(r'[^a-z0-9]+', '-', area['n'].lower()).strip('-')
        if slug not in slugs:
            missing.append(area['n'])
    assert not missing, f'areas without a page: {missing}'


####################
# Links


def test_internal_links_point_at_something(pages):
    """A link to a page that was renamed away is a dead end a crawler follows
    once and a visitor follows never again."""
    dead = []
    for slug, html in pages.items():
        for href in re.findall(r'href="(/house-prices/[^"]*)"', html):
            target = href.strip('/').split('/')
            name = target[1] if len(target) > 1 else ''
            if name and not (PAGES / name / 'index.html').exists():
                dead.append((slug, href))
    assert not dead, f'links with no page behind them: {dead[:8]}'


def test_every_page_links_back_to_the_index(pages):
    orphans = [slug for slug, html in pages.items()
               if slug and 'href="/house-prices/"' not in html]
    assert not orphans, f'pages with no way back to the index: {orphans}'


def test_the_index_links_to_every_page(pages):
    index = pages.get('')
    assert index is not None, 'no index page in web/house-prices'
    linked = set(re.findall(r'href="/house-prices/([^/"]+)/"', index))
    unlinked = sorted(slug for slug in pages if slug and slug not in linked)
    assert not unlinked, f'pages the index does not link to: {unlinked}'


def test_the_map_links_carry_a_code_the_data_knows(pages, meta):
    """The deep link is by ONS code rather than by name, because names collide
    - the West Midlands is both a region and a county. A code the export has
    never heard of silently drops the visitor on the default area instead."""
    codes = {area['c'] for area in meta['areas']}
    unknown = []
    for slug, html in pages.items():
        for code in re.findall(r'href="/\?area=([^"]+)"', html):
            if code not in codes:
                unknown.append((slug, code))
    assert not unknown, f'map links with a code the data does not have: {unknown}'


####################
# The sitemap


def test_the_sitemap_lists_every_page_and_nothing_else(pages, sitemap_urls):
    """A sitemap that names a page which does not exist teaches a crawler to
    trust it less; one that leaves a page out is the reason it never gets
    found."""
    listed = {url for url in sitemap_urls if '/house-prices/' in url}
    expected = {f'{SITE}/house-prices/' + (f'{slug}/' if slug else '')
                for slug in pages}
    assert listed == expected, (
        f'missing from the sitemap: {sorted(expected - listed)[:5]}; '
        f'listed but absent: {sorted(listed - expected)[:5]}')


def test_the_sitemap_includes_the_homepage(sitemap_urls):
    assert f'{SITE}/' in sitemap_urls, 'the homepage is not in the sitemap'


def test_the_sitemap_dates_match_the_export(sitemap_urls, meta):
    """lastmod is generated from meta.generated for exactly this reason: a date
    that stops matching the data is one a crawler stops believing."""
    dates = set(re.findall(r'<lastmod>([^<]+)</lastmod>', _read(SITEMAP)))
    assert dates == {meta['generated']}, (
        f'sitemap dates {sorted(dates)} against export {meta["generated"]}')


####################
# The way in from the rest of the site


def test_the_homepage_links_to_the_area_pages():
    """Without this the 43 pages are orphans.

    A sitemap tells a crawler a page exists; a link tells it the page matters,
    and only the link passes any authority to it. Pages that are listed and
    never linked get crawled, indexed and then left at the bottom - which is
    the whole of the difference between publishing them and ranking them.

    It has to be in the markup rather than built by JavaScript, which is why
    this reads index.html rather than anything the app renders at runtime.
    """
    html = HOMEPAGE.read_text(encoding = 'utf-8')
    assert 'href="/house-prices/"' in html, (
        'index.html has no static link to /house-prices/ - the area pages are '
        'reachable only from the sitemap')


def test_the_page_map_matches_the_pages_on_disk(pages):
    """The app reads this to decide whether to offer a link through.

    An entry with no page behind it is a 404 handed to a reader who trusted the
    button; a page with no entry is a page the tool never offers at all.
    """
    if not PAGE_MAP.exists():
        pytest.skip('web/data/pages.json is absent - run step 08')

    mapping = json.loads(PAGE_MAP.read_text(encoding = 'utf-8'))

    dead = {code: url for code, url in mapping.items()
            if url.strip('/').split('/')[-1] != 'house-prices'
            and url.strip('/').split('/')[-1] not in pages}
    assert not dead, f'page map entries with no page behind them: {dead}'

    linked = {url.strip('/').split('/')[-1] for url in mapping.values()}
    unoffered = sorted(slug for slug in pages
                       if slug and slug not in linked)
    assert not unoffered, f'pages the app is never told about: {unoffered}'


def test_the_page_map_only_names_areas_the_data_has(meta):
    if not PAGE_MAP.exists():
        pytest.skip('web/data/pages.json is absent - run step 08')

    mapping = json.loads(PAGE_MAP.read_text(encoding = 'utf-8'))
    codes = {area['c'] for area in meta['areas']}
    unknown = sorted(set(mapping) - codes)
    assert not unknown, f'page map names areas the export does not have: {unknown}'


def test_every_page_links_to_the_hub_in_its_markup(pages):
    """Every page carries the nav link, so the hub is one hop from anywhere."""
    missing = [slug or '(index)' for slug, html in pages.items()
               if 'href="/house-prices/"' not in html]
    assert not missing, f'pages with no link to the hub: {missing}'


def test_the_peak_each_page_quotes_is_its_own(pages, meta, prices):
    """A page that names a peak has to name the month its own series peaked.

    An earlier version quoted September 2007 on every page, borrowed from the
    national story. Only three of the forty-three peak that month in real terms
    - Surrey peaks in 2016, the South East in 2021, Greater Manchester in 2022 -
    so forty pages asserted something the chart directly above them contradicted.
    Wrong on the one claim the whole site trades on, and invisible without this.
    """
    cpi = np.array(meta['cpi'], dtype = float)
    start_year, start_month = (int(v) for v in meta['months']['start'].split('-'))
    months = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
              'August', 'September', 'October', 'November', 'December']

    def label(i):
        total = start_year * 12 + (start_month - 1) + i
        return f'{months[total % 12]} {total // 12}'

    by_slug = {}
    for i, area in enumerate(meta['areas']):
        slug = re.sub(r'[^a-z0-9]+', '-', area['n'].lower()).strip('-')
        by_slug.setdefault(slug, i)
        if area['c'] == 'K02000001':
            by_slug[''] = i          # the index page is the UK's own page

    checked, wrong = 0, []
    for slug, html in pages.items():
        if slug not in by_slug:
            continue
        area = by_slug[slug]
        # Each housing type states its own peak, so each one is checked
        for block in re.findall(r'data-type="(\d+)"[^>]*>(.*?)'
                                r'(?=<div class="pg-type"|\Z)', html, re.S):
            t, body = int(block[0]), block[1]
            shown = re.search(r'Below its ([A-Z][a-z]+ \d{4}) peak', body)
            if not shown:
                continue
            series = prices[t][area] / (cpi / cpi[-1])
            if np.all(np.isnan(series)):
                continue
            checked += 1
            expected = label(int(np.nanargmax(series)))
            if shown.group(1) != expected:
                wrong.append((slug, t, shown.group(1), expected))

    assert checked, 'no page states a peak month - has the tile been removed?'
    assert not wrong, f'pages naming a peak that is not their own: {wrong}'


def test_every_page_has_a_working_type_picker(pages, meta):
    """The dropdown switches between blocks that are already in the markup.

    Which means three things have to hold together: an option per housing type,
    a block per housing type wherever the page shows a figure, and exactly one
    of each set on show. A missing block leaves the page blank when that type is
    picked; a second unhidden one stacks two readings on top of each other.
    """
    types = len(meta['types'])
    broken = []
    for slug, html in pages.items():
        options = len(re.findall(r'<option value="\d+">', html))
        blocks = re.findall(r'<div class="pg-type" data-type="(\d+)"( hidden)?>', html)
        shown = [t for t, hidden in blocks if not hidden]
        counts = {t for t, _ in blocks}

        if options != types:
            broken.append((slug, f'{options} options for {types} types'))
        elif counts != set(str(t) for t in range(types)):
            broken.append((slug, f'blocks cover {sorted(counts)}'))
        elif len(blocks) % types:
            broken.append((slug, f'{len(blocks)} blocks is not a multiple of {types}'))
        elif set(shown) != {'0'} or len(shown) != len(blocks) // types:
            broken.append((slug, f'visible blocks: {shown}'))

    assert not broken, f'pages with a broken type picker: {broken[:5]}'


def test_the_hidden_blocks_are_actually_hidden():
    """The blocks sit on grids and flex rows, and a display rule on an element
    beats the browser's own [hidden] default. Without this one line every page
    shows all five housing types stacked on top of each other."""
    css = (ROOT / 'web' / 'css' / 'style.css').read_text(encoding = 'utf-8')
    assert re.search(r'\[hidden\]\s*{[^}]*display:\s*none\s*!important', css), (
        'style.css has no [hidden] { display: none !important } rule')


def test_no_page_claims_history_it_does_not_have(pages, meta, prices):
    """The open-ended column has to start where the series actually starts.

    Northern Ireland, Scotland and the UK publish an overall index back to 1995
    but no breakdown by property type until 2004 or 2005. Reading that column
    off the start of the axis regardless produced 'Since 1995, from January
    1995' above two dashes - a page that looks broken rather than one saying
    the data was never collected.
    """
    by_slug = {}
    for i, area in enumerate(meta['areas']):
        slug = re.sub(r'[^a-z0-9]+', '-', area['n'].lower()).strip('-')
        by_slug.setdefault(slug, i)
        if area['c'] == 'K02000001':
            by_slug[''] = i          # the index page is the UK's own page

    start_year, start_month = (int(v) for v in meta['months']['start'].split('-'))

    checked, wrong, blank = 0, [], []
    for slug, html in pages.items():
        if slug not in by_slug:
            continue
        area = by_slug[slug]
        for t, body in re.findall(r'data-type="(\d+)"[^>]*>(.*?)'
                                  r'(?=<div class="pg-type"|\Z)', html, re.S):
            t = int(t)
            claimed = re.search(r'<th scope="col">Since (\d{4})', body)
            if not claimed:
                continue

            observed = np.flatnonzero(np.isfinite(prices[t][area]))
            if not observed.size:
                continue
            total = start_year * 12 + (start_month - 1) + int(observed[0])
            checked += 1
            if claimed.group(1) != str(total // 12):
                wrong.append((slug, t, claimed.group(1), total // 12))

            # A column that survived the filter has to carry figures, not dashes
            table = re.search(r'<table class="pg-table pg-wide">.*?</table>', body, re.S)
            if table and re.search(r'<td class="pg-num[^"]*">-</td>', table.group(0)):
                blank.append((slug, t))

    assert checked, 'no page carries an open-ended column'
    assert not wrong, f'pages claiming history before their data starts: {wrong}'
    assert not blank, f'pages with an empty cell in the change table: {blank[:5]}'
