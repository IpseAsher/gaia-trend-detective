"""Offline IMERG V07B reader and validated polygon-area precipitation estimator.

Extracted without numerical changes from the completed regional validation.
This module is not imported by the application's runtime.
"""

import calendar
import hashlib
import re
from datetime import datetime, timedelta, timezone

import h5py
import numpy as np

FILL = float(np.float32(-9999.9))


def required_months():
    return [(2000, 12)] + [(y, m) for y in range(2001, 2025) for m in range(1, 13)]


def regional_month(rates, areas, year, month, fill=FILL, qi=None, qi_fill=FILL):
    """Mask native fill first, then convert valid rates and weight actual areas."""
    rates, areas = np.asarray(rates, dtype=np.float64), np.asarray(areas, dtype=np.float64)
    if rates.shape != areas.shape or not np.all(np.isfinite(areas)) or np.any(areas <= 0):
        raise ValueError("Inconsistent or invalid area weights")
    valid = np.isfinite(rates) & (rates != fill) & (rates >= 0) & (rates <= 1000)
    total_area, valid_area = float(areas.sum()), float(areas[valid].sum())
    mm = None
    if valid_area > 0:
        accumulations = rates[valid] * (24 * calendar.monthrange(year, month)[1])
        mm = float(np.dot(accumulations, areas[valid]) / valid_area)
    result = {
        "potential_cells": len(rates), "valid_cells": int(valid.sum()),
        "valid_area_fraction": valid_area / total_area,
        "mean_mm_over_valid_area": mm,
        "qi_valid_area_fraction": None, "qi_area_weighted_mean": None,
        "qi_below_2_area_fraction_of_region": None,
        "qi_below_10_area_fraction_of_region": None,
    }
    if qi is not None:
        qi = np.asarray(qi, dtype=np.float64)
        if qi.shape != rates.shape:
            raise ValueError("QI and precipitation shapes differ")
        qvalid = valid & np.isfinite(qi) & (qi != qi_fill) & (qi >= 0) & (qi <= 3000)
        qarea = float(areas[qvalid].sum())
        result["qi_valid_area_fraction"] = qarea / total_area
        if qarea:
            result["qi_area_weighted_mean"] = float(np.dot(qi[qvalid], areas[qvalid]) / qarea)
        result["qi_below_2_area_fraction_of_region"] = float(areas[qvalid & (qi < 2)].sum()) / total_area
        result["qi_below_10_area_fraction_of_region"] = float(areas[qvalid & (qi < 10)].sum()) / total_area
    return result


def accepted_month(result, threshold):
    # Require every cell for the 100% case; numeric tolerance only for other cutoffs.
    if result.get("status") != "observed" or result.get("mean_mm_over_valid_area") is None:
        return False
    if threshold == 1:
        return result["valid_cells"] == result["potential_cells"]
    return result["valid_area_fraction"] + 1e-12 >= threshold


def attribute(value, hdf=None):
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, np.ndarray):
        return attribute(value.tolist(), hdf)
    if isinstance(value, np.generic):
        return attribute(value.item(), hdf)
    if isinstance(value, (list, tuple)):
        return [attribute(v, hdf) for v in value]
    if isinstance(value, h5py.Reference):
        if hdf is None:
            raise ValueError("A file is needed to resolve HDF5 object references")
        return hdf[value].name if value else None
    return value


def text_attribute(value):
    value = attribute(value)
    while isinstance(value, list) and len(value) == 1:
        value = value[0]
    if not isinstance(value, str):
        raise ValueError("Expected textual HDF5 attribute")
    return value.strip()


def metadata_fields(value):
    return {key.strip(): item.strip() for line in text_attribute(value).splitlines()
            if "=" in line for key, item in [line.rstrip(";").split("=", 1)]}


