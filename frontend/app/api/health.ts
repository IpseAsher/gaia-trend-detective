export type HealthResult =
  | { kind: "unavailable" }
  | { kind: "incompatible" }
  | { kind: "ready"; datasetVersion: string };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export async function checkHealth(signal: AbortSignal): Promise<HealthResult> {
  const response = await fetch("/api/v1/health", {
    signal,
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  const body: unknown = await response.json();

  if (response.status === 503 && isRecord(body) && isRecord(body.error)) {
    if (body.error.code === "dataset_unavailable") return { kind: "unavailable" };
    if (body.error.code === "dataset_incompatible") return { kind: "incompatible" };
  }

  if (
    response.status === 200 &&
    isRecord(body) &&
    body.status === "ok" &&
    body.sqlite_read_only === true &&
    typeof body.dataset_version === "string" &&
    body.dataset_version.trim().length > 0
  ) {
    return { kind: "ready", datasetVersion: body.dataset_version };
  }

  throw new Error("Unexpected health response");
}
