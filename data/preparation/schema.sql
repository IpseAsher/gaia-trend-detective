PRAGMA foreign_keys = ON;
PRAGMA user_version = 1;

CREATE TABLE dataset_metadata (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    dataset_id TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    prepared_at TEXT NOT NULL,
    variable TEXT NOT NULL CHECK (variable = 'precipitation'),
    unit TEXT NOT NULL CHECK (unit = 'mm'),
    observation_start TEXT NOT NULL,
    observation_end TEXT NOT NULL,
    analysis_start_year INTEGER NOT NULL,
    analysis_end_year INTEGER NOT NULL,
    provenance_json TEXT NOT NULL CHECK (json_valid(provenance_json))
) STRICT;

CREATE TABLE regions (
    region_id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    geometry_geojson TEXT NOT NULL CHECK (json_valid(geometry_geojson)),
    boundary_reference TEXT NOT NULL CHECK (json_valid(boundary_reference))
) STRICT;

CREATE TABLE monthly_observations (
    region_id TEXT NOT NULL REFERENCES regions(region_id),
    year INTEGER NOT NULL CHECK (year BETWEEN 1 AND 9999),
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    precipitation_mm REAL CHECK (precipitation_mm >= 0 AND precipitation_mm < 1e308),
    quality_status TEXT NOT NULL CHECK (quality_status IN ('observed', 'missing')),
    missing_reason TEXT,
    valid_area_fraction REAL NOT NULL CHECK (valid_area_fraction BETWEEN 0 AND 1),
    valid_cells INTEGER NOT NULL CHECK (valid_cells >= 0 AND valid_cells <= potential_cells),
    potential_cells INTEGER NOT NULL CHECK (potential_cells > 0),
    qi_valid_area_fraction REAL CHECK (qi_valid_area_fraction BETWEEN 0 AND 1),
    qi_area_weighted_mean REAL CHECK (qi_area_weighted_mean BETWEEN 0 AND 3000),
    qi_below_2_area_fraction_of_region REAL CHECK (qi_below_2_area_fraction_of_region BETWEEN 0 AND 1),
    qi_below_10_area_fraction_of_region REAL CHECK (qi_below_10_area_fraction_of_region BETWEEN 0 AND 1),
    source_filename TEXT NOT NULL,
    source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64),
    PRIMARY KEY (region_id, year, month),
    CHECK (
        (quality_status = 'observed' AND precipitation_mm IS NOT NULL AND missing_reason IS NULL)
        OR (quality_status = 'missing' AND precipitation_mm IS NULL AND missing_reason IS NOT NULL)
    )
) STRICT;
