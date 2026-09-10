"""This refresh against the last one, to catch what only movement shows up.

A file can be well formed and plausible and still be wrong in a way nothing but
its predecessor exposes: an axis that has lost a decade, a reorganisation that
renumbered every area, a rebase that shifted a whole series by a constant. A
refresh ought to be boring - a month longer, the same areas, the same history.

The comparison reads the previous release out of git rather than from a
baseline file kept next to the tests, because web/data is committed and history
already holds exactly what was last deployed. See the 'previous' fixture.

Land Registry figures get revised, so the history is allowed to move a little.
Revisions concentrate in the most recent months, which is why the tail is
checked separately and loosely.
"""

import numpy as np
import pytest

from conftest import HOUSING_TYPES

# A monthly refresh adds one month. Room for a couple of skipped runs, and for
# a re-export over the same source data adding none at all.
MAX_NEW_MONTHS = 4

# Local authority reorganisations do happen - the 2023 round merged a dozen
# districts into new unitaries - but they arrive a handful at a time.
MAX_AREAS_ADDED = 30
MAX_AREAS_REMOVED = 30

# Revisions to the settled history. The stored index is relative to each area's
# first observation, which does not move, so overlapping cells compare
# directly. In practice most of them come back unchanged.
SETTLED_TAIL_MONTHS = 6          # months held out of the strict comparison
SETTLED_TOLERANCE = 0.02         # 2% per cell
SETTLED_SHARE = 0.99             # of cells that have to be within it
SETTLED_CEILING = 0.25           # no settled cell may move further than this

# The recent tail is genuinely provisional and can be restated substantially.
RECENT_CEILING = 0.40

# Cells that had a value last time and have none now. A handful turn up when
# the source withdraws a thin-market figure; a wave of them means an area or a
# whole type stopped being published.
MAX_CELLS_LOST = 500


def _aligned(meta, matrices, previous, t):
    """This release's matrix and the last one's, cut down to their common cells."""
    codes = [area['c'] for area in meta['areas']]
    common = [code for code in codes if code in previous.index]
    if not common:
        pytest.skip('no areas in common with the previous release')

    n_months = min(meta['months']['count'], previous.meta['months']['count'])
    current_index = {code: i for i, code in enumerate(codes)}

    now = matrices[t][[current_index[code] for code in common]][:, :n_months]
    then = previous.matrix(t)[[previous.index[code] for code in common]][:, :n_months]
    return common, now.astype(np.float64), then.astype(np.float64)


####################
# Shape


def test_the_month_axis_only_grows(meta, previous):
    assert meta['months']['start'] == previous.meta['months']['start'], (
        'the month axis starts in a different month than it did last time, so '
        'every stored series has shifted against the axis it is read with')

    added = meta['months']['count'] - previous.meta['months']['count']
    assert added >= 0, f'the axis lost {-added} months'
    assert added <= MAX_NEW_MONTHS, (
        f'the axis gained {added} months in a single refresh')


def test_the_scale_and_type_list_are_unchanged(meta, previous):
    assert meta['scale'] == previous.meta['scale']
    assert meta['types'] == previous.meta['types']


def test_no_area_disappeared_quietly(meta, previous):
    """Areas can be added or retired, but not by the dozen.

    A large removal is usually the boundary release and the price data failing
    to meet: step 06 keeps only the areas present in both, so a change to
    either one can empty the map without erroring.
    """
    now = {area['c'] for area in meta['areas']}
    then = set(previous.codes)

    removed = sorted(then - now)
    added = sorted(now - then)

    assert len(removed) <= MAX_AREAS_REMOVED, (
        f'{len(removed)} areas are gone: {removed[:8]}')
    assert len(added) <= MAX_AREAS_ADDED, (
        f'{len(added)} areas are new: {added[:8]}')


def test_the_mappable_range_kept_pace_with_the_area_list(meta, previous):
    """geoAreas has to move with the area count, not independently of it.

    Everything the map does is bounded by geoAreas. If it drifted while the
    list stayed put, the map would either stop short of real local authorities
    or run off the end of them into the national series.
    """
    aggregates_now = len(meta['areas']) - meta['geoAreas']
    aggregates_then = len(previous.meta['areas']) - previous.meta['geoAreas']
    assert aggregates_now == aggregates_then, (
        f'{aggregates_now} non-mappable series this time, {aggregates_then} last')


def test_area_names_are_stable(meta, previous):
    """The same code should still be carrying the same name.

    The name is what the dropdown and the headline show, so a code that has
    changed name is worth seeing here rather than discovering in the UI.
    """
    now = {area['c']: area['n'] for area in meta['areas']}
    renamed = [(code, area['n'], now[code])
               for code, area in ((a['c'], a) for a in previous.meta['areas'])
               if code in now and now[code] != area['n']]
    assert not renamed, f'renamed areas: {renamed[:5]}'


####################
# Values


