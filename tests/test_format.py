"""Format of the exported web assets.

These are the checks the browser cannot make for itself. It assumes the shape
of every file it fetches, and when an assumption breaks it fails obscurely - a
blank map, an axis off by one, a chart of NaN - rather than saying what went
wrong. Everything here is a property the code in web/js relies on by
construction.
"""

import re

import numpy as np
import pytest

from conftest import (AGGREGATE_CODES, HOUSING_TYPES, UK_BBOX, WEB_DATA,
                      iter_points, iter_rings)

# ONS geography codes: one letter for the country or the tier, then eight digits
AREA_CODE = re.compile(r'^[A-Z]\d{8}$')

MONTH_START = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')

# Step 06 rounds coordinates to 4dp, about 11 m. Anything longer means the
# rounding was skipped and the payload is carrying precision nobody can see.
COORD_DP = 4

# Step 07 has five rank thresholds, so 0-4 inclusive
MAX_PLACE_RANK = 4

# The Land Registry publishes "King's Lynn and West Norfolk " with a trailing
# space, on every row and in every release the git history reaches back
# through. Nothing in the pipeline trims RegionName, so the export carries it
# through to the dropdown. Exempted by code rather than by dropping the check,
# which still holds for the other 404 names the source publishes.
KNOWN_UNTRIMMED_CODES = {'E07000146'}


####################
# meta.json


def test_meta_has_every_key_the_browser_reads(meta):
    for key in ('scale', 'types', 'months', 'geoAreas', 'areas', 'cpi', 'base',
                'cpiBase', 'generated'):
        assert key in meta, f'meta.json is missing {key}'


def test_scale_is_the_documented_index_unit(meta):
    assert meta['scale'] == 1000


def test_types_match_the_pipeline(meta):
    assert meta['types'] == HOUSING_TYPES


def test_one_matrix_file_per_type_and_no_others(meta):
    written = sorted(path.name for path in WEB_DATA.glob('prices-*.bin'))
    assert written == sorted(f'prices-{t}.bin' for t in range(len(meta['types']))), (
        'the prices-N.bin files and meta.types disagree - a stale matrix left '
        'behind gets loaded for whichever type it answers to')


def test_month_axis_is_a_start_and_a_count(meta):
    assert MONTH_START.match(meta['months']['start']), meta['months']['start']
    assert meta['months']['count'] > 0


def test_month_axis_starts_where_the_hpi_series_does(meta):
    # The Land Registry's local authority series begin in January 1995. A
    # different start is either a change at source or a filter that has quietly
    # dropped years off the front.
    assert meta['months']['start'] == '1995-01'


def test_area_codes_are_valid_and_unique(meta):
    codes = [area['c'] for area in meta['areas']]
    assert len(set(codes)) == len(codes), 'duplicate area codes'
    bad = [code for code in codes if not AREA_CODE.match(code)]
    assert not bad, f'malformed area codes: {bad[:5]}'


def test_area_names_are_present_and_trimmed(meta):
    for area in meta['areas']:
        assert area['n'], f'{area["c"]} has no name'
        if area['c'] in KNOWN_UNTRIMMED_CODES:
            continue
        assert area['n'] == area['n'].strip(), f'{area["c"]} name has stray whitespace'


def test_geo_areas_is_within_the_area_list(meta):
    assert 0 < meta['geoAreas'] <= len(meta['areas'])


def test_local_authorities_come_first_and_are_alphabetical(meta):
    # data.js and main.js both take [0, geoAreas) as the mappable range, so the
    # ordering here is load-bearing rather than cosmetic
    names = [area['n'] for area in meta['areas'][:meta['geoAreas']]]
    assert names == sorted(names), 'the local authorities are not in name order'


def test_aggregates_follow_in_the_declared_order(meta):
    codes = [area['c'] for area in meta['areas'][meta['geoAreas']:]]
    assert codes == AGGREGATE_CODES, (
        'the national and regional series are missing, reordered, or mixed in '
        'among the local authorities')


