import subprocess
import sys

exec(open('global.py').read())


# Create a function to update the data and do checks:
# 1. The new data is more recent than the last date in the existing data
# 2. Pytests do not contain failures
def run_pipeline(cpi_date, hpi_date):

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
        exec(open(step).read(), globals())
        print('  OK')

    print('\nPipeline complete.')

    # Check the new dates
    new_cpi_date = pd.read_parquet('data/uk_cpi.parquet').tail(1)['Date'].iloc[0]
    new_hpi_date = pd.read_parquet('data/uk_hpi_data.parquet').tail(1)['Date'].iloc[0]

    if (new_cpi_date > cpi_date) or (new_hpi_date > hpi_date):
        print('New data detected, running tests...')

        # Run the unit tests and check the return code. If all tests pass, return True; otherwise, return False.
        if subprocess.run([sys.executable, '-m', 'pytest']).returncode == 0:
            print('All tests passed, pipeline run successful.')
            return True
        else:
            print('Tests failed, pipeline run unsuccessful.')
            return False
    else:
        print('No new data detected, skipping tests.')
        return False


####################################################################
## Run the pipline
####################################################################

# First get the latest dates from the current CPI and HPI data
last_cpi_date = pd.read_parquet('data/uk_cpi.parquet').tail(1)['Date'].iloc[0]
last_hpi_date = pd.read_parquet('data/uk_hpi_data.parquet').tail(1)['Date'].iloc[0]

result = run_pipeline(last_cpi_date, last_hpi_date)

# Exit and return a 1 if failed so that bash knows the repo should not be commited
sys.exit(0 if result else 1)