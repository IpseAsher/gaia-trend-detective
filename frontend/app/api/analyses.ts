export const REGIONS = [
  { id: "09", name: "Ciudad de México" },
  { id: "15", name: "Estado de México" },
] as const;

export const AGGREGATIONS = [
  { value: "season:DJF", label: "Winter · DJF" },
  { value: "season:MAM", label: "Spring · MAM" },
  { value: "season:JJA", label: "Summer · JJA" },
  { value: "season:SON", label: "Autumn · SON" },
  { value: "annual", label: "Annual total" },
  ...["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"].map(
    (label, index) => ({ value: `month:${String(index + 1).padStart(2, "0")}`, label }),
  ),
];

export type AnalysisQuery = {
  region_id: string[];
  start_year: number;
  end_year: number;
  aggregation: string;
};

export type AnnualPoint = { year: number; precipitation_mm: number | null; missing_months: string[] };
export type AggregationAnalysis = {
  aggregation: string;
  series: AnnualPoint[];
  requested_years: number;
  valid_years: number;
  coverage: number;
  status: "significant" | "inconclusive" | "insufficient_data";
  insufficient_reasons: string[];
  slope_mm_per_decade: number | null;
  confidence_interval_95_mm_per_decade: [number, number] | null;
  p_value: number | null;
};

export type RegionAnalysis = {
  region_id: string;
  name: string;
  analysis: AggregationAnalysis;
  annual_context: AggregationAnalysis;
};

export type AnalysesResponse = {
  query: AnalysisQuery;
  dataset: { dataset_version: string; sqlite_sha256: string };
  unit: "mm";
  method: { version: string; limitations: string[]; slope_unit: "mm/decade" };
  provenance: {
    precipitation: { provider: string; processing_version: string; doi: string };
    boundaries: { title: string; edition: string | number };
  };
  regions: RegionAnalysis[];
};

export function readQuery(params: URLSearchParams): AnalysisQuery {
  const codes = params.getAll("region_id");
  const region_id = codes.length ? codes : REGIONS.map(region => region.id);
  const start_year = Number(params.get("start_year") ?? 2001);
  const end_year = Number(params.get("end_year") ?? 2024);
  const aggregation = params.get("aggregation") ?? "season:DJF";
  if (!region_id.length || region_id.length > 2 || new Set(region_id).size !== region_id.length ||
      region_id.some(id => !REGIONS.some(region => region.id === id))) {
    throw new Error("Choose one or both of the available regions.");
  }
  if (!Number.isInteger(start_year) || !Number.isInteger(end_year) || start_year < 2001 || end_year > 2024 || start_year > end_year) {
    throw new Error("Choose a start and end year within 2001–2024, with the start year first.");
  }
  if (!AGGREGATIONS.some(option => option.value === aggregation)) throw new Error("Choose an available month, season, or annual total.");
  return { region_id: [...region_id].sort(), start_year, end_year, aggregation };
}

export function queryParams(query: AnalysisQuery): URLSearchParams {
  const params = new URLSearchParams();
  query.region_id.forEach(id => params.append("region_id", id));
  params.set("start_year", String(query.start_year));
  params.set("end_year", String(query.end_year));
  params.set("aggregation", query.aggregation);
  return params;
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === "string");
}

function validAnalysis(value: unknown, query: AnalysisQuery, aggregation: string): boolean {
  if (!record(value) || value.aggregation !== aggregation || !Array.isArray(value.series) ||
      value.requested_years !== query.end_year - query.start_year + 1 || value.series.length !== value.requested_years ||
      !finite(value.valid_years) || !Number.isInteger(value.valid_years) || value.valid_years < 0 || value.valid_years > value.requested_years ||
      !finite(value.coverage) || value.coverage < 0 || value.coverage > 1 || !strings(value.insufficient_reasons)) return false;
  if (!value.series.every((point, index) => record(point) && point.year === query.start_year + index &&
      (point.precipitation_mm === null || (finite(point.precipitation_mm) && point.precipitation_mm >= 0)) && strings(point.missing_months))) return false;
  if (value.status === "insufficient_data") {
    return value.slope_mm_per_decade === null && value.confidence_interval_95_mm_per_decade === null && value.p_value === null;
  }
  const interval = value.confidence_interval_95_mm_per_decade;
  return (value.status === "significant" || value.status === "inconclusive") && finite(value.slope_mm_per_decade) &&
    Array.isArray(interval) && interval.length === 2 && interval.every(finite) && interval[0] <= interval[1] &&
    finite(value.p_value) && value.p_value >= 0 && value.p_value <= 1;
}

function validResponse(body: unknown, query: AnalysisQuery): body is AnalysesResponse {
  if (!record(body) || body.unit !== "mm" || !record(body.query) || !strings(body.query.region_id) ||
      body.query.region_id.join(",") !== query.region_id.join(",") || body.query.start_year !== query.start_year ||
      body.query.end_year !== query.end_year || body.query.aggregation !== query.aggregation ||
      !record(body.dataset) || typeof body.dataset.dataset_version !== "string" || typeof body.dataset.sqlite_sha256 !== "string" ||
      !record(body.method) || typeof body.method.version !== "string" || body.method.slope_unit !== "mm/decade" || !strings(body.method.limitations) ||
      !record(body.provenance) || !record(body.provenance.precipitation) || !record(body.provenance.boundaries)) return false;
  const source = body.provenance.precipitation, boundaries = body.provenance.boundaries;
  if (typeof source.provider !== "string" || typeof source.processing_version !== "string" || typeof source.doi !== "string" ||
      typeof boundaries.title !== "string" || !["string", "number"].includes(typeof boundaries.edition)) return false;
  return Array.isArray(body.regions) && body.regions.length === query.region_id.length && body.regions.every((region, index) =>
    record(region) && region.region_id === query.region_id[index] && typeof region.name === "string" &&
    validAnalysis(region.analysis, query, query.aggregation) && validAnalysis(region.annual_context, query, "annual"));
}

export async function fetchAnalyses(query: AnalysisQuery, signal: AbortSignal): Promise<AnalysesResponse> {
  const response = await fetch(`/api/v1/analyses?${queryParams(query)}`, {
    signal, cache: "no-cache", headers: { Accept: "application/json" },
  });
  const body: unknown = await response.json();
  if (!response.ok) {
    const message = record(body) && record(body.error) && typeof body.error.message === "string"
      ? body.error.message : "The analysis could not be loaded. Please try again.";
    throw new Error(message);
  }
  if (!validResponse(body, query)) throw new Error("The analysis response could not be verified. Please try again.");
  return body;
}