def test_base_prices_are_one_row_per_type(meta):
    assert len(meta['base']) == len(meta['types'])
    for t, row in enumerate(meta['base']):
        assert len(row) == len(meta['areas']), f'base[{t}] is the wrong length'
        values = np.asarray(row, dtype = np.float64)
        assert np.isfinite(values).all(), f'base[{t}] holds NaN or infinity'
        assert (values >= 0).all(), f'base[{t}] holds a negative price'


def test_cpi_covers_the_month_axis(meta):
    assert len(meta['cpi']) == meta['months']['count'], (
        'the CPI series and the month axis are different lengths, so real '
        'prices would be deflated by the wrong month')
    values = np.asarray(meta['cpi'], dtype = np.float64)
    assert np.isfinite(values).all(), 'the CPI series holds NaN or infinity'
    assert (values > 0).all(), 'the CPI series holds a zero or a negative index'


####################
# prices-N.bin
#
# The matrices are loaded and reshaped by the 'matrices' fixture, which is
# where the file length is checked.


@pytest.mark.parametrize('t', range(len(HOUSING_TYPES)))
def test_each_area_is_indexed_from_its_own_first_observation(t, meta, matrices):
    """Every area's first recorded month has to be exactly the scale.

    This is the whole encoding: the stored values are relative to that first
    observation, and the browser gets back to pounds by multiplying through by
    base[type][area]. An area whose series does not start at 1000 has been
    rebased against the wrong month, and every price and growth figure it shows
    is out by that ratio.
    """
    matrix = matrices[t]
    wrong = []
    for area in range(matrix.shape[0]):
        recorded = np.flatnonzero(matrix[area])
        if len(recorded) and matrix[area, recorded[0]] != meta['scale']:
            wrong.append((meta['areas'][area]['n'], int(matrix[area, recorded[0]])))

    assert not wrong, f'areas not indexed from their first observation: {wrong[:5]}'


@pytest.mark.parametrize('t', range(len(HOUSING_TYPES)))
def test_series_have_no_holes_in_the_middle(t, meta, matrices):
    """A series may start late or stop early, but it should not be interrupted.

    Scotland and Northern Ireland genuinely begin after England and Wales, so a
    leading run of zeros is expected. A gap between two observations is not: it
    breaks the chart into pieces, and growth measured across the gap is
    unavailable without anything on screen explaining why.
    """
    matrix = matrices[t]
    holes = []
    for area in range(matrix.shape[0]):
        recorded = np.flatnonzero(matrix[area])
        if len(recorded) and len(recorded) != recorded[-1] - recorded[0] + 1:
            holes.append(meta['areas'][area]['n'])

    assert not holes, f'{len(holes)} series have interior gaps: {holes[:5]}'


@pytest.mark.parametrize('t', range(len(HOUSING_TYPES)))
def test_no_value_sits_against_the_uint16_ceiling(t, matrices):
    # Step 06 clips to 65535, so a value at the ceiling is a clipped one - a
    # price up more than 65x on the area's first observation, which in practice
    # means the base is wrong rather than the market extraordinary
    assert matrices[t].max() < 65535, 'a value was clipped to the uint16 maximum'


####################
# lads.geojson


def test_boundaries_are_a_feature_collection(lads):
    assert lads['type'] == 'FeatureCollection'
    assert lads['features'], 'lads.geojson has no features'


def test_every_mappable_area_has_exactly_one_boundary(meta, lads):
    """Area index is the join key between the matrix and the map.

    The feature id is what setFeatureState keys off, so a missing feature is an
    area that can never be coloured, and a stray one is a feature addressing a
    row of the matrix that belongs to somebody else.
    """
    ids = [feature['id'] for feature in lads['features']]
    assert len(set(ids)) == len(ids), 'duplicate feature ids'
    assert set(ids) == set(range(meta['geoAreas'])), (
        f'{len(ids)} boundaries for {meta["geoAreas"]} mappable areas - the '
        'geography release and the price data have drifted apart')


def test_feature_id_and_properties_agree(lads):
    for feature in lads['features']:
        assert feature['id'] == feature['properties']['i'], feature['id']


def test_geometries_are_polygons(lads):
    types = {feature['geometry']['type'] for feature in lads['features']}
    assert types <= {'Polygon', 'MultiPolygon'}, types


