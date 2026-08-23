/**
 * Where the API runs. Paths below are the server's own routes -- /companies,
 * /get-accepted-solutions -- appended to this, with nothing in between: there
 * is no /api prefix on the server, so there is none here either.
 *
 * Point a deployment somewhere else with NEXT_PUBLIC_API_URL, e.g. at a server
 * on your own machine. That server has to allow this app's origin: set
 * ALLOWED_ORIGINS on it, or the browser refuses the request before sending it.
 */
const DEFAULT_API_URL = "https://bernhackt26.kirchenfeldrobotics.ch";

// A trailing slash would make every path a double slash, which FastAPI 404s on.
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_URL).replace(/\/+$/, "");

// A hung request should fail rather than spin forever behind a "Loading…".
const TIMEOUT_MS = 30_000;

/** A row of the `companies` table, as `/companies` returns it. */
export type Company = {
  // Text uuid on newer servers, an integer on older ones. Only ever used as a
  // key, so both are accepted rather than forcing one and breaking on the other.
  id: string | number;
  name: string;
  // Only servers that still keep categories send this.
  category?: string | null;
  website: string | null;
  details: string | null;
  created_at: string;
};

/** A failed request, carrying the status so callers can tell a 404 apart. */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

// A proxy in front of the API answers with its own HTML error page, which says
// nothing useful once it is stripped of markup.
const STATUS_MESSAGE: Record<number, string> = {
  404: "This server does not offer that endpoint.",
  405: "This server does not offer that endpoint.",
  500: "The API failed while handling the request.",
  502: "The API is not reachable right now. The service behind the proxy is down or restarting.",
  503: "The API is temporarily unavailable.",
  504: "The API took too long to answer.",
};

/** FastAPI reports failures as {"detail": ...}; show that rather than raw JSON. */
function errorMessage(body: string, response: Response): string {
  const trimmed = body.trim();

  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    try {
      const detail = JSON.parse(trimmed).detail;
      if (typeof detail === "string") return detail;
      if (detail !== undefined) return JSON.stringify(detail);
    } catch {
      // not JSON after all; fall through
    }
  }

  const known = STATUS_MESSAGE[response.status];
  if (known !== undefined) return known;

  // Never render a whole HTML error page into the view.
  if (trimmed === "" || trimmed.startsWith("<"))
    return `${response.status} ${response.statusText}`.trim();

  return trimmed.slice(0, 300);
}

/** fetch() rejects with a bare "Failed to fetch"; say what that actually means. */
function networkMessage(cause: unknown): string {
  if (cause instanceof DOMException && cause.name === "TimeoutError")
    return `${API_URL} did not answer within ${TIMEOUT_MS / 1000} seconds.`;
  return `Could not reach ${API_URL}. It may be down, or unreachable from here.`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch (cause) {
    // No response at all: DNS, TLS, CORS, offline, or the timeout above.
    throw new ApiError(networkMessage(cause), 0);
  }

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new ApiError(errorMessage(body, response), response.status);
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError("The API answered with something that is not JSON.", response.status);
  }
}

// --- accepted solutions -----------------------------------------------------
//
// `POST /get-accepted-solutions` with {"company_name": …} answers with one row
// per accepted solution:
//
//   [{ solution:   {id, name, url?, description},
//      conclusion: {id, batch, title, problem, savings_10y_chf, anchor, created_at} }]
//
// A conclusion with several accepted solutions therefore repeats across rows.
// The whole list is regrouped here -- by conclusion, then by scan -- so the
// components get the shape they actually render and never see the repetition.
//
// Only *accepted* solutions come back: a fix nobody took in VR is not in this
// answer at all.

export type Position = { x: number; y: number; z: number };

/** One accepted fix. `url` is unset for a behavioural one -- it is never invented. */
export type EntrySolution = {
  id: string | null;
  name: string;
  description: string | null;
  url: string | null;
};

