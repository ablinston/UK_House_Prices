exec(open('global.py').read())


####################
# Process the CPI inflation data

# Read in data and remove the first 10 rows of metadata
cpi_data = dt.fread('raw_data/' + config['UK_cpi_filename'])[10:, :]

# Convert the column to a number
cpi_data['CPI INDEX 00: ALL ITEMS 2015=100'] = dt.float64

# Get the needed columns
cpi_data['cpi_index'] = cpi_data[:, dt.f['CPI INDEX 00: ALL ITEMS 2015=100'] / 100]

#  Filter only the monthly data
cpi_data = cpi_data.to_pandas()
cpi_data = cpi_data[cpi_data['Title'].str.len() == 8]    

# Format the dates to be compatible with the HPI data
cpi_data['Date'] = pd.to_datetime(cpi_data['Title'], format = '%Y %b')

# Recalculate index to latest available date
latest_cpi_index = cpi_data[cpi_data['Date'] == cpi_data['Date'].max()]['cpi_index'].iloc[0]
cpi_data['cpi_index'] = cpi_data['cpi_index'] / latest_cpi_index

cpi_data[cpi_data['cpi_index'].notna()][['Date', 'cpi_index']].to_parquet('data/uk_cpi.parquet')