def test_rings_are_closed_and_long_enough(meta, lads):
    for feature in lads['features']:
        name = meta['areas'][feature['id']]['n']
        for ring in iter_rings(feature['geometry']):
            assert len(ring) >= 4, f'{name} has a ring of {len(ring)} points'
            assert ring[0] == ring[-1], f'{name} has an unclosed ring'


def test_boundaries_are_inside_the_uk(meta, lads):
    west, south, east, north = UK_BBOX
    for feature in lads['features']:
        for lon, lat in iter_points(feature['geometry']):
            assert west <= lon <= east and south <= lat <= north, (
                f'{meta["areas"][feature["id"]]["n"]} has a point at '
                f'({lon}, {lat}) - check the reprojection in step 03')


def test_coordinates_are_rounded(lads):
    for feature in lads['features']:
        for point in iter_points(feature['geometry']):
            for value in point:
                assert round(value, COORD_DP) == value, f'{value} is not rounded'


####################
# places.geojson
#
# Unrelated to the price data and sharing none of its indexing, but the map
# draws it, so its own contract with map-canvas.js is worth holding to.


def test_places_are_a_feature_collection(places):
    assert places['type'] == 'FeatureCollection'
    assert places['features'], 'places.geojson has no features'


def test_place_ranks_are_within_the_zoom_cutoffs(places):
    # map-canvas.js turns 'r' into a zoom cutoff, so a rank it does not know
    # about is a label that never appears at all
    for feature in places['features']:
        rank = feature['properties']['r']
        assert isinstance(rank, int) and 0 <= rank <= MAX_PLACE_RANK, rank


def test_place_sort_keys_are_a_dense_population_order(places):
    """'s' is the collision sort key, so it has to be a total order with no ties.

    Step 07 writes it as the position in population order, which makes it
    0..n-1 in file order. If two labels shared a key, the larger settlement
    would no longer reliably keep its place where both cannot fit.
    """
    keys = [feature['properties']['s'] for feature in places['features']]
    assert keys == list(range(len(keys))), 'the place sort keys are not 0..n-1 in order'


def test_place_names_are_present(places):
    for feature in places['features']:
        assert feature['properties']['n'].strip(), 'a place has no name'


def test_places_are_points_inside_the_uk(places):
    west, south, east, north = UK_BBOX
    for feature in places['features']:
        assert feature['geometry']['type'] == 'Point'
        lon, lat = feature['geometry']['coordinates']
        assert west <= lon <= east and south <= lat <= north, (
            f'{feature["properties"]["n"]} is at ({lon}, {lat})')


def test_no_place_is_labelled_twice(places):
    """Step 07 drops the settlements GeoNames lists twice.

    Two labels at the same spot draw on top of each other, and the collision
    pass cannot help because neither one displaces the other.
    """
    seen = [(feature['properties']['n'],
             round(feature['geometry']['coordinates'][0], 1),
             round(feature['geometry']['coordinates'][1], 1))
            for feature in places['features']]
    duplicates = {key for key in seen if seen.count(key) > 1}
    assert not duplicates, f'duplicate places: {sorted(duplicates)[:5]}'


def test_every_series_without_a_boundary_has_a_tier(meta):
    """main.js groups the dropdown by reading the tier off the ONS code.

    K02 is the UK, a 9 in second place a country, E12 a region, and E10, E11 or
    E13 a county. A series arriving with a code outside that set falls into the
    catch-all group at the bottom of the list, under a heading that tells the
    reader nothing - which is the sort of thing nobody notices until somebody
    asks why 'Greater London Authority' is filed under 'Other series'.
    """
    import re

    def tier(code):
        if code.startswith('K02'):
            return 'uk'
        if re.match(r'^[EWSN]9', code):
            return 'country'
        if code.startswith('E12'):
            return 'region'
        if re.match(r'^E1[013]', code):
            return 'county'
        return None

    homeless = [area['n'] for area in meta['areas'][meta['geoAreas']:]
                if tier(area['c']) is None]
    assert not homeless, f'series with no tier for the dropdown: {homeless}'
