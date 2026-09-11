"""Shared fixtures for the data checks.

The suite reads the exported assets in web/data - the actual deploy payload -
rather than re-running any part of the pipeline. That is deliberate: what
matters after a refresh is whether the files about to be pushed are sound, not
whether the code that wrote them still runs.

Where data/*.parquet has been pulled the fixtures below also let a test compare
the export against its own input. It is DVC-tracked and gitignored, so it may
not be there; the tests that need it skip rather than fail.
"""

import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB_DATA = ROOT / 'web' / 'data'
PIPELINE_DATA = ROOT / 'data'

# Housing types in the order step 06 writes them - the position is the N in
# prices-N.bin
HOUSING_TYPES = ['Overall', 'Detached', 'SemiDetached', 'Terraced', 'Flat']

# The series without a boundary, in the order they are appended after the local
# authorities. Kept here as a second copy of the list in step 06, so that a
# reordering of either one is caught rather than followed.
AGGREGATE_CODES = ['K02000001',   # United Kingdom
                   'E92000001',   # England
                   'W92000004',   # Wales
                   'S92000003',   # Scotland
                   'N92000002',   # Northern Ireland
                   'E12000001',   # North East
                   'E12000002',   # North West
                   'E12000003',   # Yorkshire and The Humber
                   'E12000004',   # East Midlands
                   'E12000005',   # West Midlands Region
                   'E12000006',   # East of England
                   'E12000007',   # London
                   'E12000008',   # South East
                   'E12000009',   # South West

                   # Counties, which Land Registry publishes alongside the districts
                   # that make them up - so there is nothing to aggregate here and no
                   # weighting to invent. England only: Scotland, Wales and Northern
                   # Ireland have no tier between the country and the council area.
                   'E13000001',   # Inner London
                   'E13000002',   # Outer London
                   'E11000001',   # Greater Manchester
                   'E11000002',   # Merseyside
                   'E11000003',   # South Yorkshire
                   'E11000007',   # Tyne and Wear
                   'E11000005',   # West Midlands
                   'E11000006',   # West Yorkshire
                   'E10000003',   # Cambridgeshire
                   'E10000007',   # Derbyshire
                   'E10000008',   # Devon
                   'E10000011',   # East Sussex
                   'E10000012',   # Essex
                   'E10000013',   # Gloucestershire
                   'E10000014',   # Hampshire
                   'E10000015',   # Hertfordshire
                   'E10000016',   # Kent
                   'E10000017',   # Lancashire
                   'E10000018',   # Leicestershire
                   'E10000019',   # Lincolnshire
                   'E10000020',   # Norfolk
                   'E10000024',   # Nottinghamshire
                   'E10000025',   # Oxfordshire
                   'E10000028',   # Staffordshire
                   'E10000029',   # Suffolk
                   'E10000030',   # Surrey
                   'E10000031',   # Warwickshire
                   'E10000032',   # West Sussex
                   'E10000034']   # Worcestershire

# Great Britain and Northern Ireland, with room for Shetland, the Isles of
# Scilly and Lowestoft. Anything outside it is a projection that went wrong:
# eastings and northings left unconverted land in the millions, and a lon/lat
# pair the wrong way round puts the country in the Indian Ocean.
UK_BBOX = (-9.0, 49.5, 2.0, 61.5)


def _require(path):
    if not path.exists():
        pytest.skip(f'{path.relative_to(ROOT)} is missing - run the pipeline first')
    return path


####################
# The exported web assets


@pytest.fixture(scope = 'session')
def meta():
    return json.loads(_require(WEB_DATA / 'meta.json').read_text())


@pytest.fixture(scope = 'session')
def matrices(meta):
    """Each type's uint16 [area][month] matrix, as written to prices-N.bin.

    Reshaping here is what turns the row-major layout data.js assumes -
    matrix[area * nMonths + month] - into something asserted rather than
    assumed: a file of the wrong length cannot be reshaped at all.
    """
    n_areas = len(meta['areas'])
    n_months = meta['months']['count']

    loaded = {}
    for t in range(len(meta['types'])):
        raw = _require(WEB_DATA / f'prices-{t}.bin').read_bytes()
        expected = n_areas * n_months * 2
        assert len(raw) == expected, (
            f'prices-{t}.bin is {len(raw)} bytes, expected {expected} '
            f'({n_areas} areas x {n_months} months x 2)')
        loaded[t] = np.frombuffer(raw, dtype = '<u2').reshape(n_areas, n_months)

    return loaded


