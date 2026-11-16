import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Form, Link, useSearchParams } from "react-router";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { AGGREGATIONS, REGIONS, fetchAnalyses, queryParams, readQuery,
  type AggregationAnalysis, type AnalysesResponse, type AnalysisQuery } from "../api/analyses";

type LoadState = { kind: "loading"; key: string } | { kind: "error"; key: string; message: string } |
  { kind: "ready"; key: string; data: AnalysesResponse };

const YEARS = Array.from({ length: 24 }, (_, index) => 2001 + index);
const COLORS: Record<string, string> = { "09": "#176956", "15": "#315da8" };
const numbers = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const slopes = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: "exceptZero" });
const label = (aggregation: string) => AGGREGATIONS.find(option => option.value === aggregation)?.label ?? aggregation;
const amount = (value: number | null) => value === null ? "—" : numbers.format(value);
const pValue = (value: number | null) => value === null ? "—" : value < .001 ? "<0.001" : value.toFixed(3);

function Evidence({ result }: { result: AggregationAnalysis }) {
  const text = { significant: "Significant", inconclusive: "Inconclusive", insufficient_data: "Insufficient data" }[result.status];
  return <span className={`evidence evidence-${result.status}`}>{text}</span>;
}

function Results({ data }: { data: AnalysesResponse }) {
  const { query, regions } = data;
  const points = regions[0].analysis.series.map((point, index) => ({
    year: point.year,
    ...Object.fromEntries(regions.map(region => [region.region_id, region.analysis.series[index].precipitation_mm])),
  }));
  const hasValues = regions.some(region => region.analysis.valid_years > 0);
  const rows = regions.flatMap(region => (query.aggregation === "annual" ? [region.analysis] : [region.analysis, region.annual_context])
    .map(result => ({ region, result })));

  return (
    <>
      <section className="chart-panel" aria-labelledby="chart-title">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">The observed record</p>
            <h2 id="chart-title">{label(query.aggregation)}</h2>
          </div>
          <span className="period-tag">{query.start_year}–{query.end_year}</span>
        </div>
        <ul className="chart-legend" aria-label="Chart series">
          {regions.map(region => <li key={region.region_id}>
            <span aria-hidden="true" className={`line-key line-${region.region_id}`} />{region.name}
          </li>)}
        </ul>
        <figure aria-labelledby="chart-title" aria-describedby="chart-caption">
          <p className="axis-unit">Precipitation (mm)</p>
          {hasValues ? (
            <div className="rain-chart">
              <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                <LineChart data={points} accessibilityLayer margin={{ top: 16, right: 20, bottom: 8, left: 0 }}>
                  <CartesianGrid vertical={false} stroke="#dce4dc" strokeDasharray="3 4" />
                  <XAxis dataKey="year" type="number" domain={["dataMin", "dataMax"]} allowDecimals={false}
                    minTickGap={35} tickLine={false} axisLine={false} tick={{ fill: "#526457", fontSize: 12 }} />
                  <YAxis domain={[0, "auto"]} width={52} tickLine={false} axisLine={false}
                    tick={{ fill: "#526457", fontSize: 12 }} />
                  <Tooltip labelFormatter={value => `Year ${value}`} formatter={(value, name) => [`${amount(typeof value === "number" ? value : null)} mm`, name]}
                    contentStyle={{ borderRadius: 8, borderColor: "#b8c7b6", color: "#203f36" }} />
                  {regions.map(region => <Line key={region.region_id} type="linear" dataKey={region.region_id}
                    name={region.name} stroke={COLORS[region.region_id]} strokeWidth={2.5}
                    strokeDasharray={region.region_id === "15" ? "7 4" : undefined} connectNulls={false}
                    dot={{ r: 3, strokeWidth: 1.5, fill: "#fff" }} activeDot={{ r: 5 }} isAnimationActive={false} />)}
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : <p className="empty-chart" role="status">No complete observations are available for this selection.</p>}
          <figcaption id="chart-caption">
            Each point is a regional {query.aggregation === "annual" ? "annual" : query.aggregation.startsWith("season:") ? "seasonal" : "monthly"} total on the same scale.
            {query.aggregation === "season:DJF" && " DJF includes December of the preceding year, January, and February."}
          </figcaption>
        </figure>
      </section>

      <section className="estimates-panel" aria-labelledby="estimates-title">
        <div className="panel-heading">
          <div><p className="eyebrow">The statistical evidence</p><h2 id="estimates-title">Trend estimates &amp; annual context</h2></div>
          <span className="unit-note">Slopes &amp; intervals in mm/decade</span>
        </div>
        <div className="table-scroll" role="region" aria-label="Regional trend estimates" tabIndex={0}>
          <table className="estimates-table">
            <caption className="sr-only">Requested aggregation and independently evaluated annual context for each region.</caption>
            <thead><tr><th scope="col">Region</th><th scope="col">Period</th><th scope="col">Valid years</th>
              <th scope="col">Sen slope</th><th scope="col">95% confidence interval</th><th scope="col">MK p-value</th><th scope="col">Evidence</th></tr></thead>
            <tbody>{rows.map(({ region, result }) => <tr key={`${region.region_id}-${result.aggregation}`} className={result.aggregation === "annual" ? "annual-row" : undefined}>
              <th scope="row"><span className={`region-dot region-${region.region_id}`} aria-hidden="true" />{region.name}</th>
              <td>{result.aggregation === "annual" ? "Annual" : query.aggregation.startsWith("season:") ? query.aggregation.slice(7) : label(result.aggregation)}</td>
              <td>{result.valid_years}/{result.requested_years}<span className="cell-detail">{Math.round(result.coverage * 100)}% coverage</span></td>
              <td className="number slope-value">{result.slope_mm_per_decade === null ? "—" : slopes.format(result.slope_mm_per_decade)}</td>
              <td className="number">{result.confidence_interval_95_mm_per_decade === null ? "—" :
                `[${amount(result.confidence_interval_95_mm_per_decade[0])}, ${amount(result.confidence_interval_95_mm_per_decade[1])}]`}</td>
              <td className="number">{pValue(result.p_value)}</td><td><Evidence result={result} /></td>
            </tr>)}</tbody>
          </table>
        </div>
        <p className="table-hint">Scroll horizontally to view all estimates.</p>
        <p className="interpretation">Annual context requires all twelve months and is evaluated separately. Estimates require at least 20 valid years and 80% coverage. Inconclusive evidence does not establish an absence of change.</p>
      </section>

      <details className="data-disclosure">
        <summary>View the precipitation values</summary>
        <div className="table-scroll" role="region" aria-label="Observed precipitation values" tabIndex={0}>
          <table className="values-table"><caption>{label(query.aggregation)} · regional totals in mm</caption>
            <thead><tr><th scope="col">Year</th>{regions.map(region => <th scope="col" key={region.region_id}>{region.name}</th>)}</tr></thead>
            <tbody>{regions[0].analysis.series.map((point, index) => <tr key={point.year}><th scope="row">{point.year}</th>
              {regions.map(region => <td key={region.region_id}>{amount(region.analysis.series[index].precipitation_mm)}</td>)}
            </tr>)}</tbody></table>
        </div>
      </details>

      <section className="provenance-panel" aria-labelledby="provenance-title">
        <div><p className="eyebrow" id="provenance-title">Data &amp; method</p>
          <p className="source-line">{data.provenance.precipitation.provider} · IMERG {data.provenance.precipitation.processing_version}
            <span aria-hidden="true"> / </span> INEGI Marco Geoestadístico {data.provenance.boundaries.edition}</p>
          <p className="method-note">Theil–Sen · Sen 95% interval · Two-sided Mann–Kendall. Intervals and p-values are pointwise and assume temporal independence.</p>
        </div>
        <details><summary>Dataset identity &amp; interpretation</summary>
          <p>Dataset: <code>{data.dataset.dataset_version}</code></p>
          <p>Method: <code>{data.method.version}</code></p>
          <ul>{data.method.limitations.map(note => <li key={note}>{note}</li>)}</ul>
          <p><a href={`https://doi.org/${data.provenance.precipitation.doi}`} target="_blank" rel="noreferrer">NASA source citation ↗</a></p>
        </details>
      </section>
    </>
  );
}

export default function Explore() {
  const [params] = useSearchParams();
  const selection = useMemo(() => {
    try { return { query: readQuery(params), error: null }; }
    catch (error) { return { query: readQuery(new URLSearchParams()), error: error instanceof Error ? error.message : "Invalid selection." }; }
  }, [params]);
  const query = selection.query;
  const key = queryParams(query).toString();
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<LoadState>({ kind: "loading", key });
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (selection.error) return;
    const controller = new AbortController();
    let active = true;
    const timeout = window.setTimeout(() => controller.abort(), 15_000);
    setState({ kind: "loading", key });
    fetchAnalyses(query, controller.signal).then(data => {
      if (active) setState({ kind: "ready", key, data });
    }).catch(error => {
      if (active) setState({ kind: "error", key, message: controller.signal.aborted ? "The request timed out. Please try again." :
        error instanceof Error ? error.message : "Unable to load the analysis. Please try again." });
    }).finally(() => window.clearTimeout(timeout));
    return () => { active = false; controller.abort(); window.clearTimeout(timeout); };
  }, [key, attempt, selection.error]);

  function validateForm(event: FormEvent<HTMLFormElement>) {
    const form = new FormData(event.currentTarget);
    try {
      const proposed = new URLSearchParams();
      for (const [name, value] of form) if (typeof value === "string") proposed.append(name, value);
      if (!form.getAll("region_id").length) throw new Error("Select at least one region.");
      readQuery(proposed);
      setFormError(null);
    } catch (error) {
      event.preventDefault();
      setFormError(error instanceof Error ? error.message : "Check your selection.");
    }
  }

  const current = state.key === key ? state : { kind: "loading" as const, key };
  return (
    <div className="page-shell explore-shell">
      <a className="skip-link" href="#exploration">Skip to results</a>
      <header className="site-header explore-header">
        <Link to="/" className="brand-link" aria-label="GAIA home"><span className="wordmark">GAIA<span aria-hidden="true">.</span></span>
          <span className="brand-description">Earth System Trend Detective</span></Link>
        <nav className="site-nav" aria-label="Main navigation"><Link className="text-link" to="/">Home</Link>
          <Link className="text-link" to="/explore" aria-current="page">Explore rainfall</Link></nav>
      </header>
      <main id="exploration" tabIndex={-1}>
        <div className="explore-intro"><div><p className="eyebrow">Regional exploration</p><h1>Precipitation, in perspective.</h1>
          <p>Compare the observed record, the estimated trend, and its annual context.</p></div>
          <span className="source-tag">NASA IMERG · 2001–2024</span></div>

        <Form key={key} method="get" action="/explore" className="analysis-controls" onSubmit={validateForm} preventScrollReset>
          <fieldset><legend>Regions</legend><div className="region-options">{REGIONS.map(region => <label key={region.id}>
            <input type="checkbox" name="region_id" value={region.id} defaultChecked={query.region_id.includes(region.id)} />{region.name}
          </label>)}</div></fieldset>
          <label className="select-field">From<select name="start_year" defaultValue={query.start_year}>{YEARS.map(year => <option key={year}>{year}</option>)}</select></label>
          <label className="select-field">To<select name="end_year" defaultValue={query.end_year}>{YEARS.map(year => <option key={year}>{year}</option>)}</select></label>
          <label className="select-field aggregation-select">Aggregation<select name="aggregation" defaultValue={query.aggregation}>
            {AGGREGATIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
          <button type="submit">Update analysis <span aria-hidden="true">↗</span></button>
          {formError && <p role="alert" className="form-error">{formError}</p>}
        </Form>

        {selection.error ? <section className="analysis-message" role="alert"><h2>Check the selection</h2><p>{selection.error}</p>
          <Link className="text-link" to="/explore">Reset to DJF 2001–2024</Link></section> :
          current.kind === "loading" ? <section className="analysis-message" role="status"><p className="eyebrow">Loading the observed record</p>
            <h2>Fetching regional precipitation…</h2><p>The series and statistical evidence will appear together.</p></section> :
          current.kind === "error" ? <section className="analysis-message" role="alert"><h2>Analysis unavailable</h2><p>{current.message}</p>
            <button type="button" onClick={() => setAttempt(value => value + 1)}>Try again</button></section> : <Results data={current.data} />}
      </main>
      <footer>GAIA · Regional precipitation, with the evidence in view.</footer>
    </div>
  );
}
