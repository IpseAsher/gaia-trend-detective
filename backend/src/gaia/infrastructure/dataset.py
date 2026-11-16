"""Verify the prepared local dataset; never create or mutate it at runtime."""

from contextlib import closing, contextmanager
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from gaia.application.health import DatasetHealth, DatasetIncompatible, DatasetUnavailable
from gaia.application.analyses import AnalysisDataset, DatasetIdentity, RegionSeries
from gaia.domain.analysis import MonthlyObservation

DEFAULT_DATA_DIRECTORY = Path(__file__).resolve().parents[4] / "data"
SCHEMA_VERSION = 1
REQUIRED_COLUMNS = {
    "dataset_metadata": {
        "id": "INTEGER", "dataset_id": "TEXT", "dataset_version": "TEXT", "schema_version": "INTEGER",
        "prepared_at": "TEXT", "variable": "TEXT", "unit": "TEXT", "observation_start": "TEXT",
        "observation_end": "TEXT", "analysis_start_year": "INTEGER", "analysis_end_year": "INTEGER",
        "provenance_json": "TEXT",
    },
    "regions": {"region_id": "TEXT", "name": "TEXT", "geometry_geojson": "TEXT", "boundary_reference": "TEXT"},
    "monthly_observations": {
        "region_id": "TEXT", "year": "INTEGER", "month": "INTEGER", "precipitation_mm": "REAL",
        "quality_status": "TEXT", "missing_reason": "TEXT", "valid_area_fraction": "REAL",
        "valid_cells": "INTEGER", "potential_cells": "INTEGER", "qi_valid_area_fraction": "REAL",
        "qi_area_weighted_mean": "REAL", "qi_below_2_area_fraction_of_region": "REAL",
        "qi_below_10_area_fraction_of_region": "REAL", "source_filename": "TEXT", "source_sha256": "TEXT",
    },
}
PRIMARY_KEYS = {"dataset_metadata": ["id"], "regions": ["region_id"],
                "monthly_observations": ["region_id", "year", "month"]}


