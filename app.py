
from shiny import App, render, ui, run_app, reactive
from shinywidgets import output_widget, render_widget

exec(open('global.py').read())

# Read in geo data
uk_geojson = j.load(open('data/uk_lads.geojson', 'r'))
uk_geojson_highres = j.load(open('data/uk_lads_highres.geojson', 'r'))

# Read in the house price index data
uk_hpi_data = pd.read_parquet('data/uk_hpi_data.parquet')
# Reformat the date for later filtering
uk_hpi_data['Date'] = uk_hpi_data['Date'].dt.date

# Define the housing types
housing_types = ['Overall',
                 'Detached',
                 'SemiDetached',
                 'Terraced',
                 'Flat']

# Read in lad list and add the region names
lad_list = pd.read_parquet('data/lad_list.parquet', engine = 'pyarrow')

# Read in the uk cpi data
cpi_data = pd.read_parquet('data/uk_cpi.parquet', engine = 'pyarrow')
cpi_data['Date'] = cpi_data['Date'].dt.date

cpi_index_date = cpi_data['Date'].max()

# Merge onto house data
uk_hpi_data = uk_hpi_data.merge(cpi_data, how = 'left', on = 'Date')

# Get a list of regions to select from for stats
region_list = lad_list.merge(uk_hpi_data[['AreaCode', 'RegionName']].drop_duplicates(),
                             how = 'inner',
                             left_on = 'ID',
                             right_on = 'AreaCode')

region_list.sort_values(by = 'RegionName', inplace = True)
    
app_ui = ui.page_fluid(
    ui.head_content(ui.include_css("app/custom.css")),
    ui.row(
        ui.column(6,
            ui.div(ui.h2('House Price Changes Heatmap'),
                   class_ = "heading_box"),
            ui.div(
                ui.output_text('introduction'),
                class_ = 'main_text'
                ),
            ui.div(
                ui.input_date_range('date_range',
                    'Choose a date range to measure average house price changes between',
                    start = '2005-01-01',
                    end = date.today()),
                # ui.row(
                #     ui.column(
                #         6,
                #         ui.input_slider('start_date_slider',
                #                         label = 'test',
                #                         min = date(2004, 1, 1),
                #                         max = date.today(),
                #                         value = date(2004, 1, 1),
                #                         ticks = True,
                #                         width = '100%')
                #         ),
                #     ui.column(
                #         6,
                #         ui.input_slider('end_date_slider',
                #                         label = 'test',
                #                         min = date(2004, 1, 1),
                #                         max = date.today(),
                #                         value = date.today(),
                #                         ticks = True,
                #                         width = '100%')
                #         )
                #     ),
                ui.row(
                    ui.column(
                        4,
                        ui.input_select('house_type',
                                        'Choose type of housing:',
                                        choices = housing_types,
                                        width = '100%')
                    ),
                    ui.column(
                        4,
                        ui.input_select('map_resolution',
                                        'Map resolution',
                                        choices = ['Low', 'High'],
                                        selected = 'Low',
                                        width = '100%'),
                    ),
                    ui.column(
                        4,
                        ui.input_select('nominal_real',
                                        'Nominal or real prices',
                                        choices = ['Nominal', 'Real'],
                                        selected = 'Real',
                                        width = '100%'),
                    )
                ),
                # ui.input_slider('n', 'N', 0, 100, 20),
                # ui.output_text_verbatim('txt'),
                # ui.input_text('area_id', 'Test click', 'default'),
                class_ = 'padded_col'
            ),
            ui.div(ui.h2('Local Authority statistics'),
                   class_ = 'heading_box'),
            ui.div(
                ui.output_text('la_stats_intro'),
                class_ = 'main_text'
                ),
            ui.div(
                ui.row(
                    ui.column(
                        4,
                        ui.input_select('area_name',
                                        '',
                                        choices = region_list['RegionName'].to_list()),
                        ui.br(),
                        ui.dataframe.output_data_frame('area_stats')
                    ),
                    ui.column(
                        8,
                        output_widget('local_authority_time_series')
                    )
                ),
                # ui.dataframe.output_data_frame('data_head'),
                ui.div(
                    ui.output_text('source'),
                    class_ = 'small_text'
                    ),
                class_ = 'padded_col'
            ),
            class_ = 'left_column'
        ),
        ui.column(6, 
            output_widget('map'),
            style = 'height: 100%',
            class_ = 'right_column'
        ),
        style = 'max-height: 100%' 
    )
)


