# GAIA — Earth System Trend Detective

GAIA is a scientific web application in planning that explores how precipitation changes across regions, months, and seasons. It brings together a regional map, time series, and statistical evidence to help people investigate changes in rainfall.

**Research question:** Where and when is precipitation changing, at what rate, and with what statistical evidence?

## Purpose

Annual rainfall totals can hide changes within individual months or seasons. Regional averages can also hide differences between locations. GAIA aims to make those patterns easier to examine and to show the observations and uncertainty behind each estimated trend.

## Planned experience

1. Choose a time period and a month, season, or full year.
2. Explore a map showing the estimated precipitation trend for each region.
3. Select a region to inspect its rainfall history, rate of change in millimeters per decade, uncertainty, and statistical evidence.
4. Examine the second region under the same settings and use annual totals to put seasonal changes in context.

Results will include data provenance and distinguish insufficient data from an estimated trend with inconclusive evidence.

## MVP scope

- Two predefined regions, selected after validating data coverage.
- A fixed, versioned monthly precipitation dataset bundled with the application.
- Monthly, seasonal, and annual analysis over a selected time period.
- A regional map and time series with trend estimates and supporting statistical evidence.
- Local execution and access without accounts. The installed application must work without an external network connection.

The data source and regions still need validation. A 3D globe, global coverage, file uploads, and user-drawn regions are outside the MVP scope.

## Current status

GAIA is validating its scope and data. The features above describe the planned MVP; a runnable application is not available yet.