@pytest.mark.parametrize('t', range(len(HOUSING_TYPES)))
def test_the_settled_history_barely_moves(t, meta, matrices, previous):
    common, now, then = _aligned(meta, matrices, previous, t)
    if now.shape[1] <= SETTLED_TAIL_MONTHS:
        pytest.skip('not enough overlapping history to compare')

    now = now[:, :-SETTLED_TAIL_MONTHS]
    then = then[:, :-SETTLED_TAIL_MONTHS]

    both = (now > 0) & (then > 0)
    assert both.sum(), 'no overlapping observations to compare'

    change = np.zeros_like(now)
    change[both] = np.abs(now[both] / then[both] - 1)

    share = float((change[both] <= SETTLED_TOLERANCE).mean())
    assert share >= SETTLED_SHARE, (
        f'only {share:.2%} of settled {meta["types"][t]} values are within '
        f'{SETTLED_TOLERANCE:.0%} of the previous release')

    area, month = np.unravel_index(int(np.argmax(change)), change.shape)
    assert change.max() <= SETTLED_CEILING, (
        f'{meta["types"][t]} restated by {change.max():.0%}, worst at '
        f'{common[area]} month {month} of the overlap')


@pytest.mark.parametrize('t', range(len(HOUSING_TYPES)))
def test_the_recent_months_were_only_revised(t, meta, matrices, previous):
    """The provisional tail is allowed to move, but it is still the same market."""
    common, now, then = _aligned(meta, matrices, previous, t)
    now = now[:, -SETTLED_TAIL_MONTHS:]
    then = then[:, -SETTLED_TAIL_MONTHS:]

    both = (now > 0) & (then > 0)
    if not both.sum():
        pytest.skip('no overlapping recent observations')

    change = np.abs(now[both] / then[both] - 1)

    assert change.max() <= RECENT_CEILING, (
        f'a recent {meta["types"][t]} figure was restated by {change.max():.0%}')


@pytest.mark.parametrize('t', range(len(HOUSING_TYPES)))
def test_observations_are_not_lost(t, meta, matrices, previous):
    common, now, then = _aligned(meta, matrices, previous, t)
    lost = int(((then > 0) & (now == 0)).sum())
    assert lost <= MAX_CELLS_LOST, (
        f'{lost} {meta["types"][t]} observations that were there last time are '
        'now missing')


@pytest.mark.parametrize('t', range(len(HOUSING_TYPES)))
def test_the_refresh_added_data(t, meta, matrices, previous):
    """A refresh that gained a month has to have gained observations with it.

    An axis extended over an empty column is what this catches: the map opens
    on the new month and shows nothing at all.
    """
    if meta['months']['count'] == previous.meta['months']['count']:
        pytest.skip('same number of months - nothing new was expected')

    added = matrices[t][:, previous.meta['months']['count']:]
    assert (added > 0).any(), (
        f'the axis grew but the new {meta["types"][t]} months are empty')


def test_base_prices_are_unchanged_for_areas_that_kept_their_history(meta, previous):
    """The base is each area's first observation, which is settled history.

    It moving means the area's series now starts in a different month - so
    every stored index for it is relative to a new anchor, and any comparison
    with the previous release, the tests above included, is measuring the
    rebase rather than the data. Revisions to the first month itself are real
    but tiny, which is what the tolerance is for.
    """
    drifted = []
    for t in range(len(meta['types'])):
        now = dict(zip((a['c'] for a in meta['areas']), meta['base'][t]))
        for code, was in zip(previous.codes, previous.meta['base'][t]):
            if code not in now or not was:
                continue
            if abs(now[code] / was - 1) > SETTLED_TOLERANCE:
                drifted.append((meta['types'][t], code, was, now[code]))

    assert not drifted, f'rebased areas: {drifted[:5]}'


def test_the_cpi_series_agrees_with_the_previous_release(meta, previous):
    """Compared on its own terms, since the series is rebased every refresh.

    A new CPI month moves the base month, and with it every value in the
    series. Dividing both by their value in the last common month cancels that
    out and leaves the actual history to be compared.
    """
    now = np.asarray(meta['cpi'], dtype = np.float64)
    then = np.asarray(previous.meta['cpi'], dtype = np.float64)

    n = min(len(now), len(then))
    if n < 2:
        pytest.skip('no overlapping CPI history')

    rebased_now = now[:n] / now[n - 1]
    rebased_then = then[:n] / then[n - 1]

    drift = float(np.abs(rebased_now / rebased_then - 1).max())
    assert drift < 0.01, (
        f'the CPI history moved by up to {drift:.2%} once rebased to the last '
        'common month - the ONS revises the index rarely, so this is more '
        'likely to be the wrong series, or a changed base')


####################
# Boundaries and labels


def test_the_boundaries_did_not_change_shape_wholesale(lads, previous):
    """The geometry comes from a yearly ONS release, not from the monthly data.

    Step 06 rewrites lads.geojson on every run, so a change in the feature
    count between two monthly refreshes means the geography moved underneath -
    which is worth knowing, because the area indices move with it.
    """
    then = previous.json('lads.geojson')
    assert len(lads['features']) == len(then['features']), (
        f'{len(lads["features"])} boundaries now, {len(then["features"])} '
        'before - the geography release has changed')