def verify_native_grid(hdf):
    arrays = {name: np.asarray(hdf[f"Grid/{name}"], dtype=np.float64)
              for name in ("lon", "lat", "lon_bnds", "lat_bnds")}
    expected = {
        "lon": -180 + (np.arange(3600) + 0.5) / 10,
        "lat": -90 + (np.arange(1800) + 0.5) / 10,
        "lon_bnds": np.column_stack((-180 + np.arange(3600) / 10, -180 + (np.arange(3600) + 1) / 10)),
        "lat_bnds": np.column_stack((-90 + np.arange(1800) / 10, -90 + (np.arange(1800) + 1) / 10)),
    }
    tolerance = 2e-5  # degrees; accommodates float32 encoding, far below a 0.1° cell.
    errors = {}
    for name, values in arrays.items():
        if values.shape != expected[name].shape or not np.all(np.isfinite(values)):
            raise ValueError(f"Invalid native coordinate/bounds array: {name}")
        errors[name] = float(np.max(np.abs(values - expected[name])))
        if not np.allclose(values, expected[name], atol=tolerance, rtol=0):
            raise ValueError(f"Grid does not match the existing spatial weights: {name}")
    for name, units in (("lon", "degrees_east"), ("lat", "degrees_north")):
        if text_attribute(hdf[f"Grid/{name}"].attrs["units"]) != units:
            raise ValueError(f"Unexpected coordinate units: {name}")
        if not np.all(np.diff(arrays[name]) > 0):
            raise ValueError(f"Unordered grid coordinate: {name}")
    grid_header = metadata_fields(hdf["Grid"].attrs["GridHeader"])
    expected_header = {"Registration": "CENTER", "Origin": "SOUTHWEST"}
    if any(grid_header.get(key) != value for key, value in expected_header.items()):
        raise ValueError("Unexpected grid registration/origin")
    for key, value in {"LatitudeResolution": .1, "LongitudeResolution": .1,
                       "NorthBoundingCoordinate": 90, "SouthBoundingCoordinate": -90,
                       "EastBoundingCoordinate": 180, "WestBoundingCoordinate": -180}.items():
        if float(grid_header.get(key, "nan")) != value:
            raise ValueError(f"Unexpected GridHeader field: {key}")
    return {"coordinate_bounds_max_abs_error_degrees": errors,
            "coordinate_tolerance_degrees": tolerance,
            "all_global_centers_and_bounds_match_nominal_grid": True,
            "grid_header": grid_header}


