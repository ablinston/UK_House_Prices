exec(open('global.py').read())

####################
# Export the processed data as compact assets for the static web app
#
# Written to web/data/:
#   prices-N.bin  uint16 price-index matrix [area][month] for housing type N,
#                 0 = missing. One file per type so the browser can load the
#                 selected type first and stream the rest in the background.
#   meta.json     area codes/names, month axis, CPI series, base prices
#   lads.geojson  LAD boundaries, feature id = area index
#
# Prices are stored as an index relative to each area's own first observation
# (x1000, uint16). The map only ever needs ratios between two dates, so the
# base cancels out; absolute prices are recovered in the browser as
# base * index / SCALE. This halves the payload versus float32.

OUT_DIR = 'web/data'
SCALE = 1000          # index units: first observation for an area = 1000
COORD_DP = 4          # ~11 m precision, ample at national zoom

# National and regional series, kept alongside the local authorities so an area
# can be compared with its region and with the UK as a whole. These have no
# boundary on the map: they are selectable from the dropdown only, and are
# appended after the local authorities so that an area's position in the list
# still doubles as its feature id in lads.geojson.
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
                   'E12000009']   # South West

housing_types = ['Overall',
                 'Detached',
                 'SemiDetached',
                 'Terraced',
                 'Flat']

os.makedirs(OUT_DIR, exist_ok = True)


####################
# Load the processed data

uk_hpi_data = pd.read_parquet('data/uk_hpi_data.parquet')
lad_list = pd.read_parquet('data/lad_list.parquet')
cpi_data = pd.read_parquet('data/uk_cpi.parquet')

uk_hpi_data['Date'] = pd.to_datetime(uk_hpi_data['Date'])

# Local authorities: those with both a boundary and price data, ordered by name
lad_rows = uk_hpi_data[uk_hpi_data['AreaCode'].isin(lad_list['ID'])]
lad_areas = (lad_rows[['AreaCode', 'RegionName']]
             .drop_duplicates(subset = 'AreaCode')
             .sort_values('RegionName'))

# Aggregates, kept in the order declared above rather than alphabetically
agg_rows = uk_hpi_data[uk_hpi_data['AreaCode'].isin(AGGREGATE_CODES)]
agg_areas = (agg_rows[['AreaCode', 'RegionName']]
             .drop_duplicates(subset = 'AreaCode')
             .set_index('AreaCode')
             .reindex([c for c in AGGREGATE_CODES if c in set(agg_rows['AreaCode'])])
             .reset_index())

missing_aggregates = [c for c in AGGREGATE_CODES if c not in set(agg_rows['AreaCode'])]
if missing_aggregates:
    print(f'  WARNING: aggregate series not found in the data: {missing_aggregates}')

areas = pd.concat([lad_areas, agg_areas], ignore_index = True)
area_index = {code: i for i, code in enumerate(areas['AreaCode'])}

# Only the local authorities have boundaries, and they come first, so this count
# is also the number of features in lads.geojson
geo_areas = len(lad_areas)

hpi = pd.concat([lad_rows, agg_rows], ignore_index = True)

# The month axis is taken from the local authorities alone. The national series
# reach back to 1968, but carrying that history would near-double every matrix
# for data only a handful of areas have, so aggregates are clipped to the same
# window and compare like with like.
months = pd.date_range(lad_rows['Date'].min(), lad_rows['Date'].max(), freq = 'MS')

print(f'Areas:  {len(areas)} ({geo_areas} local authorities + {len(agg_areas)} aggregates)')
print(f'Months: {len(months)} ({months[0]:%Y-%m} to {months[-1]:%Y-%m})')


####################
# Build the price index matrix

matrix = np.zeros((len(housing_types), len(areas), len(months)), dtype = np.uint16)
base_prices = np.zeros((len(housing_types), len(areas)), dtype = np.float64)

