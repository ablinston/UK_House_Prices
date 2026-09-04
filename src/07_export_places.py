import csv
import io
import urllib.request
import zipfile

exec(open('global.py').read())

####################
# Export city and town labels for the map's place layer
#
# The map has no basemap tiles (deliberately - see CLAUDE.md), so the only
# geographic context it carries is the shape of the local authority polygons
# themselves. That gives the coastline for free but leaves the map unlabelled:
# without a few place names it is hard to tell Manchester from Leeds.
#
# This writes web/data/places.geojson - populated places from the GeoNames GB
# gazetteer, each tagged with a rank so the browser can reveal more of them as
# the user zooms in. Labels are drawn over the choropleth, not under it, so the
# price colours stay true; the halo in map.js is what keeps them readable.
#
# GeoNames is CC BY 4.0, which is why index.html credits it in the footer.

OUT_PATH = 'web/data/places.geojson'
RAW_PATH = 'raw_data/GB.zip'
COORD_DP = 4          # matches the boundary precision in step 06

# Seats of administrative divisions plus ordinary populated places. The codes
# left out are the ones that would only add noise: PPLX (a section of a town,
# so it duplicates its parent), PPLL (a locality with no real centre), and the
# historical PPLQ/PPLW/PPLH entries for places that no longer exist.
PLACE_CODES = {'PPLC',    # national capital
               'PPLA',    # seat of a first-order division
               'PPLA2',   # seat of a second-order division
               'PPLA3',   # seat of a third-order division
               'PPLA4',   # seat of a fourth-order division
               'PPL'}     # populated place

# Population thresholds for each rank, largest first. Rank is the only thing
# the browser needs: map.js turns it into a zoom cutoff, so rank 0 shows at
# national zoom and rank 4 only once the user is well into a region.
RANK_THRESHOLDS = [300000,   # 0 - the biggest cities, visible UK-wide
                   150000,   # 1
                   70000,    # 2
                   30000,    # 3
                   15000]    # 4 - towns, once zoomed in

# GeoNames lists the London boroughs as places in their own right, several of
# them larger than Nottingham, so on population alone Islington and Westminster
# would elbow their way onto a map of the whole country. Held back to this rank
# they appear only once the view is around London - which is where they earn
# their place, since the local authorities there are the boroughs themselves.
LONDON_ADMIN2 = 'GLA'
LONDON_BOROUGH_MIN_RANK = 3

# GeoNames' tab-separated export has no header row
NAME = 1
LATITUDE = 4
LONGITUDE = 5
FEATURE_CLASS = 6
FEATURE_CODE = 7
ADMIN2 = 11
POPULATION = 14

os.makedirs('raw_data', exist_ok = True)
os.makedirs('web/data', exist_ok = True)


####################
# Fetch the gazetteer

print(f"Downloading {config['UK_places_source']}")

ssl_context = ssl._create_unverified_context()
with urllib.request.urlopen(config['UK_places_source'], context = ssl_context) as response:
    with open(RAW_PATH, 'wb') as f:
        f.write(response.read())


####################
# Filter down to the places worth labelling

with zipfile.ZipFile(RAW_PATH) as archive:
    text = archive.read('GB.txt').decode('utf-8')

# QUOTE_NONE because GeoNames does not quote its fields, and some place names
# legitimately contain a double quote
rows = csv.reader(io.StringIO(text), delimiter = '\t', quoting = csv.QUOTE_NONE)

places = []
for row in rows:
    if row[FEATURE_CLASS] != 'P' or row[FEATURE_CODE] not in PLACE_CODES:
        continue

    population = int(row[POPULATION] or 0)
    if population < RANK_THRESHOLDS[-1]:
        continue

    places.append({
        'name': row[NAME].strip(),
        'lon': round(float(row[LONGITUDE]), COORD_DP),
        'lat': round(float(row[LATITUDE]), COORD_DP),
        'population': population,
        # PPLC is London itself, which keeps its rank; everything else inside
        # Greater London is a borough
        'borough': row[ADMIN2] == LONDON_ADMIN2 and row[FEATURE_CODE] != 'PPLC',
    })

places.sort(key = lambda place: -place['population'])

# GeoNames sometimes carries the same settlement twice, once as an ordinary
# place and once as an administrative seat. Keeping the more populous of the
# two avoids a label drawn on top of itself; places that merely share a name
# (there are several Newports) sit far enough apart to survive this.
seen = set()
deduped = []
for place in places:
    key = (place['name'], round(place['lon'], 1), round(place['lat'], 1))
    if key in seen:
        continue
    seen.add(key)
    deduped.append(place)

duplicates = len(places) - len(deduped)
if duplicates:
    print(f'  {duplicates} duplicate entries dropped')

places = deduped


####################
# Write the GeoJSON

def rank_of(place):
    rank = len(RANK_THRESHOLDS) - 1
    for candidate, threshold in enumerate(RANK_THRESHOLDS):
        if place['population'] >= threshold:
            rank = candidate
            break

    if place['borough']:
        return max(rank, LONDON_BOROUGH_MIN_RANK)
    return rank


# 'r' drives the zoom at which a label becomes eligible; 's' is its position in
# population order, which map.js uses as the collision sort key so that where
# two labels cannot both fit it is the larger settlement that keeps its place.
# Without it MapLibre falls back to screen position and drops cities such as
# Edinburgh in favour of whichever neighbour happens to sit higher up.
features = [{
    'type': 'Feature',
    'properties': {'n': place['name'], 'r': rank_of(place), 's': s},
    'geometry': {'type': 'Point', 'coordinates': [place['lon'], place['lat']]},
} for s, place in enumerate(places)]

with open(OUT_PATH, 'w', encoding = 'utf-8') as f:
    j.dump({'type': 'FeatureCollection', 'features': features}, f,
           separators = (',', ':'), ensure_ascii = False)


####################
# Report what was written

boroughs = sum(1 for place in places if place['borough'])

print(f'\nPlaces: {len(features)}  ({boroughs} London boroughs held back to rank '
      f'{LONDON_BOROUGH_MIN_RANK})')
for rank, threshold in enumerate(RANK_THRESHOLDS):
    count = sum(1 for feature in features if feature['properties']['r'] == rank)
    print(f'  rank {rank}  from pop {threshold:>6}  {count:>4} places')

# Only the U+0000-U+00FF glyph range is committed under web/vendor/fonts/glyphs,
# because every UK place name above the population cut-off happens to be plain
# ASCII. If a later GeoNames refresh introduces an accented name it would render
# as blank boxes, so flag it here: the fix is to add the next range (256-511.pbf)
# from the OpenMapTiles font release alongside the one already there.
outside = sorted({character
                  for feature in features
                  for character in feature['properties']['n']
                  if ord(character) > 0x00FF})
if outside:
    print(f'  WARNING: characters with no committed glyph range: {outside}')
    print('           add web/vendor/fonts/glyphs/NotoSans-Regular/256-511.pbf')

print(f'\n{OUT_PATH}  {os.path.getsize(OUT_PATH) / 1024:.0f} KB')
