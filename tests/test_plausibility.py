"""Whether the numbers are believable as UK house prices.

A change of units at source, a column swapped for its neighbour, a deflator
applied twice - all three produce a perfectly well formed export. What gives
them away is the values: prices in the wrong order of magnitude, month on month
jumps no housing market makes, inflation running backwards.

The bounds here are deliberately wide. They are meant to catch a refresh that
has gone wrong rather than to pin the market down, so each one sits well
outside the range the current data occupies and the comment says where the real
figure is.
"""

import numpy as np
import pandas as pd
import pytest

from conftest import HOUSING_TYPES

# The cheapest average in the series is about £23k (1995), the dearest single
# figure about £2.9m (City of London terraced, on a handful of sales).
PRICE_FLOOR = 5_000
PRICE_CEILING = 10_000_000

# Month on month moves. The extremes come from City of London, Kensington and
# the Isles of Scilly, where a month's average rests on very few transactions:
# the largest in the current data is about 35%, and 8 cells out of 136,000 get
# past 20%. A change of units would move every cell at once, which is what the
# share test below catches; this ceiling is for a single corrupted figure.
MONTHLY_MOVE_CEILING = 0.60
MONTHLY_MOVE_TYPICAL = 0.25
MONTHLY_MOVE_TYPICAL_SHARE = 0.999

# The UK average across all types in the latest month: £272k as at mid-2026. A
# band this wide holds for years while still catching a factor of ten.
UK_PRICE_BAND = (120_000, 800_000)

# CPI month on month, on the index as rebased by step 05. Monthly deflation is
# normal - 74 of the 377 steps are negative - and the largest rise in the
# series is 2.5%.
CPI_MOVE_FLOOR = -0.03
CPI_MOVE_CEILING = 0.05

# Cumulative inflation since January 1995, which is 1 / cpi[0]. Currently 2.17.
CPI_TOTAL_BAND = (1.5, 5.0)

# The Land Registry publishes about two months in arrears, and the axis is
# built from the data rather than from the calendar.
MAX_PUBLICATION_LAG_MONTHS = 8


####################
# Price levels


@pytest.mark.parametrize('t', range(len(HOUSING_TYPES)))
def test_prices_are_in_pounds(t, meta, prices, months):
    """Every recorded price sits inside a plausible range for a UK average.

    Pence, thousands of pounds, or an index left undivided would all land
    outside this by orders of magnitude.
    """
    values = prices[t]
    recorded = np.isfinite(values)

    low = np.argwhere(recorded & (values < PRICE_FLOOR))
    high = np.argwhere(recorded & (values > PRICE_CEILING))

    def describe(cells):
        return [f'{meta["areas"][a]["n"]} {months[m]:%Y-%m} {values[a, m]:.0f}'
                for a, m in cells[:5]]

    assert not len(low), f'implausibly cheap: {describe(low)}'
    assert not len(high), f'implausibly dear: {describe(high)}'


def test_the_uk_average_is_where_it_should_be(meta, prices, months):
    area = [a['c'] for a in meta['areas']].index('K02000001')
    latest = prices[0][area, -1]
    low, high = UK_PRICE_BAND
    assert low <= latest <= high, (
        f'the UK average for {months[-1]:%B %Y} is {latest:,.0f}')


def test_prices_have_risen_since_the_start_of_the_series(meta, prices):
    """The UK average has roughly quintupled in nominal terms since 1995.

    Reversed, this is the check that notices a month axis built backwards or a
    series read from the bottom up.
    """
    area = [a['c'] for a in meta['areas']].index('K02000001')
    series = prices[0][area]
    assert series[-1] > 2 * series[0], (
        f'the UK average went from {series[0]:,.0f} to {series[-1]:,.0f}')


def test_real_growth_is_positive_but_smaller_than_nominal(meta, prices):
    """Deflating has to reduce past growth, never increase it.

    Done the wrong way round - multiplying by the CPI index instead of dividing
    - real growth comes out larger than nominal, which is the single easiest
    thing on the chart to get backwards.
    """
    area = [a['c'] for a in meta['areas']].index('K02000001')
    cpi = np.asarray(meta['cpi'], dtype = np.float64)
    series = prices[0][area]

    nominal = series[-1] / series[0]
    real = (series[-1] / cpi[-1]) / (series[0] / cpi[0])

    assert 1.0 < real < nominal, f'nominal {nominal:.2f}x, real {real:.2f}x'


