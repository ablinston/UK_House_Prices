"""Agreement between the exported files, and with the pipeline's own input.

Every file in web/data can go on being well formed in itself long after the
four of them have stopped describing the same world. These are the checks that
hold them together: the area index means the same thing everywhere, the base
prices and the matrices agree about which areas have data, and the numbers the
browser recovers are the ones in the parquet they came from.
"""

import numpy as np
import pandas as pd
import pytest

from conftest import AGGREGATE_CODES, HOUSING_TYPES

# Every local authority has an Overall series, but the type breakdowns are
# thinner: the 11 Northern Ireland districts carry no detached, semi, terraced
# or flat figures at all. Room for those and a couple more, but not for a
# wholesale loss.
MAX_AREAS_WITHOUT_A_TYPE = 20

# Areas sampled for the parquet cross-check. Enough to catch an indexing error,
# which shows up in the first cell it touches, without reading the whole
# 4.7 MB file back cell by cell.
CROSS_CHECK_AREAS = 40


####################
# Within web/data


@pytest.mark.parametrize('t', range(len(HOUSING_TYPES)))
def test_a_base_price_exists_for_every_series(t, meta, matrices):
    """base[type][area] is zero in exactly the places the matrix is empty.

    The browser multiplies by the base to get back to pounds, so a series with
    no base charts as a flat zero, and a base with no series is dead weight
    that hides an area having been dropped.
    """
    has_data = matrices[t].any(axis = 1)
    has_base = np.asarray(meta['base'][t], dtype = np.float64) > 0

    missing_base = [meta['areas'][i]['n']
                    for i in np.flatnonzero(has_data & ~has_base)]
    orphan_base = [meta['areas'][i]['n']
                   for i in np.flatnonzero(has_base & ~has_data)]

    assert not missing_base, f'series with no base price: {missing_base[:5]}'
    assert not orphan_base, f'base price with no series: {orphan_base[:5]}'


def test_every_area_has_an_overall_series(meta, matrices):
    # An area is in meta at all because it has HPI rows, and the overall
    # average is the one column the Land Registry always publishes
    empty = [meta['areas'][i]['n'] for i in np.flatnonzero(~matrices[0].any(axis = 1))]
    assert not empty, f'areas with no Overall data at all: {empty[:5]}'


@pytest.mark.parametrize('t', range(1, len(HOUSING_TYPES)))
def test_type_breakdowns_cover_almost_every_area(t, meta, matrices):
    empty = [meta['areas'][i]['n'] for i in np.flatnonzero(~matrices[t].any(axis = 1))]
    assert len(empty) <= MAX_AREAS_WITHOUT_A_TYPE, (
        f'{len(empty)} areas have no {meta["types"][t]} data: {empty[:8]}')


@pytest.mark.parametrize('t', range(len(HOUSING_TYPES)))
def test_the_latest_month_is_populated(t, meta, matrices):
    """The last month on the axis has to be a real month, not an empty column.

    The axis is built from the local authority date range, so its final month
    came from somewhere - but if only a handful of areas reached it, the map
    opens on a near-blank month and every reading defaults to missing.
    """
    reported = int((matrices[t][:meta['geoAreas'], -1] > 0).sum())
    share = reported / meta['geoAreas']
    assert share >= 0.9, (
        f'only {reported} of {meta["geoAreas"]} local authorities have '
        f'{meta["types"][t]} data in the final month')


def test_the_aggregate_series_are_complete(meta, matrices):
    """The UK and regional overall series should span the whole axis.

    They are the comparison lines on every chart, and they reach back further
    than the local authorities do, so a gap in one is a processing fault rather
    than data that was never published.
    """
    incomplete = [meta['areas'][i]['n']
                  for i in range(meta['geoAreas'], len(meta['areas']))
                  if not matrices[0][i].all()]
    assert not incomplete, f'aggregate series with missing months: {incomplete}'


def test_aggregates_have_no_boundary(meta, lads):
    # The other half of test_every_mappable_area_has_exactly_one_boundary: the
    # national and regional series have to stay outside the mappable range
    mapped = {feature['id'] for feature in lads['features']}
    assert not any(i in mapped for i in range(meta['geoAreas'], len(meta['areas'])))


def test_the_cpi_base_month_is_on_or_after_the_axis_end(meta, months):
    """Real prices are quoted in the money of cpiBase, which the footer shows.

    CPI is published a month or so ahead of the HPI, so the base month normally
    sits just past the end of the axis. Behind it means the deflator is older
    than the prices it is deflating, and today's money is a date in the past.
    """
    base = pd.to_datetime(meta['cpiBase'], format = '%B %Y')
    assert base >= months[-1], (
        f'cpiBase is {meta["cpiBase"]} but the price axis runs to '
        f'{months[-1]:%B %Y}')


