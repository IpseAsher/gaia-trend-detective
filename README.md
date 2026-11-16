# GAIA — Earth System Trend Detective

GAIA is a local scientific web application for analyzing precipitation trends in Ciudad de México and Estado de México. It examines monthly, seasonal, and annual rainfall from 2001 to 2024 and reports the rate of change, uncertainty, and statistical evidence behind each result.

**Research question:** Where and when is precipitation changing, at what rate, and with what statistical evidence?

## Purpose

Annual rainfall totals can hide changes within individual months or seasons. Regional averages can also hide differences between locations. GAIA lets people compare those periods and regions using the observations and uncertainty behind each estimated trend.

## What you can do

1. Select one or both regions and a period within 2001–2024.
2. Analyze an individual month, a season (DJF, MAM, JJA, or SON), or a full calendar year.
3. Inspect the yearly precipitation series, Theil–Sen trend in millimeters per decade, Sen 95% confidence interval, and two-sided Mann–Kendall p-value.
4. Compare regions under the same settings and use the separately evaluated annual totals to put monthly or seasonal results in context.

Results include data provenance and distinguish statistically significant trends, inconclusive evidence, and insufficient data. Analyses require at least 20 valid years and 80% coverage of the requested period. Missing observations remain gaps rather than being replaced with zero.

## MVP scope

- Two predefined regions: Ciudad de México and Estado de México.
- A fixed, versioned monthly precipitation dataset bundled with the application.
- Monthly, seasonal, and annual analysis over a selected time period.
- Trend estimates, confidence intervals, statistical evidence, and source provenance.
- Local execution and access without accounts, using local data without external network requests.

The validated dataset uses NASA GES DISC IMERG V07B precipitation and INEGI Marco Geoestadístico 2024 boundaries. A 3D globe, global coverage, file uploads, and user-drawn regions are outside the MVP scope.

## Current status

The dataset and regional analysis API are implemented and verified against independent reference calculations. Analyses are available through the interactive API documentation linked below.

The web interface currently displays service and dataset availability. Interactive regional maps and time-series charts are the next development phase.

## Running GAIA locally

### Requirements

- Python 3.11 or later.
- Node.js 22.22.0 or later and pnpm 10.24.0.
- For scientific analyses, the prepared `data/gaia.sqlite` and its matching `data/manifest.json`. Without these files, the services can start, but the API reports that the dataset is unavailable.

Run the following commands from the project root.

### Install dependencies

Install the frontend dependencies:

```sh
pnpm --dir frontend install --frozen-lockfile
```

Set up the backend on Windows (PowerShell):

```powershell
python -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -e ./backend
```

On macOS or Linux:

```sh
python3 -m venv backend/.venv
./backend/.venv/bin/python -m pip install -e ./backend
```

### Start the services

In one terminal, start the backend on Windows:

```powershell
.\backend\.venv\Scripts\python.exe -m uvicorn gaia.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

On macOS or Linux:

```sh
./backend/.venv/bin/python -m uvicorn gaia.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

In a second terminal, start the frontend:

```sh
pnpm --dir frontend dev
```

Open [GAIA](http://127.0.0.1:5173) to view the current service status. To run an analysis, open the [interactive API documentation](http://127.0.0.1:8000/docs), expand `GET /api/v1/analyses`, and select **Try it out**. Use region ID `09` for Ciudad de México, `15` for Estado de México, or both. Set the period within 2001–2024 and choose `annual`, `month:01` through `month:12`, or `season:DJF`, `season:MAM`, `season:JJA`, or `season:SON`.

Keep both terminals running while using GAIA. Stop each service with `Ctrl+C` in its terminal.
