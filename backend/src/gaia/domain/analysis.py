"""Pure calendar aggregation and the fixed GAIA Sen/Mann–Kendall method.

No HTTP, persistence, preparation or third-party numerical dependencies.
"""

from collections import Counter
from dataclasses import dataclass
from math import erfc, fsum, isfinite, sqrt
from statistics import NormalDist, median
from typing import Literal, Sequence

METHOD_VERSION = "gaia-sen-mk-v1"
MINIMUM_VALID_YEARS = 20
MINIMUM_COVERAGE = .8
SEASONS = {"DJF": (12, 1, 2), "MAM": (3, 4, 5), "JJA": (6, 7, 8), "SON": (9, 10, 11)}
AGGREGATIONS = ("annual", *(f"month:{month:02d}" for month in range(1, 13)), *(f"season:{season}" for season in SEASONS))
EvidenceStatus = Literal["significant", "inconclusive", "insufficient_data"]


@dataclass(frozen=True)
class MonthlyObservation:
    year: int
    month: int
    precipitation_mm: float | None
    quality_status: str = "observed"
    missing_reason: str | None = None


@dataclass(frozen=True)
class AnnualPoint:
    year: int
    precipitation_mm: float | None
    missing_months: tuple[str, ...] = ()


@dataclass(frozen=True)
class TrendEstimate:
    slope_mm_per_decade: float
    confidence_interval_95_mm_per_decade: tuple[float, float]
    p_value: float
    mann_kendall_s: int
    variance_s: float
    z_score: float


@dataclass(frozen=True)
class AggregationAnalysis:
    aggregation: str
    series: tuple[AnnualPoint, ...]
    requested_years: int
    valid_years: int
    coverage: float
    minimum_valid_years: int
    minimum_coverage: float
    status: EvidenceStatus
    insufficient_reasons: tuple[str, ...]
    slope_mm_per_decade: float | None
    confidence_interval_95_mm_per_decade: tuple[float, float] | None
    p_value: float | None


def required_months(year: int, aggregation: str) -> tuple[tuple[int, int], ...]:
    if aggregation not in AGGREGATIONS:
        raise ValueError("Unknown aggregation")
    if aggregation == "annual":
        return tuple((year, month) for month in range(1, 13))
    if aggregation.startswith("month:"):
        return ((year, int(aggregation[6:])),)
    season = aggregation[7:]
    return tuple((year - 1 if season == "DJF" and month == 12 else year, month) for month in SEASONS[season])


def aggregate(observations: Sequence[MonthlyObservation], start_year: int, end_year: int,
              aggregation: str) -> tuple[AnnualPoint, ...]:
    if type(start_year) is not int or type(end_year) is not int or not 1 <= start_year <= end_year <= 9999:
        raise ValueError("Invalid inclusive calendar period")
    if aggregation not in AGGREGATIONS:
        raise ValueError("Unknown aggregation")
    indexed = {}
    for observation in observations:
        key = observation.year, observation.month
        if (type(observation.year) is not int or not 1 <= observation.year <= 9999
                or type(observation.month) is not int or not 1 <= observation.month <= 12 or key in indexed):
            raise ValueError("Invalid or duplicate monthly observation")
        value = observation.precipitation_mm
        if observation.quality_status == "observed" and value is not None:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
                raise ValueError("Observed precipitation must be finite and nonnegative")
        indexed[key] = observation
    points = []
    for year in range(start_year, end_year + 1):
        missing, values = [], []
        for key in required_months(year, aggregation):
            observation = indexed.get(key)
            if observation is None or observation.quality_status != "observed" or observation.precipitation_mm is None:
                missing.append(f"{key[0]:04d}-{key[1]:02d}")
            else:
                values.append(observation.precipitation_mm)
        points.append(AnnualPoint(year, None if missing else fsum(values), tuple(missing)))
    return tuple(points)


def estimate_trend(years: Sequence[int], values: Sequence[float]) -> TrendEstimate:
    pairs = sorted(zip(years, values, strict=True))
    n = len(pairs)
    if n < 2 or any(type(year) is not int for year, _ in pairs) or len({year for year, _ in pairs}) != n:
        raise ValueError("Inference requires at least two unique calendar years")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0 for _, value in pairs):
        raise ValueError("Inference requires finite, nonnegative precipitation")
    slopes, score = [], 0
    for i, (year, value) in enumerate(pairs):
        for later_year, later_value in pairs[i + 1:]:
            difference = later_value - value
            slopes.append(difference / (later_year - year))
            score += (difference > 0) - (difference < 0)
    slopes.sort()
    ties = Counter(value for _, value in pairs)
    variance = (n * (n - 1) * (2 * n + 5) - sum(t * (t - 1) * (2 * t + 5) for t in ties.values())) / 18
    if variance == 0:
        return TrendEstimate(0., (0., 0.), 1., 0, 0., 0.)
    z = (score - (1 if score > 0 else -1)) / sqrt(variance) if score else 0.
    p = erfc(abs(z) / sqrt(2))
    # Sen (1968) rank interval, normal/tie variance; nearest-even ranks,
    # with the one-based lower rank translated to a zero-based index.
    count = len(slopes)
    critical = NormalDist().inv_cdf(.975) * sqrt(variance)
    lower = min(max(round((count - critical) / 2) - 1, 0), count - 1)
    upper = min(max(round((count + critical) / 2), 0), count - 1)
    return TrendEstimate(float(median(slopes) * 10), (slopes[lower] * 10, slopes[upper] * 10), p,
                         score, variance, z)


def analyze(observations: Sequence[MonthlyObservation], start_year: int, end_year: int,
            aggregation: str) -> AggregationAnalysis:
    series = aggregate(observations, start_year, end_year, aggregation)
    valid = [point for point in series if point.precipitation_mm is not None]
    coverage = len(valid) / len(series)
    reasons = []
    if len(valid) < MINIMUM_VALID_YEARS:
        reasons.append("fewer_than_20_valid_years")
    if coverage < MINIMUM_COVERAGE:
        reasons.append("coverage_below_80_percent")
    trend = None if reasons else estimate_trend([point.year for point in valid], [point.precipitation_mm for point in valid])
    return AggregationAnalysis(aggregation, series, len(series), len(valid), coverage,
        MINIMUM_VALID_YEARS, MINIMUM_COVERAGE,
        "insufficient_data" if reasons else "significant" if trend.p_value < .05 else "inconclusive",
        tuple(reasons), trend.slope_mm_per_decade if trend else None,
        trend.confidence_interval_95_mm_per_decade if trend else None, trend.p_value if trend else None)
