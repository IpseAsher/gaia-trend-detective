"""Domain verification uses frozen external values, never GAIA-generated expectations."""

import json
import math
from pathlib import Path

import pytest

from gaia.domain import analysis as domain

REFERENCE = json.loads((Path(__file__).parent / "fixtures/trend_reference.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", REFERENCE["synthetic_cases"], ids=lambda c: c["case_id"])
def test_sen_ci_and_mk_match_independent_frozen_reference(case):
    estimate = domain.estimate_trend(case["years"], case["values_mm"])
    expected, tolerances = case["expected"], REFERENCE["tolerances"]
    assert estimate.slope_mm_per_decade == pytest.approx(expected["slope_mm_per_decade"], abs=tolerances["slope_and_ci_mm_per_decade"], rel=0)
    assert estimate.confidence_interval_95_mm_per_decade == pytest.approx(expected["confidence_interval_95_mm_per_decade"], abs=tolerances["slope_and_ci_mm_per_decade"], rel=0)
    assert estimate.p_value == pytest.approx(expected["p_value"], abs=tolerances["p_and_z"], rel=0)
    assert estimate.z_score == pytest.approx(expected["z_score"], abs=tolerances["p_and_z"], rel=0)
    assert estimate.variance_s == pytest.approx(expected["variance_s"], abs=tolerances["variance_s"], rel=0)
    assert estimate.mann_kendall_s == expected["mann_kendall_s"]
    observations = [domain.MonthlyObservation(year, 1, value) for year, value in zip(case["years"], case["values_mm"], strict=True)]
    result = domain.analyze(observations, 2001, 2024, "month:01")
    assert result.status == expected["status"]


@pytest.mark.parametrize("aggregation,expected", [("month:01", 1.), ("month:12", 12.),
    ("season:DJF", 13.), ("season:MAM", 12.), ("season:JJA", 21.), ("season:SON", 30.), ("annual", 78.)])
def test_calendar_month_season_and_year_sums(aggregation, expected):
    observations = [domain.MonthlyObservation(2000, 12, 10.)]
    observations += [domain.MonthlyObservation(2001, month, float(month)) for month in range(1, 13)]
    point, = domain.aggregate(tuple(reversed(observations)), 2001, 2001, aggregation)
    assert point.year == 2001 and point.precipitation_mm == expected
    assert point.missing_months == ()


def test_missing_previous_december_invalidates_djf_but_not_calendar_year():
    observations = [domain.MonthlyObservation(2001, month, 1.) for month in range(1, 13)]
    winter, = domain.aggregate(observations, 2001, 2001, "season:DJF")
    annual, = domain.aggregate(observations, 2001, 2001, "annual")
    assert winter.precipitation_mm is None and winter.missing_months == ("2000-12",)
    assert annual.precipitation_mm == 12


@pytest.mark.parametrize("observation", [None, domain.MonthlyObservation(2001, 2, None),
    domain.MonthlyObservation(2001, 2, 5., "missing", "source_rejected")])
def test_one_missing_or_rejected_month_invalidates_whole_season(observation):
    observations = [domain.MonthlyObservation(2000, 12, 2.), domain.MonthlyObservation(2001, 1, 3.)]
    if observation is not None:
        observations.append(observation)
    point, = domain.aggregate(observations, 2001, 2001, "season:DJF")
    assert point.precipitation_mm is None and point.missing_months == ("2001-02",)


def test_zero_is_observed_and_constant_series_is_inconclusive():
    observations = [domain.MonthlyObservation(year, 1, 0.) for year in range(2001, 2025)]
    result = domain.analyze(observations, 2001, 2024, "month:01")
    assert result.valid_years == 24 and result.coverage == 1
    assert result.status == "inconclusive" and result.slope_mm_per_decade == 0
    assert result.confidence_interval_95_mm_per_decade == (0., 0.) and result.p_value == 1


@pytest.mark.parametrize("valid,requested,reasons", [
    (19, 24, ("fewer_than_20_valid_years", "coverage_below_80_percent")),
    (20, 30, ("coverage_below_80_percent",)),
    (5, 5, ("fewer_than_20_valid_years",)),
    (0, 24, ("fewer_than_20_valid_years", "coverage_below_80_percent")),
])
def test_insufficient_data_retains_gaps_and_nulls_estimates(valid, requested, reasons):
    observations = [domain.MonthlyObservation(2001 + i, 1, float(i)) for i in range(valid)]
    result = domain.analyze(observations, 2001, 2000 + requested, "month:01")
    assert result.status == "insufficient_data" and result.insufficient_reasons == reasons
    assert result.valid_years == valid and result.requested_years == requested
    assert len(result.series) == requested and result.coverage == valid / requested
    assert result.slope_mm_per_decade is result.confidence_interval_95_mm_per_decade is result.p_value is None


def test_exact_twenty_years_and_eighty_percent_are_accepted():
    observations = [domain.MonthlyObservation(year, 1, float(year - 2001)) for year in range(2001, 2021)]
    result = domain.analyze(observations, 2001, 2025, "month:01")
    assert result.valid_years == 20 and result.coverage == .8 and result.status == "significant"
    assert result.slope_mm_per_decade == 10 and result.insufficient_reasons == ()


def test_missing_calendar_years_are_not_compressed_for_slopes():
    years = [year for year in range(2001, 2025) if year not in (2004, 2007, 2011, 2018)]
    observations = [domain.MonthlyObservation(year, 1, float(4 * (year - 2001))) for year in years]
    result = domain.analyze(observations, 2001, 2024, "month:01")
    assert result.valid_years == 20 and result.requested_years == 24
    assert result.slope_mm_per_decade == 40 and result.confidence_interval_95_mm_per_decade == (40., 40.)
    assert [point.year for point in result.series if point.precipitation_mm is not None] == years


def test_p_equal_to_alpha_is_inconclusive(monkeypatch):
    monkeypatch.setattr(domain, "estimate_trend", lambda *args: domain.TrendEstimate(1., (-1., 2.), .05, 0, 1., 0.))
    result = domain.analyze([domain.MonthlyObservation(year, 1, 1.) for year in range(2001, 2025)], 2001, 2024, "month:01")
    assert result.status == "inconclusive"


@pytest.mark.parametrize("value", [-1., math.nan, math.inf, -math.inf, True])
def test_invalid_observed_precipitation_is_not_silently_used(value):
    with pytest.raises(ValueError):
        domain.aggregate([domain.MonthlyObservation(2001, 1, value)], 2001, 2001, "month:01")


def test_duplicate_months_and_duplicate_years_are_rejected():
    observation = domain.MonthlyObservation(2001, 1, 1.)
    with pytest.raises(ValueError):
        domain.aggregate([observation, observation], 2001, 2001, "annual")
    with pytest.raises(ValueError):
        domain.estimate_trend([2001, 2001], [1., 2.])
    with pytest.raises(ValueError):
        domain.estimate_trend([2001], [1.])


@pytest.mark.parametrize("aggregation", ["month:1", "month:13", "season:winter", "season:djf", ""])
def test_unsupported_aggregation_is_rejected(aggregation):
    with pytest.raises(ValueError):
        domain.aggregate([], 2001, 2024, aggregation)