/** One conclusion, with the solutions this company accepted for it. */
export type ConclusionEntry = {
  id: string | null;
  batch: string | null;
  createdAt: string | null;
  title: string;
  problem: string;
  solutions: EntrySolution[];
  /** The solutions that carry a link: the things there are to buy. */
  products: EntrySolution[];
  savings: { amount: number | null; basis: string | null };
  anchorLabel: string | null;
  position: Position | null;
};

/** One scan's worth of conclusions, keyed by the batch they came from. */
export type Scan = {
  batch: string;
  createdAt: string | null;
  entries: ConclusionEntry[];
};

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value : null;
}

/**
 * `savings_10y_chf` is the string "|amount|explanation". A bare number is
 * accepted too, and anything unreadable yields a null amount, which the list
 * shows as unknown rather than as "CHF NaN".
 */
function parseSavings(value: unknown): { amount: number | null; basis: string | null } {
  if (typeof value === "number" && Number.isFinite(value))
    return { amount: value, basis: null };

  if (typeof value === "string") {
    // [\s\S] rather than . with the s flag: the build targets ES2017.
    const piped = /^\s*\|\s*([\d'’.,\s]+)\s*\|\s*([\s\S]*)$/.exec(value);
    if (piped !== null) {
      const amount = Number(piped[1].replace(/[^\d.]/g, ""));
      return {
        amount: Number.isFinite(amount) ? amount : null,
        basis: asString(piped[2]),
      };
    }
    const bare = Number(value.replace(/[^\d.]/g, ""));
    if (Number.isFinite(bare) && value.trim() !== "")
      return { amount: bare, basis: null };
  }

  return { amount: null, basis: null };
}

function normaliseSolution(raw: unknown): EntrySolution {
  const solution = asRecord(raw);
  return {
    id: asString(solution.id),
    name: asString(solution.name) ?? "",
    description: asString(solution.description),
    url: asString(solution.url),
  };
}

function normalisePosition(raw: unknown): Position | null {
  const position = asRecord(raw);
  const coordinate = (key: "x" | "y" | "z") =>
    typeof position[key] === "number" ? (position[key] as number) : null;
  const [x, y, z] = [coordinate("x"), coordinate("y"), coordinate("z")];
  return x !== null && y !== null && z !== null ? { x, y, z } : null;
}

/** Collapse the repeated conclusions, keeping each one's accepted solutions together. */
function groupIntoEntries(rows: unknown): ConclusionEntry[] {
  if (!Array.isArray(rows)) return [];

  const byConclusion = new Map<string, ConclusionEntry>();

  for (const [index, raw] of rows.entries()) {
    const row = asRecord(raw);
    const conclusion = asRecord(row.conclusion);
    const solution = normaliseSolution(row.solution);
    // Without an id there is nothing to group on, so the row stands alone.
    const key = asString(conclusion.id) ?? `row-${index}`;

    let entry = byConclusion.get(key);
    if (entry === undefined) {
      const anchor = asRecord(conclusion.anchor);
      entry = {
        id: asString(conclusion.id),
        batch: asString(conclusion.batch),
        createdAt: asString(conclusion.created_at),
        title: asString(conclusion.title) ?? "Untitled",
        problem: asString(conclusion.problem) ?? "",
        solutions: [],
        products: [],
        savings: parseSavings(conclusion.savings_10y_chf),
        anchorLabel: asString(anchor.label),
        position: normalisePosition(anchor.position),
      };
      byConclusion.set(key, entry);
    }

    if (solution.name !== "") {
      entry.solutions.push(solution);
      if (solution.url !== null) entry.products.push(solution);
    }
  }

  return [...byConclusion.values()];
}

/** Group the conclusions by the scan they came out of, newest scan first. */
function groupIntoScans(entries: ConclusionEntry[]): Scan[] {
  const byBatch = new Map<string, Scan>();

  for (const entry of entries) {
    // A conclusion with no batch still belongs somewhere it can be opened.
    const batch = entry.batch ?? "unknown";
    let scan = byBatch.get(batch);
    if (scan === undefined) {
      scan = { batch, createdAt: entry.createdAt, entries: [] };
      byBatch.set(batch, scan);
    }
    scan.entries.push(entry);
    // The scan is as old as its earliest conclusion.
    if (
      scan.createdAt === null ||
      (entry.createdAt !== null && entry.createdAt < scan.createdAt)
    )
      scan.createdAt = entry.createdAt;
  }

  // Batch names are timestamps, so this sorts newest first either way.
  return [...byBatch.values()].sort((a, b) => b.batch.localeCompare(a.batch));
}

// --- endpoints --------------------------------------------------------------

export function listCompanies() {
  return request<Company[]>("/companies");
}

export function getCompany(name: string) {
  return request<Company>(`/companies/${encodeURIComponent(name)}`);
}

/** The company, or null if no company of that name exists yet. */
export async function findCompany(name: string): Promise<Company | null> {
  try {
    return await getCompany(name);
  } catch (cause) {
    if (cause instanceof ApiError && cause.status === 404) return null;
    throw cause;
  }
}

/** Creates the company if it is new, otherwise updates the fields given. */
export function saveCompany(company: {
  name: string;
  website?: string;
  details?: string;
}) {
  return request<Company>("/companies", {
    method: "POST",
    body: JSON.stringify(company),
  });
}

export function deleteCompany(name: string) {
  return request<{ status: string; name: string }>(
    `/companies/${encodeURIComponent(name)}`,
    { method: "DELETE" },
  );
}

/**
 * Every conclusion this company has accepted a solution for, grouped by scan.
 *
 * The company name is the whole payload: `{"company_name": …}`.
 */
export async function listScans(company: string): Promise<Scan[]> {
  const rows = await request<unknown>("/get-accepted-solutions", {
    method: "POST",
    body: JSON.stringify({ company_name: company }),
  });
  return groupIntoScans(groupIntoEntries(rows));
}

/** One scan's conclusions, or null if this company has none from that batch. */
export async function getScan(company: string, batch: string): Promise<Scan | null> {
  const scans = await listScans(company);
  return scans.find((scan) => scan.batch === batch) ?? null;
}

/** The signed-in company name, kept in the browser -- there are no passwords. */
const SESSION_KEY = "company-name";

const listeners = new Set<() => void>();

/** Subscribe to the session: other tabs via `storage`, this one via the setters. */
export function subscribeSession(listener: () => void) {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

export function readSession(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(SESSION_KEY);
  } catch {
    // Private windows and blocked site data throw rather than return null.
    return null;
  }
}

export function writeSession(name: string) {
  try {
    window.localStorage.setItem(SESSION_KEY, name);
  } catch {
    // Not being able to remember the choice is survivable; the view still works.
  }
  listeners.forEach((listener) => listener());
}

export function clearSession() {
  try {
    window.localStorage.removeItem(SESSION_KEY);
  } catch {
    // as above
  }
  listeners.forEach((listener) => listener());
}

/** Timestamps come back as ISO strings; show them readably. */
export function formatBatchDate(iso: string | null) {
  if (iso === null) return "unknown date";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/**
 * Savings as Swiss francs. Fixed to de-CH rather than the visitor's locale: the
 * number is francs whoever is reading it, and the apostrophe grouping is how it
 * is written here. Rappen are dropped -- these are ten-year estimates.
 */
const CHF = new Intl.NumberFormat("de-CH", {
  style: "currency",
  currency: "CHF",
  maximumFractionDigits: 0,
});

export function formatChf(amount: number | null) {
  return amount === null ? "Unknown" : CHF.format(amount);
}

/**
 * What a set of conclusions is worth. Null when none of them carried a usable
 * number, so the view can say so instead of showing a confident zero.
 */
export function totalSavings(entries: ConclusionEntry[]): number | null {
  const amounts = entries
    .map((entry) => entry.savings.amount)
    .filter((amount): amount is number => amount !== null);
  return amounts.length === 0 ? null : amounts.reduce((sum, amount) => sum + amount, 0);
}
