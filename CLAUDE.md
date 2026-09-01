# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Python **Shiny** (`shiny`/`shinywidgets`) web app that visualizes UK house price changes at Local Authority District (LAD) level: a choropleth map (via `ipyleaflet`) alongside per-area time series (via `plotly`), built from the Land Registry UK House Price Index and ONS CPI data.

## Commands

Activate the venv first (Windows): `venv\Scripts\activate.bat`

- **Run the app locally**: `run_app_locally.bat`, or directly `shiny run --reload app.py`
- **Rebuild the data pipeline** (scrape HPI/CPI data, process geojson, produce the parquet/geojson files under `data/`): `python src\00_pipeline.py`
  - This just chains the numbered scripts in `src/` in order (01 scrape HPI → 02 scrape CPI → 03 process geojson → 04 process HPI → 05 process CPI). Run an individual `src/0N_*.py` script directly to redo just one step.
- **Pull data instead of regenerating it**: `dvc pull` (see Data below)
- **Build the Docker image**: `create_docker_image.bat` (builds `ablinston/uk_house_prices`)
- **Deploy to shinyapps.io**: `deploy_app.bat` — stages a minimal bundle (app code + `data/`, `www/`, `functions/`, no `.dvc`/dotfiles/`__pycache__`) into `C:\tmp_deploy` and calls `rsconnect deploy shiny`. Read the comment block at the top of the script before changing `DEPLOY_MODE`/`APP_ID` — shinyapps.io app state (new vs. update) is easy to get wrong and the script documents the recovery steps.

There is no lint/test tooling configured in this repo (no test suite, no linter config beyond the dependency list).

## Architecture

**Global load pattern**: Nothing here uses normal Python imports between the app's own modules. `app.py` and `src/00_pipeline.py` both start with `exec(open('global.py').read())`, and `global.py` itself does `exec()` on every `.py` file in `functions/`. This means:
- Shared imports/config/helpers live in `global.py` and `functions/*.py` and become available implicitly wherever `global.py` is exec'd — there are no explicit imports to trace.
- `config.yaml` (source URLs and filenames for HPI/geojson/CPI data) is loaded once in `global.py` as the `config` dict.
- When adding a new shared helper, drop a new file in `functions/` — it's picked up automatically, no registration needed.

**Data pipeline** (`src/`, numbered to indicate execution order): scrapes HPI data from Land Registry and CPI data from ONS, reprojects the LAD geojson boundaries (EPSG:27700 → EPSG:4326, LAD code column is auto-detected per year, e.g. `LAD23CD`/`LAD25CD`), and writes processed output as parquet/geojson into `data/`. `raw_data/` holds the untouched downloads.

**Data storage via DVC**: `data/` and `raw_data/` are git-ignored (see their `.gitignore`) — only `.dvc` pointer files are committed. Actual data must be materialized with `dvc pull`, or regenerated via `src/00_pipeline.py`. `deploy_app.bat` explicitly checks for the materialized parquet/geojson files before deploying and fails fast with instructions if they're missing — rsconnect needs real files, not `.dvc` stubs.

**App (`app.py`)**: a single-file Shiny app.
- UI: date-range picker, housing-type selector (Overall/Detached/SemiDetached/Terraced/Flat), map resolution toggle (Low/High — swaps between `uk_lads.geojson` and `uk_lads_highres.geojson`), nominal/real toggle (real prices are CPI-deflated), a choropleth map, a Local Authority selector with a stats table, and a per-area time series chart.
- Server logic is reactive (`@reactive.Calc`/`@reactive.Effect`): `filter_data()` filters the HPI data to the selected date range and applies CPI adjustment when "Real" is selected; `processed_data()` computes % house price change between the range's start/end dates per LAD, feeding the map. Map clicks and the area dropdown are kept in sync via a shared `reactive.Value` (`clicked_area_value`).
- Static assets (CSS) live in `www/`.

## Deployment

Two independent deployment paths exist and are kept in sync manually: `Dockerfile` (Amazon Linux, builds Python 3.9.13 from source, runs via `uvicorn app:app`) and shinyapps.io via `rsconnect-python` (`deploy_app.bat`, config in `rsconnect-python/UK_House_Prices.json`).