def test_prices_are_deflated_towards_the_base_month(meta):
    """Step 05 rebases the CPI index so that the base month is 1.0.

    Every earlier month is therefore below 1, and dividing by it lifts an old
    price into today's money. A series scaled some other way - the ONS index on
    2015=100, say - would deflate in the wrong direction entirely.
    """
    cpi = np.asarray(meta['cpi'], dtype = np.float64)
    assert cpi.max() <= 1.0 + 1e-6, 'the CPI series is not rebased to its last month'
    assert cpi[-1] > 0.9, (
        f'the last CPI value is {cpi[-1]:.3f}, so the series is rebased to a '
        'month well past the end of the axis, or not rebased at all')


####################
# Against the pipeline's own output
#
# data/*.parquet is DVC-tracked and may not have been pulled; these skip when
# it is absent rather than failing.


def test_the_export_matches_the_parquet_it_came_from(meta, prices, months, hpi):
    """Recover the prices the way the browser does and compare with the source.

    This is the end to end check on step 06: the rebasing, the uint16 rounding,
    the area ordering and the month axis all have to be right together for a
    cell to land on its parquet value. The tolerance is half an index unit of
    the area's own base, which is what the rounding can cost - measured against
    the base rather than the value, because an area whose price has fallen
    since its first observation carries a base larger than the price being
    checked.
    """
    hpi = hpi.assign(Date = pd.to_datetime(hpi['Date']))
    index = {code: i for i, code in enumerate(area['c'] for area in meta['areas'])}
    month_index = {month: i for i, month in enumerate(months)}

    rng = np.random.default_rng(0)
    sample = rng.choice(len(meta['areas']), CROSS_CHECK_AREAS, replace = False)
    codes = {meta['areas'][i]['c'] for i in sample}

    checked = 0
    for row in hpi[hpi['AreaCode'].isin(codes)].itertuples():
        month = month_index.get(row.Date)
        if month is None:
            continue
        area = index[row.AreaCode]

        for t, house_type in enumerate(meta['types']):
            source = getattr(row, house_type + 'Price')
            if not np.isfinite(source) or source <= 0:
                continue

            exported = prices[t][area, month]
            assert np.isfinite(exported), (
                f'{row.AreaCode} {row.Date:%Y-%m} {house_type} is {source:.0f} in '
                'the parquet but missing from the export')

            tolerance = meta['base'][t][area] / (2 * meta['scale']) + 0.01
            assert abs(exported - source) <= tolerance, (
                f'{row.AreaCode} {row.Date:%Y-%m} {house_type}: exported '
                f'{exported:.2f}, parquet {source:.2f}')
            checked += 1

    assert checked > 1000, f'only {checked} values compared - the sample missed'


def test_the_month_axis_matches_the_local_authority_date_range(months, hpi, lad_list):
    """The axis is the local authority range, not the aggregates' 1968 start.

    Widening it to take in the national series would near-double every matrix
    for history only fourteen areas have.
    """
    dates = pd.to_datetime(hpi.loc[hpi['AreaCode'].isin(lad_list['ID']), 'Date'])
    assert months[0] == dates.min(), f'axis starts {months[0]:%Y-%m}, LADs {dates.min():%Y-%m}'
    assert months[-1] == dates.max(), f'axis ends {months[-1]:%Y-%m}, LADs {dates.max():%Y-%m}'


def test_every_area_in_the_export_is_a_lad_or_a_declared_aggregate(meta, lad_list):
    known = set(lad_list['ID']) | set(AGGREGATE_CODES)
    unexpected = [area['c'] for area in meta['areas'] if area['c'] not in known]
    assert not unexpected, f'exported areas that are neither: {unexpected[:5]}'


def test_no_lad_with_prices_was_left_out_of_the_export(meta, hpi, lad_list):
    """An area in both the boundary list and the price data has to be exported.

    Step 06 keeps the intersection of the two, so an area dropped from either
    side disappears off the map without a word being printed.
    """
    priced = set(hpi.loc[hpi['AreaCode'].isin(lad_list['ID']), 'AreaCode'])
    exported = {area['c'] for area in meta['areas']}
    assert not priced - exported, f'dropped local authorities: {sorted(priced - exported)[:5]}'


def test_the_cpi_series_was_aligned_not_resampled(meta, months, cpi):
    """Each month on the axis takes that month's own CPI value.

    Step 06 reindexes onto the axis and fills forward, so a month that falls
    inside the CPI series has to match it exactly; only months past the end of
    the series are allowed to repeat.
    """
    source = (cpi.assign(Date = pd.to_datetime(cpi['Date']))
              .set_index('Date')['cpi_index'])
    exported = pd.Series(meta['cpi'], index = months)

    overlap = exported.index.intersection(source.index)
    assert len(overlap) > 300, f'only {len(overlap)} months overlap the CPI series'

    # meta.json rounds the series to six decimal places
    difference = (exported[overlap] - source[overlap]).abs().max()
    assert difference < 1e-5, f'CPI values differ from the source by up to {difference}'
