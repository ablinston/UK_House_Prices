import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

exec(open('global.py').read())

###############
# Get the UK CPI data manually

if (os.path.exists('raw_data/' + config['UK_cpi_filename'])):
    os.remove('raw_data/' + config['UK_cpi_filename'])

# Call the function to download the CSV file
save_path = 'raw_data/' + config['UK_cpi_filename']

# Call the function to download the CSV file
download_file(config['UK_cpi_source'], 
              save_path)


