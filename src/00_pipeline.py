exec(open('global.py').read())

# Each step prints its own status; a traceback appearing straight after a
# step's banner (with no matching "OK" line) is what failed - the ones before
# it already succeeded.
STEPS = [
    'src/01_scrape_hpi_data.py',
    'src/02_scrape_cpi_data.py',
    # 'src/03_geojson_processing.py',
    'src/04_hpi_processing.py',
    'src/05_cpi_processing.py',
    'src/06_export_web_data.py',
    'src/07_export_places.py',
]

for step in STEPS:
    exec(open(step).read())
    print('  OK')

print('\nPipeline complete.')