def server(input, output, session):

    # First define the raw text to appear in the UI
    @output
    @render.text
    def source():
        return f'Real house prices are given in prices as at {cpi_index_date}. \nSources: Land Registry House Price Index, ONS Consumer Price Index (CPI) monthly'
    
    @output
    @render.text
    def introduction():
        return f'This dashboard shows the house price history of the UK and which areas have seen the smallest/largest changes. Simply choose the date range you are interested in and the map and figures below will update to show the changes in average sold price between these dates.'
    
    @output
    @render.text
    def la_stats_intro():
        return f'Choose a Local Authority either from the drop down below or click an area of the map.'
    
    # Process the data based on the selected inputs
    @reactive.Calc
    def filter_data():
        
        # # Debugging
        # input_date_range = (date(2008, 1, 1), date(2022, 6, 8))
        # filter_data = uk_hpi_data[((uk_hpi_data['Date'] >= date(2008, 1, 1)) &
        #                               (uk_hpi_data['Date'] <= date(2022, 6, 8)))]
                
        # First filter the data for the two dates
        filter_data = uk_hpi_data[((uk_hpi_data['Date'] >= input.date_range()[0]) &
                                     (uk_hpi_data['Date'] <= input.date_range()[1]))]
        
        # Adjust for CPI if necessary
        if input.nominal_real() == 'Real':
            for house_type in housing_types:
                filter_data[house_type + 'Price'] = \
                    filter_data[house_type + 'Price'] / filter_data['cpi_index']
        
        return filter_data
    
    @reactive.Calc
    def processed_data():
        
        # # Debugging
        # input_date_range = (date(2008, 1, 1), date(2022, 6, 8))
        # filtered_data = uk_hpi_data[((uk_hpi_data['Date'] >= date(2008, 1, 1)) &
        #                              (uk_hpi_data['Date'] <= date(2022, 6, 8)))]
        # input_house_type = 'All'
        # # Rename to input.date_range() after debug
                
        # First filter the data for the two dates
        filtered_data = filter_data()
        
        # Find the first and last recorded dates
        start_data_date = filtered_data['Date'].min()
        end_data_date = filtered_data['Date'].max()
        
        # Update the UI to reflect the used dates in the data
        ui.update_date_range("date_range", start = start_data_date, end = end_data_date)
                
        # Split the data into the min and max
        start_index_data = filtered_data[filtered_data['Date'] == start_data_date
                                         ]
        
        end_index_data = filtered_data[filtered_data['Date'] == end_data_date
                                         ][['AreaCode'] + [ht + 'Price' for ht in housing_types]]

        # Merge the data together and compute the house price growth
        merged_data = start_index_data.merge(end_index_data,
                                          on = 'AreaCode')
        
        map_data = merged_data[['AreaCode', 'RegionName']]
        
        # Calculate house price inflation
        for metric in housing_types:
            map_data[metric] = 100 * ((
                merged_data[metric + 'Price_y'] / 
                merged_data[metric + 'Price_x']) - 1)
  
        # Compute the column of interest
        if (input.house_type() == 'Overall'):
            map_data['MapValue'] = map_data['Overall']
        else:
            map_data['MapValue'] = map_data[input.house_type()]
        
        return map_data
    
    # def hover_handler(self, *args, **kwargs):
        
    #     self.tooltip.value = 'test'
    #     # label.value =\
    #     #         f'State: {feature["properties"]["LAD23NM"]}'
        

    clicked_area_value = reactive.Value('S12000036')

    # This function is used to update the stats for an area with a map click
    def update_clicked_area_value(**kwargs):

        def callback(feature, *args, **kwargs):
            value = feature['properties']['ID']
            clicked_area_value.set(value)

        return callback

    @reactive.Effect
    def clicked_area():
        # ui.update_text('area_id', value = clicked_area_value())
        ui.update_select(
            'area_name',
            selected = region_list[region_list['ID'] == clicked_area_value()]['RegionName'].iloc[0]
        )
    
    @output
    @render.text
    def txt():
        return f'n*2 is {input.n() * 2}'

    @output
    @render.data_frame
    def area_stats():
        # ## Debug
        # df = map_data[map_data['RegionName'] == 'Sheffield']
        # input_date_range = (date(2008, 1, 1), date(2022, 6, 8))
        # years = (input_date_range[1] - input_date_range[0]).days / 365
        
        # Get data
        df = processed_data()
        # Filter for the region
        df = df[df['RegionName'] == input.area_name()]
        
        df = df.drop(columns = ['MapValue', 'AreaCode', 'RegionName']).round(1).T
        df.reset_index(inplace=True)
        df.columns = ['% Change', 'Total']
        
        # Calculate the change in annualised terms
        years = (input.date_range()[1] - input.date_range()[0]).days / 365
        df['Annualised'] = ((((df['Total'] / 100 + 1) ** (1 / years)) - 1) * 100).round(1)
        
        return render.DataGrid(df)

    # Create time series chart for local authority
    @output
    @render_widget
    def local_authority_time_series():
        ## Debug
        # df = uk_hpi_data[((uk_hpi_data['Date'] >= date(2008, 1, 1)) &
        #                               (uk_hpi_data['Date'] <= date(2022, 6, 8)))]
        # df = df[df['RegionName'] == 'Sheffield']
        
        # Get data and filter for the area
        df = filter_data()
        df = df[df['RegionName'] == input.area_name()]
        
        # Change format of the date column to work with plotly
        df['Date'] = pd.to_datetime(df['Date'])
        
        df_long = df.drop(columns = ['RegionName', 
                                     'AreaCode', 
                                     'cpi_index', 
                                     'SalesVolume']).melt(id_vars = 'Date')
        df_long['variable'] = df_long['variable'].str.replace('Price', '')
        
        # Create chart
        fig = px.line(df_long,
                      x = 'Date', 
                      y = 'value',
                      color = 'variable',
                      line_dash = 'variable',
                      range_y = [0, df_long['value'].max() + 20000],
                      labels = {'value': '£',
                                'Date': '',
                                'variable': 'House Type'},
                      template = "plotly_white",
                      height = 300)
        
        fig.update_layout(title_text = 'Average ' + input.nominal_real() + ' House Price in ' + input.area_name(), 
                          legend = dict(
                              title = None, 
                              orientation = "h", 
                              y = -0.3, 
                              yanchor = "bottom", 
                              x = 0.5, 
                              xanchor = "center"),
                          title_x = 0.5,
                          autosize = True,
                          margin = dict(b = 0, l = 0, r = 0))
        
        return fig
    
    # @output
    # @render.data_frame
    # def data_head():
    #     return render.DataGrid(processed_data().head())
    
    # Create the map of the UK
    @output
    @render_widget
    def map():
        
        with ui.Progress(min = 1, max = 5) as p:

            p.set(message='Rendering in progress', detail='This may take a while...')
            p.set(1)

            # Compute the data for map by merging to avoid missing area codes needed for map
            data_for_map = lad_list.merge(processed_data(),
                                          how = 'left',
                                          left_on = 'ID',
                                          right_on = 'AreaCode')

            map_dictionary = dict(zip(data_for_map['ID'],
                                      data_for_map['MapValue']))
                   
            p.set(2)
            
            # Setup function to select correct geonjson
            def get_map_geojson(selection):
                if selection == 'High':
                    return uk_geojson_highres
                else:
                    return uk_geojson
            
            # Set the colours for the map layer
            # Exclude the top 5 so that extreme values don't affect colours as much
            # min_value = np.min([0, data_for_map['MapValue'].nsmallest(5).max()])
            # max_value = np.max([data_for_map['MapValue'].nlargest(5).min(), 0])
            
            max_value = data_for_map['MapValue'].abs().nlargest(10).min()
            min_value = -max_value
            
            map_colours = LinearColormap(colors = ['#9a0000', '#ffffff', '#085602'], 
                                         index = [min_value, 0, max_value], 
                                         vmin = min_value, 
                                         vmax = max_value)
            
            # Add the coloured layer to the map
            layer = ip.Choropleth(
                geo_data = get_map_geojson(input.map_resolution()),
                choro_data = map_dictionary,
                key_on = 'id',
                colormap = map_colours,
                value_min = min_value,
                value_max = max_value,
                style = {'fillOpacity': 0.6},
                hover_style = {'color': 'white', 'fillOpacity': 0.3}
            )
            
            # Create the map and centred location
            m = ip.Map(center = (55, -4.5),
                       zoom = 6,
                       scroll_wheel_zoom = True)

            p.set(3)

            layer.on_click(update_clicked_area_value())
            # layer.on_hover(hover_handler)

            # Edit layout
            m.layout.height = '950px'

            m.add_layer(layer)

            p.set(4)

            return m

        
        
app = App(app_ui, server, debug = True)