for t, house_type in enumerate(housing_types):

    wide = (hpi.pivot_table(index = 'AreaCode',
                            columns = 'Date',
                            values = house_type + 'Price',
                            aggfunc = 'first')
            .reindex(index = areas['AreaCode'], columns = months))

    values = wide.to_numpy(dtype = np.float64)

    # Locate each area's first observation to use as its base
    valid = np.isfinite(values) & (values > 0)
    has_data = valid.any(axis = 1)
    first = np.argmax(valid, axis = 1)
    base = np.where(has_data, values[np.arange(len(values)), first], np.nan)

    # Index relative to that base, with 0 reserved as the missing marker
    safe_base = np.where(np.isfinite(base), base, 1.0)
    index = np.round(values / safe_base[:, None] * SCALE)
    index = np.clip(index, 1, 65535)
    index = np.where(valid & has_data[:, None], index, 0)

    overflow = int((np.round(values / safe_base[:, None] * SCALE) > 65535).sum())
    if overflow:
        print(f'  WARNING: {overflow} {house_type} values exceeded the uint16 range and were clipped')

    matrix[t] = index.astype(np.uint16)
    base_prices[t] = np.nan_to_num(base)

    print(f'  {house_type:<13} {int(valid.sum()):>7} observations')


####################
# Align the CPI series to the same month axis

cpi = (cpi_data
       .assign(Date = pd.to_datetime(cpi_data['Date']))
       .set_index('Date')['cpi_index']
       .reindex(months)
       .ffill()
       .bfill())

# 05_cpi_processing rebases the index so the latest month is 1.0, which makes
# nominal / cpi_index a price in today's money
cpi_base_date = pd.to_datetime(cpi_data['Date']).max()


####################
# Write one binary per housing type, plus the metadata

for t, house_type in enumerate(housing_types):
    with open(f'{OUT_DIR}/prices-{t}.bin', 'wb') as f:
        f.write(matrix[t].tobytes(order = 'C'))

meta = {
    'generated': datetime.now().strftime('%Y-%m-%d'),
    'scale': SCALE,
    'types': housing_types,
    'months': {'start': f'{months[0]:%Y-%m}', 'count': len(months)},
    'geoAreas': geo_areas,
    'areas': [{'c': c, 'n': n} for c, n in zip(areas['AreaCode'], areas['RegionName'])],
    'cpi': [round(float(v), 6) for v in cpi],
    'cpiBase': f'{cpi_base_date:%B %Y}',
    'base': [[round(float(v), 2) for v in row] for row in base_prices],
}

with open(f'{OUT_DIR}/meta.json', 'w') as f:
    j.dump(meta, f, separators = (',', ':'))


####################
# Slim down the boundaries for the browser

def round_coords(node):
    """Recursively round coordinates and drop points that collapse together."""
    if isinstance(node[0], (int, float)):
        return [round(float(node[0]), COORD_DP), round(float(node[1]), COORD_DP)]

    cleaned = [round_coords(child) for child in node]

    # Only rings (lists of points) can be de-duplicated
    if cleaned and isinstance(cleaned[0][0], (int, float)):
        deduped = [cleaned[0]]
        for point in cleaned[1:]:
            if point != deduped[-1]:
                deduped.append(point)
        # A valid ring needs at least three distinct points plus the closing one
        if len(deduped) < 4:
            return cleaned
        if deduped[0] != deduped[-1]:
            deduped.append(deduped[0])
        return deduped

    return cleaned


with open('data/uk_lads.geojson', 'r') as f:
    boundaries = j.load(f)

features = []
for feature in boundaries['features']:
    code = feature['properties'].get('ID') or feature.get('id')
    if code not in area_index:
        continue
    features.append({
        'type': 'Feature',
        'id': area_index[code],
        'properties': {'i': area_index[code]},
        'geometry': {
            'type': feature['geometry']['type'],
            'coordinates': round_coords(feature['geometry']['coordinates']),
        },
    })

with open(f'{OUT_DIR}/lads.geojson', 'w') as f:
    j.dump({'type': 'FeatureCollection', 'features': features}, f, separators = (',', ':'))

# Aggregates are expected to have no boundary; a local authority without one is
# a genuine mismatch between the price data and the geography release
mapped = {feature['properties']['i'] for feature in features}
missing = [code for code, i in area_index.items() if i < geo_areas and i not in mapped]
if missing:
    print(f'  WARNING: {len(missing)} local authorities have prices but no boundary')


####################
# Report what was written

print('\nWritten to ' + OUT_DIR + ':')
written = [f'prices-{t}.bin' for t in range(len(housing_types))] + ['meta.json', 'lads.geojson']
for name in written:
    size = os.path.getsize(f'{OUT_DIR}/{name}') / 1024
    print(f'  {name:<14} {size:>8.0f} KB')

# Remove the single-file matrix left by earlier versions of this script
if os.path.exists(f'{OUT_DIR}/prices.bin'):
    os.remove(f'{OUT_DIR}/prices.bin')
