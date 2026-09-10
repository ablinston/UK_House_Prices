# Every import the pipeline needs lives here, so a step can be run on its
# own without carrying an import block of its own - and so the helpers in
# functions/, exec'd at the bottom, can count on them whatever called
# them. download_file() reaches for requests and BeautifulSoup without
# importing either, and used to work only because step 02 happened to
# import them before exec'ing this file.
from bs4 import BeautifulSoup
import csv
from datetime import date, datetime, timedelta
try:
    # Only needed by src/03_geojson_processing.py, which is Windows-only -
    # geopandas pulls in Fiona, which has no Linux ARM64 wheel and so isn't
    # installed in the Docker image used on the Raspberry Pi.
    import geopandas as gp
except ImportError:
    gp = None
import io
import json as j
import numpy as np
import os
import pandas as pd
import pdb
import requests
import ssl
import subprocess
import sys
import urllib.request
from urllib.parse import urljoin
import yaml
import zipfile

# Load the config settings
config = yaml.safe_load(open('config.yaml'))

# Load all the functions in the functions folder
for filename in os.listdir('functions/'):
    if filename.endswith('.py'):
        exec(open('functions/' + filename).read())