def inspect_original(path, expected_filename=None):
    original_name = expected_filename or path.name
    with path.open("rb") as stream:
        if stream.read(8) != b"\x89HDF\r\n\x1a\n":
            raise ValueError("Input is not an HDF5 binary; an HTML login page is not data")
    with h5py.File(path, "r") as hdf:
        dataset = hdf["Grid/precipitation"]
        attrs = {key: attribute(value, hdf) for key, value in dataset.attrs.items()}
        if text_attribute(dataset.attrs.get("units", "")) != "mm/hr":
            raise ValueError("Unexpected precipitation units")
        if "_FillValue" not in attrs:
            raise ValueError("Missing original _FillValue attribute")
        fill = float(np.asarray(dataset.attrs["_FillValue"]).reshape(-1)[0])
        if fill != FILL or dataset.dtype != np.dtype("float32"):
            raise ValueError("Unexpected precipitation dtype/fill")
        if float(np.asarray(dataset.attrs.get("scale_factor", 1)).reshape(-1)[0]) != 1 or float(np.asarray(dataset.attrs.get("add_offset", 0)).reshape(-1)[0]) != 0:
            raise ValueError("Packing requires explicit review; do not silently apply native-rate conversion")
        lon, lat = np.asarray(hdf["Grid/lon"]), np.asarray(hdf["Grid/lat"])
        if dataset.shape != (1, len(lon), len(lat)):
            raise ValueError("Unverified array order; expected time/lon/lat")
        if text_attribute(dataset.attrs["DimensionNames"]) != "time,lon,lat":
            raise ValueError("Unexpected precipitation dimension names")
        scale_paths = [[scale.name for scale in dim.values()] for dim in dataset.dims]
        if scale_paths != [["/Grid/time"], ["/Grid/lon"], ["/Grid/lat"]]:
            raise ValueError("Unexpected attached dimension scales")
        grid_evidence = verify_native_grid(hdf)
        header = metadata_fields(hdf.attrs["FileHeader"])
        if any(header.get(key) != value for key, value in {
            "FileName": original_name, "ProductVersion": "V07B", "AlgorithmID": "3IMERGM",
            "DOI": "10.5067/GPM/IMERG/3B-MONTH/07", "TimeInterval": "MONTH",
            "EmptyGranule": "NOT_EMPTY"}.items()):
            raise ValueError("Original FileHeader does not identify the expected nonempty monthly V07B product")
        match = re.search(r"\.(\d{4})(\d{2})01-S000000-E235959\.\d{2}\.V07B\.HDF5$", original_name)
        if not match:
            raise ValueError("Unexpected V07B original filename")
        year, month = map(int, match.groups())
        time_bounds = hdf["Grid/time_bnds"]
        documented_units = "seconds since 1980-01-06 00:00:00 UTC"
        if text_attribute(time_bounds.attrs.get("units", hdf["Grid/time"].attrs.get("units", ""))) != documented_units:
            raise ValueError("Unverified time units")
        bounds = np.asarray(time_bounds).reshape(-1)
        if len(bounds) != 2 or not np.all(np.isfinite(bounds)):
            raise ValueError("Invalid time bounds")
        epoch = datetime(1980, 1, 6, tzinfo=timezone.utc)
        start = datetime(year, month, 1, tzinfo=timezone.utc)
        stop = start + timedelta(days=calendar.monthrange(year, month)[1])
        # NASA services may encode either an inclusive last second or exclusive end.
        if abs(float(bounds[0]) - (start - epoch).total_seconds()) > 1 or abs(float(bounds[1]) - (stop - epoch).total_seconds()) > 1:
            raise ValueError("Time bounds do not match the filename's calendar month")
        return {"filename": original_name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "precipitation_attributes": attrs, "shape": list(dataset.shape), "dtype": str(dataset.dtype),
                "file_attributes": {key: attribute(value, hdf) for key, value in hdf.attrs.items()},
                "header_fields": header, "grid_verification": grid_evidence,
                "dimension_scale_paths": scale_paths,
                "packing": {"scale_factor_present": "scale_factor" in dataset.attrs,
                            "add_offset_present": "add_offset" in dataset.attrs,
                            "effective_scale_factor": 1.0, "effective_add_offset": 0.0},
                "time_attributes": {key: attribute(value, hdf) for key, value in hdf["Grid/time"].attrs.items()},
                "time": np.asarray(hdf["Grid/time"]).tolist(),
                "time_bnds": np.asarray(hdf["Grid/time_bnds"]).tolist(),
                "grid_verified": True, "calendar_month_verified": True}


def read_region(hdf, rows):
    lon, lat = np.asarray(hdf["Grid/lon"]), np.asarray(hdf["Grid/lat"])
    j = np.argmin(abs(lon[:, None] - np.array([r["lon_center"] for r in rows])), axis=0)
    k = np.argmin(abs(lat[:, None] - np.array([r["lat_center"] for r in rows])), axis=0)
    if not np.allclose(lon[j], [r["lon_center"] for r in rows], atol=2e-5, rtol=0) or not np.allclose(lat[k], [r["lat_center"] for r in rows], atol=2e-5, rtol=0):
        raise ValueError("File does not cover all regional grid cells")
    j0, j1, k0, k1 = j.min(), j.max(), k.min(), k.max()
    p = np.asarray(hdf["Grid/precipitation"][0, j0:j1+1, k0:k1+1])[j-j0, k-k0]
    q = None
    qfill = FILL
    if "Grid/precipitationQualityIndex" in hdf:
        qi = hdf["Grid/precipitationQualityIndex"]
        q = np.asarray(qi[0, j0:j1+1, k0:k1+1])[j-j0, k-k0]
        qfill = float(np.asarray(qi.attrs["_FillValue"]).reshape(-1)[0])
    return p, q, qfill
