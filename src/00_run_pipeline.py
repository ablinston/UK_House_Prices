import subprocess
import sys

exec(open('global.py').read())


####################
# Run the pipeline in stages, with a gate between each
#
# The order matters for more than tidiness. Scraping and processing are cheap;
# exporting is not, and step 08 alone writes three megabytes across forty-three
# pages. Running all of that before asking whether the download even contained a
# new month meant most weeks rebuilt the entire payload, byte for byte, to
# produce a diff of nothing - and any week the data was wrong, the pipeline
# cheerfully wrote out a full set of pages from it before the tests said so.
#
# So each stage now has to earn the next one:
#
#   01, 02, 04, 05   scrape and process           always
#   -> is there a new month at all?               stop here most weeks
#   06, 07           export web/data              only if there is
#   -> do the data checks pass?                   stop if the export is wrong
#   08               export the pages             only if they do
#   -> do the page checks pass?
#
# The data checks cannot run any earlier than this: every one of them reads
# web/data, which is step 06's own output, so there is nothing for them to look
# at until it has run. What can be held back is step 08, and that is the
# expensive half.

STEPS_PROCESS = ['src/01_scrape_hpi_data.py',
                 'src/02_scrape_cpi_data.py',
                 # 'src/03_geojson_processing.py',   Windows only
                 'src/04_hpi_processing.py',
                 'src/05_cpi_processing.py']

STEPS_EXPORT = ['src/06_export_web_data.py',
                'src/07_export_places.py']

STEPS_PAGES = ['src/08_export_pages.py']

# Split so a failing export stops before the pages are built from it. The page
# module is left to the end because it has nothing to read until step 08 runs.
DATA_TESTS = ['tests/test_format.py',
              'tests/test_consistency.py',
              'tests/test_plausibility.py',
              'tests/test_regression.py']

PAGE_TESTS = ['tests/test_pages.py']


def run_steps(steps):
    # Each step prints its own status; a traceback appearing straight after a
    # step's banner (with no matching "OK" line) is what failed - the ones before
    # it already succeeded.
    for step in steps:
        exec(open(step).read(), globals())
        print('  OK')


def run_tests(paths, label):
    print(f'\nChecking {label}...')
    passed = subprocess.run([sys.executable, '-m', 'pytest', *paths]).returncode == 0
    if not passed:
        print(f'  {label} failed - stopping before anything further is written')
    return passed


def run_pipeline(cpi_date, hpi_date):

    run_steps(STEPS_PROCESS)

    # Nothing downstream is worth doing without a new month. Land Registry
    # publishes once a month and the Pi looks weekly, so three runs in four
    # reach here and stop, which is the point.
    new_cpi_date = pd.read_parquet('data/uk_cpi.parquet').tail(1)['Date'].iloc[0]
    new_hpi_date = pd.read_parquet('data/uk_hpi_data.parquet').tail(1)['Date'].iloc[0]

    if not ((new_cpi_date > cpi_date) or (new_hpi_date > hpi_date)):
        print('\nNo new data detected, nothing exported.')
        return False

    print(f'\nNew data detected (HPI to {new_hpi_date:%Y-%m}, '
          f'CPI to {new_cpi_date:%Y-%m}), exporting.')

    run_steps(STEPS_EXPORT)
    if not run_tests(DATA_TESTS, 'the exported data'):
        return False

    run_steps(STEPS_PAGES)
    if not run_tests(PAGE_TESTS, 'the generated pages'):
        return False

    print('\nPipeline complete, all checks passed.')
    return True


####################################################################
## Run the pipline
####################################################################

# First get the latest dates from the current CPI and HPI data
last_cpi_date = pd.read_parquet('data/uk_cpi.parquet').tail(1)['Date'].iloc[0]
last_hpi_date = pd.read_parquet('data/uk_hpi_data.parquet').tail(1)['Date'].iloc[0]

result = run_pipeline(last_cpi_date, last_hpi_date)

# Exit and return a 1 if failed so that bash knows the repo should not be commited
sys.exit(0 if result else 1)
