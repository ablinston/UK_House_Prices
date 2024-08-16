from branca.colormap import LinearColormap
import datatable as dt
from datetime import date, datetime, timedelta
import geopandas as gp
import ipyleaflet as ip
import json as j
import numpy as np
import os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import ssl
import yaml

# Load the config settings
config = yaml.safe_load(open('config.yaml'))

# Load all the functions in the functions folder
for filename in os.listdir('functions/'):
    if filename.endswith('.py'):
        exec(open('functions/' + filename).read())