exec(open('global.py').read())


####################
# Process the land registry data

# Read in the house price index data
uk_hpi_data = dt.fread('raw_data/UK-HPI-full-file.csv')

# Convert the date column to date format
uk_hpi_data[:, dt.update(Date = dt.time.ymd(dt.as_type(dt.str.slice(dt.f.Date, 6, 10), int), 
                                            dt.as_type(dt.str.slice(dt.f.Date, 3, 5), int),
                                            dt.as_type(dt.str.slice(dt.f.Date, 0, 2), int)))]

uk_hpi_data = uk_hpi_data.to_pandas().rename(columns = {'AveragePrice': 'OverallPrice'})

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


