"""Read-only analysis orchestration; repository ports are defined here."""

from dataclasses import dataclass
from typing import Protocol

from gaia.application.health import DatasetRepository
from gaia.domain.analysis import AGGREGATIONS, METHOD_VERSION, AggregationAnalysis, MonthlyObservation, analyze


class AnalysisInputError(Exception):
    code = "invalid_request"
    message = "Invalid analysis parameters."


class InvalidPeriod(AnalysisInputError):
    code = "invalid_period"
    message = "The inclusive period is outside the dataset analysis coverage."


class InvalidRegions(AnalysisInputError):
    code = "invalid_regions"
    message = "Select one or two distinct region identifiers."


class InvalidAggregation(AnalysisInputError):
    code = "invalid_aggregation"
    message = "The requested aggregation is not supported."


class UnknownRegion(AnalysisInputError):
    code = "unknown_region"
    message = "A requested region does not exist in this dataset."


@dataclass(frozen=True)
class RegionSeries:
    region_id: str
    name: str
    boundary_provenance: dict[str, object]
    observations: tuple[MonthlyObservation, ...]


@dataclass(frozen=True)
class DatasetIdentity:
    dataset_id: str
    dataset_version: str
    schema_version: int
    sqlite_sha256: str
    prepared_at: str


@dataclass(frozen=True)
class AnalysisDataset:
    identity: DatasetIdentity
    analysis_start_year: int
    analysis_end_year: int
    regions: tuple[RegionSeries, ...]
    provenance: dict[str, object]


class AnalysisRepository(Protocol):
    def read_analysis_data(self, region_ids: tuple[str, ...], start_year: int, end_year: int) -> AnalysisDataset:
        """Read an immutable verified snapshot, including prior December."""
        ...


class GAIARepository(DatasetRepository, AnalysisRepository, Protocol):
    """Infrastructure implements the health and analysis application ports."""


@dataclass(frozen=True)
class AnalysisQuery:
    region_id: tuple[str, ...]
    start_year: int
    end_year: int
    aggregation: str


@dataclass(frozen=True)
class MethodDescription:
    version: str = METHOD_VERSION
    slope_estimator: str = "Theil-Sen median of all valid calendar-year pair slopes"
    confidence_interval: str = "Sen normal rank interval with precipitation-tie variance and nearest-even ranks"
    significance_test: str = "two-sided original Mann-Kendall, tie variance and continuity correction"
    slope_unit: str = "mm/decade"
    confidence_level: float = .95
    alpha: float = .05
    limitations: tuple[str, ...] = (
        "Inference assumes temporal independence; no autocorrelation adjustment is applied.",
        "Intervals and p-values are pointwise; exploring multiple queries does not provide joint significance.",
        "Regional estimates are individual results, not a significance test of their difference.",
    )


@dataclass(frozen=True)
class RegionAnalysis:
    region_id: str
    name: str
    boundary_provenance: dict[str, object]
    analysis: AggregationAnalysis
    annual_context: AggregationAnalysis


@dataclass(frozen=True)
class AnalysesResponse:
    query: AnalysisQuery
    dataset: DatasetIdentity
    variable: str
    unit: str
    method: MethodDescription
    provenance: dict[str, object]
    regions: tuple[RegionAnalysis, ...]


@dataclass(frozen=True)
class AnalyzeRegions:
    repository: AnalysisRepository

    def execute(self, region_ids: tuple[str, ...], start_year: int, end_year: int, aggregation: str) -> AnalysesResponse:
        if not 1 <= len(region_ids) <= 2 or len(set(region_ids)) != len(region_ids):
            raise InvalidRegions
        if aggregation not in AGGREGATIONS:
            raise InvalidAggregation
        if type(start_year) is not int or type(end_year) is not int or not 1 <= start_year <= end_year <= 9999:
            raise InvalidPeriod
        region_ids = tuple(sorted(region_ids))
        dataset = self.repository.read_analysis_data(region_ids, start_year, end_year)
        if start_year < dataset.analysis_start_year or end_year > dataset.analysis_end_year:
            raise InvalidPeriod
        available = {region.region_id: region for region in dataset.regions}
        if any(code not in available for code in region_ids):
            raise UnknownRegion
        results = []
        for code in region_ids:
            region = available[code]
            selected = analyze(region.observations, start_year, end_year, aggregation)
            annual = selected if aggregation == "annual" else analyze(region.observations, start_year, end_year, "annual")
            results.append(RegionAnalysis(code, region.name, region.boundary_provenance, selected, annual))
        return AnalysesResponse(AnalysisQuery(region_ids, start_year, end_year, aggregation), dataset.identity,
                                "precipitation", "mm", MethodDescription(), dataset.provenance, tuple(results))