@pytest.fixture(scope = 'session')
def prices(meta, matrices):
    """Each type's absolute prices in pounds, NaN where nothing was recorded.

    The same arithmetic data.js does: base * index / scale.
    """
    out = {}
    for t, matrix in matrices.items():
        base = np.asarray(meta['base'][t], dtype = np.float64)
        out[t] = np.where(matrix > 0,
                          base[:, None] * matrix / meta['scale'],
                          np.nan)
    return out


@pytest.fixture(scope = 'session')
def months(meta):
    """The month axis as timestamps, expanded from its start and count."""
    return pd.date_range(meta['months']['start'] + '-01',
                         periods = meta['months']['count'],
                         freq = 'MS')


@pytest.fixture(scope = 'session')
def lads():
    return json.loads(_require(WEB_DATA / 'lads.geojson').read_text())


@pytest.fixture(scope = 'session')
def places():
    return json.loads(_require(WEB_DATA / 'places.geojson').read_text(encoding = 'utf-8'))


####################
# The pipeline's own output, where it has been pulled


@pytest.fixture(scope = 'session')
def hpi():
    return pd.read_parquet(_require(PIPELINE_DATA / 'uk_hpi_data.parquet'))


@pytest.fixture(scope = 'session')
def cpi():
    return pd.read_parquet(_require(PIPELINE_DATA / 'uk_cpi.parquet'))


@pytest.fixture(scope = 'session')
def lad_list():
    return pd.read_parquet(_require(PIPELINE_DATA / 'lad_list.parquet'))


####################
# The previous release, for comparison
#
# web/data is committed rather than gitignored, so the last deployed payload is
# already in git history. That is the baseline: there is no snapshot file to
# keep up to date, and no way for one to drift out of step with what was
# actually shipped.


class Release:
    """One committed version of web/data, read straight out of git."""

    def __init__(self, rev, meta):
        self.rev = rev
        self.meta = meta
        self.codes = [area['c'] for area in meta['areas']]
        self.index = {code: i for i, code in enumerate(self.codes)}

    def blob(self, name):
        """One file from web/data as it stood at this revision, or None."""
        return _git_blob(f'web/data/{name}')(self.rev)

    def json(self, name):
        raw = self.blob(name)
        if raw is None:
            pytest.skip(f'{name} did not exist at {self.rev[:8]}')
        return json.loads(raw)

    def matrix(self, t):
        raw = self.blob(f'prices-{t}.bin')
        if raw is None:
            pytest.skip(f'prices-{t}.bin did not exist at {self.rev[:8]}')
        n_areas = len(self.meta['areas'])
        n_months = self.meta['months']['count']
        if len(raw) != n_areas * n_months * 2:
            pytest.skip(f'prices-{t}.bin at {self.rev[:8]} does not match its own meta.json')
        return np.frombuffer(raw, dtype = '<u2').reshape(n_areas, n_months)


def _git_blob(path):
    def read(rev):
        result = subprocess.run(['git', 'show', f'{rev}:{path}'],
                                cwd = ROOT, capture_output = True)
        return result.stdout if result.returncode == 0 else None
    return read


@pytest.fixture(scope = 'session')
def previous():
    """The last committed release whose meta.json differs from the working tree.

    Newest first, and the first one that differs wins: run the checks before
    committing a refresh and that is HEAD, run them afterwards and it is the
    release before, so the comparison says something either way. Every export
    stamps a new 'generated' date, so even a re-run over unchanged source data
    counts as different - which is what keeps 'nothing to compare against'
    meaning genuinely nothing rather than merely identical.
    """
    current = _require(WEB_DATA / 'meta.json').read_bytes()

    revs = subprocess.run(['git', 'rev-list', '-n', '40', 'HEAD', '--', 'web/data/meta.json'],
                          cwd = ROOT, capture_output = True, text = True)
    if revs.returncode != 0:
        pytest.skip('not a git repository, so there is no previous release to compare with')

    read = _git_blob('web/data/meta.json')
    for rev in revs.stdout.split():
        blob = read(rev)
        if blob is not None and blob != current:
            return Release(rev, json.loads(blob))

    pytest.skip('no earlier committed release of web/data/meta.json to compare with')


####################
# Helpers


def iter_rings(geometry):
    """Every linear ring in a Polygon or a MultiPolygon."""
    coordinates = geometry['coordinates']
    if geometry['type'] == 'Polygon':
        return list(coordinates)
    return [ring for polygon in coordinates for ring in polygon]


def iter_points(geometry):
    return [point for ring in iter_rings(geometry) for point in ring]
