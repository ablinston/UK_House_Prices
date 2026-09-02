exec(open('global.py').read())


####################
# Process the land registry data

# Read in the house price index data
uk_hpi_data = pd.read_csv('raw_data/UK-HPI-full-file.csv')

# Convert the date column to date format
uk_hpi_data['Date'] = pd.to_datetime(uk_hpi_data['Date'], format = '%d/%m/%Y')

uk_hpi_data = uk_hpi_data.rename(columns = {'AveragePrice': 'OverallPrice'})

# Calculate sales volume
uk_hpi_data['SalesVolume'] = uk_hpi_data['OldSalesVolume'] + uk_hpi_data['NewSalesVolume']

uk_hpi_data[['Date',
             'RegionName',
             'AreaCode', 
             'OverallPrice', 
             'DetachedPrice',
             'SemiDetachedPrice', 
             'TerracedPrice', 
             'FlatPrice',
             'SalesVolume']].to_parquet('data/uk_hpi_data.parquet')


