exec(open('global.py').read())

exec(open('src/01_scrape_hpi_data.py').read())
exec(open('src/02_scrape_cpi_data.py').read())
exec(open('src/03_geojson_processing.py').read())
exec(open('src/04_hpi_processing.py').read())
exec(open('src/05_cpi_processing.py').read())
