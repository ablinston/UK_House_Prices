exec(open('global.py').read())


################
# Get the UK house price statistics

print('Step 01: Scrape HPI data')

if (os.path.exists('raw_data/UK-HPI-full-file.csv')):
    os.remove('raw_data/UK-HPI-full-file.csv')

# Get the current date
current_date = datetime.now()

# Create an unverified SSL context
ssl_context = ssl._create_unverified_context()

# Loop through the last 5 months to see if data is available. When it is, download and exit
for i in range(5):

    # Get the download link
    link = str(config['UK_house_price_stats_source']).replace("YEAR", str(current_date.year)).replace("MONTH", str(current_date.strftime("%m")))

    try:
        # Open the URL with the unverified context
       with urllib.request.urlopen(link, context=ssl_context) as response:
           # Read the data from the response
           data = response.read()

           # Write the data to a file
           with open('raw_data/UK-HPI-full-file.csv', 'wb') as f:
               f.write(data)
    except Exception:
       # Move to the previous month
       print(f'  no HPI data yet for {current_date:%Y-%m}')
       current_date = current_date.replace(day=1) - timedelta(days=1)
    else:
        print(f'  downloaded HPI data for {current_date:%Y-%m}')
        break
else:
    print('  WARNING: no HPI data found in the last 5 months - '
          'check UK_house_price_stats_source in config.yaml')