####################
# Movement over time


@pytest.mark.parametrize('t', range(len(HOUSING_TYPES)))
def test_no_single_month_moves_impossibly(t, meta, prices, months):
    values = prices[t]
    with np.errstate(invalid = 'ignore'):
        move = values[:, 1:] / values[:, :-1] - 1

    extreme = np.argwhere(np.isfinite(move) & (np.abs(move) > MONTHLY_MOVE_CEILING))
    described = [f'{meta["areas"][a]["n"]} {months[m + 1]:%Y-%m} {move[a, m]:+.0%}'
                 for a, m in extreme[:5]]
    assert not len(extreme), f'month on month moves beyond reason: {described}'


@pytest.mark.parametrize('t', range(len(HOUSING_TYPES)))
def test_monthly_moves_are_almost_all_small(t, prices):
    """The distribution as a whole, rather than its tail.

    Thin-market areas throw out the occasional 30% month, but if any real share
    of every area is moving that far then the fault is in the data rather than
    in the market.
    """
    values = prices[t]
    with np.errstate(invalid = 'ignore'):
        move = values[:, 1:] / values[:, :-1] - 1
    move = move[np.isfinite(move)]

    share = float((np.abs(move) <= MONTHLY_MOVE_TYPICAL).mean())
    assert share >= MONTHLY_MOVE_TYPICAL_SHARE, (
        f'only {share:.4%} of monthly moves are within '
        f'{MONTHLY_MOVE_TYPICAL:.0%}')


def test_area_series_do_not_repeat_one_value_forever(meta, matrices):
    """A series that never changes is a fill forward, not a housing market.

    Worth catching because it survives every other check here: the values are
    in range, the format is right, and the map simply shows nothing happening.
    """
    matrix = matrices[0]
    frozen = []
    for area in range(matrix.shape[0]):
        recorded = matrix[area][matrix[area] > 0]
        if len(recorded) > 24 and len(np.unique(recorded)) < 3:
            frozen.append(meta['areas'][area]['n'])

    assert not frozen, f'series that barely move: {frozen[:5]}'


####################
# Inflation


def test_inflation_moves_month_to_month_within_reason(meta):
    cpi = np.asarray(meta['cpi'], dtype = np.float64)
    move = np.diff(cpi) / cpi[:-1]
    assert move.min() >= CPI_MOVE_FLOOR, f'CPI fell {move.min():.2%} in one month'
    assert move.max() <= CPI_MOVE_CEILING, f'CPI rose {move.max():.2%} in one month'


def test_inflation_since_1995_is_plausible(meta):
    cpi = np.asarray(meta['cpi'], dtype = np.float64)
    total = 1 / cpi[0]
    low, high = CPI_TOTAL_BAND
    assert low <= total <= high, (
        f'prices would have to have risen {total:.2f}x since '
        f'{meta["months"]["start"]} for this CPI series to be right')


def test_inflation_trends_upwards(meta):
    """Not month by month - individual months do fall - but decade by decade."""
    cpi = pd.Series(meta['cpi'])
    yearly = cpi.groupby(cpi.index // 12).mean()
    falls = (yearly.diff() < 0).sum()
    assert falls <= 2, f'{falls} years of average deflation in the CPI series'


####################
# Freshness
#
# Marked so that a run outside an update window can leave them out:
#   pytest -m 'not freshness'


@pytest.mark.freshness
def test_the_export_is_recent(meta):
    generated = pd.to_datetime(meta['generated'])
    age = (pd.Timestamp.today().normalize() - generated).days
    assert age <= 45, (
        f'web/data was generated {age} days ago ({meta["generated"]}) - a push '
        'now would deploy that vintage')


@pytest.mark.freshness
def test_the_data_reaches_close_to_the_present(meta, months):
    """The axis should end within a couple of months of the export date.

    The lag is the Land Registry's publication schedule. A lag that grows means
    step 01 fell back through several months and found nothing new, which it
    prints as a warning and otherwise carries on from.
    """
    generated = pd.to_datetime(meta['generated']).to_period('M')
    lag = (generated - months[-1].to_period('M')).n
    assert lag <= MAX_PUBLICATION_LAG_MONTHS, (
        f'the latest month is {months[-1]:%Y-%m} but the export was generated '
        f'in {generated} - {lag} months of lag')
