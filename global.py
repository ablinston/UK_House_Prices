import datatable as dt
from datetime import date, datetime, timedelta
import geopandas as gp
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