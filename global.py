from datetime import date, datetime, timedelta
try:
    # Only needed by src/03_geojson_processing.py, which is Windows-only -
    # geopandas pulls in Fiona, which has no Linux ARM64 wheel and so isn't
    # installed in the Docker image used on the Raspberry Pi.
    import geopandas as gp
except ImportError:
    gp = None
import json as j
import numpy as np
import os
import pandas as pd
import ssl
import yaml

# Load the config settings
config = yaml.safe_load(open('config.yaml'))

# Load all the functions in the functions folder
for filename in os.listdir('functions/'):
    if filename.endswith('.py'):
        exec(open('functions/' + filename).read())