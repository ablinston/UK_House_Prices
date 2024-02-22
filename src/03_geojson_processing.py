exec(open('global.py').read())

####################
# Process the geojson data

# Read it in with geopandas
gb_geojson = gp.read_file('raw_data/' + config['UK_geojson_filename'])
gb_geojson_highres = gp.read_file('raw_data/' + config['UK_geojson_highres_filename'])

for geojson in [gb_geojson, gb_geojson_highres]:

    # Convert the coordinates from a projected coordinate system to longitude and latitude
    epsg_code = 27700              # should be referenced in the shapefile
    geojson.crs = {'init': 'epsg:{}'.format(epsg_code)}
    gb_geojson_reprojected = geojson.to_crs({'init': 'epsg:4326'})
    
    # Set the id's of the area's to be the LAD codes and keep a list of codes
    gb_geojson_reprojected['ID'] = gb_geojson_reprojected['LAD23CD']
    
    # Convert the final object to a dictionary
    gb_geojson_final = j.loads(gb_geojson_reprojected.to_json())
    
    # Recode the id's as the LAD code
    for item in gb_geojson_final['features']:
        item['id'] = item['properties']['LAD23CD']
    
    # Save the output for the model
    if geojson.equals(gb_geojson):
        with open('data/uk_lads.geojson', 'w') as f:
            f.write(j.dumps(gb_geojson_final))
    else:
        with open('data/uk_lads_highres.geojson', 'w') as f:
            f.write(j.dumps(gb_geojson_final))
            
# Save a list of LADs needed for the map
gb_geojson_reprojected[['ID']].to_parquet('data/lad_list.parquet')