class SQLiteDatasetRepository:
    def __init__(self, database_path: Path, manifest_path: Path):
        self.database_path = Path(database_path)
        self.manifest_path = Path(manifest_path)

    def _manifest(self):
        try:
            raw = self.manifest_path.read_bytes()
            value = json.loads(raw)
            if (value["manifest_version"] != 1 or type(value["schema_version"]) is not int
                    or value["schema_version"] != SCHEMA_VERSION
                    or value["sqlite_file"] != self.database_path.name
                    or not isinstance(value["dataset_version"], str) or not value["dataset_version"]
                    or not re.fullmatch(r"[0-9a-f]{64}", value["sqlite_sha256"])
                    or type(value["region_count"]) is not int or value["region_count"] != 2
                    or type(value["monthly_observation_count"]) is not int or value["monthly_observation_count"] != 578):
                raise DatasetIncompatible
            return value, raw
        except OSError:
            raise DatasetUnavailable from None
        except (ValueError, KeyError, TypeError):
            raise DatasetIncompatible from None

    @staticmethod
    def _schema(connection):
        if connection.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            raise DatasetIncompatible
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if tables != set(REQUIRED_COLUMNS):
            raise DatasetIncompatible
        for table, expected in REQUIRED_COLUMNS.items():
            # Table identifiers are code constants, never manifest/request input.
            columns = connection.execute(f"PRAGMA table_info({table})").fetchall()
            actual = {column[1]: column[2] for column in columns}
            keys = [column[1] for column in sorted(columns, key=lambda c: c[5]) if column[5]]
            if actual != expected or keys != PRIMARY_KEYS[table]:
                raise DatasetIncompatible
        foreign_keys = connection.execute("PRAGMA foreign_key_list(monthly_observations)").fetchall()
        if len(foreign_keys) != 1 or foreign_keys[0][2:5] != ("regions", "region_id", "region_id"):
            raise DatasetIncompatible

    @contextmanager
    def open_read_only(self):
        """Yield a verified URI mode=ro/query_only connection; always close it."""
        manifest, raw_manifest = self._manifest()
        try:
            before = self.database_path.stat()
            with self.database_path.open("rb") as stream:
                actual_hash = hashlib.file_digest(stream, "sha256").hexdigest()
            if actual_hash != manifest["sqlite_sha256"] or before.st_size != manifest["sqlite_bytes"]:
                raise DatasetIncompatible
            uri = self.database_path.resolve().as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True)) as connection:
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA query_only=ON")
                self._schema(connection)
                metadata = connection.execute(
                    "SELECT dataset_id, dataset_version, schema_version, variable, unit, observation_start, observation_end, analysis_start_year, analysis_end_year FROM dataset_metadata"
                ).fetchall()
                coverage = manifest["coverage"]
                expected_metadata = (manifest["dataset_id"], manifest["dataset_version"], SCHEMA_VERSION,
                    "precipitation", "mm", coverage["observation_start"], coverage["observation_end"],
                    coverage["analysis_start_year"], coverage["analysis_end_year"])
                if metadata != [expected_metadata]:
                    raise DatasetIncompatible
                counts = (connection.execute("SELECT COUNT(*) FROM regions").fetchone()[0],
                          connection.execute("SELECT COUNT(*) FROM monthly_observations").fetchone()[0])
                if counts != (manifest["region_count"], manifest["monthly_observation_count"]):
                    raise DatasetIncompatible
                if connection.execute("PRAGMA foreign_key_check").fetchall():
                    raise DatasetIncompatible
                after = self.database_path.stat()
                if (before.st_mtime_ns, before.st_size, before.st_ino) != (after.st_mtime_ns, after.st_size, after.st_ino):
                    raise DatasetIncompatible
                if self.manifest_path.read_bytes() != raw_manifest:
                    raise DatasetIncompatible
                yield connection, manifest
        except OSError:
            raise DatasetUnavailable from None
        except (sqlite3.DatabaseError, ValueError, KeyError, TypeError):
            raise DatasetIncompatible from None

    def verify(self) -> DatasetHealth:
        with self.open_read_only() as (_, manifest):
            return DatasetHealth(dataset_version=manifest["dataset_version"])

    def read_analysis_data(self, region_ids: tuple[str, ...], start_year: int, end_year: int) -> AnalysisDataset:
        with self.open_read_only() as (connection, manifest):
            prepared_at, raw_provenance = connection.execute(
                "SELECT prepared_at, provenance_json FROM dataset_metadata WHERE id=1").fetchone()
            provenance = json.loads(raw_provenance)
            placeholders = ",".join("?" for _ in region_ids)
            rows = connection.execute(
                f"SELECT region_id,year,month,precipitation_mm,quality_status,missing_reason FROM monthly_observations "
                f"WHERE region_id IN ({placeholders}) AND year BETWEEN ? AND ? ORDER BY region_id,year,month",
                (*region_ids, start_year - 1, end_year)).fetchall()
            monthly = {code: [] for code in region_ids}
            for code, year, month, value, quality, reason in rows:
                monthly[code].append(MonthlyObservation(year, month, value, quality, reason))
            regions = tuple(RegionSeries(code, name, json.loads(boundary), tuple(monthly.get(code, ())))
                for code, name, boundary in connection.execute(
                    "SELECT region_id,name,boundary_reference FROM regions ORDER BY region_id"))
            # The immutable SQLite retains every original hash. HTTP provenance
            # identifies that artifact and its preparation without repeating 289
            # raw-file records in every analysis response.
            selected_provenance = {key: provenance[key] for key in (
                "precipitation", "boundaries", "preparation_inputs_sha256", "input_files_sha256",
                "preparation_code_sha256", "area_method", "spatial_acceptance_fraction", "quality_index_policy",
                "conversion", "missing_policy", "original_crs", "geometry_crs", "boundary_transformation",
                "shared_source_cells")}
            return AnalysisDataset(
                DatasetIdentity(manifest["dataset_id"], manifest["dataset_version"], manifest["schema_version"],
                                manifest["sqlite_sha256"], prepared_at),
                manifest["coverage"]["analysis_start_year"], manifest["coverage"]["analysis_end_year"],
                regions, selected_provenance)
