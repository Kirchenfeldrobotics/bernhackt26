/**
 * The API, reached through this app's own origin. `next.config.ts` forwards
 * /backend to wherever the server actually runs.
 *
 * Going through our own origin rather than naming the API host here is what
 * makes the app work off localhost at all: the API only allows CORS from
 * localhost:3000, so a browser anywhere else is refused before the request is
 * even sent. Same-origin requests are not subject to that.
 *
 * The prefix is "/backend" rather than "/api" because the nginx vhost in front
 * of this app keeps "/api" for itself; see the note in `next.config.ts`.
 *
 * Set NEXT_PUBLIC_API_URL to call a server directly instead -- useful against a
 * local one that allows your origin.
 */
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "/backend";

// Naming "/backend" in an error message tells nobody anything.
const API_LABEL = API_URL.startsWith("/") ? "the API" : API_URL;

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

// --- the conclusion ---------------------------------------------------------
//
// Two server generations describe a conclusion differently, and the web app
// must not care which one answered:
//
//   older: solutions: string[]        products: {name,url}[] | null
//          savings_10y_chf: number    anchor_label + position
//   newer: solutions: {name,url,description}[]
//          savings_10y_chf: "|amount|explanation"
//          anchor: {label, position}
//
// Both are normalised into the shapes below at the edge, so exactly one shape
// reaches the components.

export type Position = { x: number; y: number; z: number };

/** One fix, and the product link behind it when there is one. */
export type EntrySolution = {
  name: string;
  description: string | null;
  /** Null whenever no product was sourced -- never a guessed URL. */
  url: string | null;
};

/** One conclusion entry, in the five parts the list renders. */
export type ConclusionEntry = {
  title: string;
  problem: string;
  solutions: EntrySolution[];
  /**
   * What to buy, kept separate from the solutions so a product keeps its own
   * name. Null means nothing was sourced; an empty list means the fixes here
   * genuinely need no purchase.
   */
  products: EntrySolution[] | null;
  savings: { amount: number | null; basis: string | null };
  benefit: string | null;
  anchorLabel: string | null;
  position: Position | null;
  placementReasoning: string | null;
};

export type Conclusion = {
  company: string | null;
  created_at: string | null;
  problems: string | null;
  entries: ConclusionEntry[];
};

/** One Gemini answer stored on the server by `/receive-data`. */
export type GeminiOutput = {
  batch: string;
  created_at: string;
  images: number;
  anchors: number;
  description: string;
  /**
   * Servers without a stored conclusion omit the field entirely rather than
   * sending null, so this is normalised to null on the way in and every reader
   * can rely on it being present.
   */
  conclusion: Conclusion | null;
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
    return `${API_LABEL} did not answer within ${TIMEOUT_MS / 1000} seconds.`;
  return `Could not reach ${API_LABEL}. It may be down, or unreachable from here.`;
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

// --- normalising a conclusion ----------------------------------------------

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value : null;
}

/**
 * Savings arrive either as a number, or as the newer "|amount|explanation"
 * string. Anything else yields a null amount, which the list shows as unknown
 * rather than as "CHF NaN".
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

/**
 * Solutions are either plain strings with the products listed separately, or
 * objects that already carry their own product link.
 *
 * The two are never zipped together by position: that pairing is invented, and
 * it costs a product its own name. Whichever shape arrived, a product keeps the
 * name the server gave it.
 */
function normaliseFixes(raw: Record<string, unknown>): {
  solutions: EntrySolution[];
  products: EntrySolution[] | null;
} {
  const rawSolutions = Array.isArray(raw.solutions) ? raw.solutions : [];

  const solutions = rawSolutions
    .map((solution): EntrySolution => {
      if (typeof solution === "string")
        return { name: solution, description: null, url: null };
      const record = asRecord(solution);
      return {
        name: asString(record.name) ?? "",
        description: asString(record.description),
        url: asString(record.url),
      };
    })
    .filter((solution) => solution.name !== "");

  // Older shape: products are their own list, and its absence means unsourced.
  if (Array.isArray(raw.products)) {
    const products = raw.products
      .map((product): EntrySolution => {
        const record = asRecord(product);
        return {
          name: asString(record.name) ?? "",
          description: asString(record.description),
          url: asString(record.url),
        };
      })
      .filter((product) => product.name !== "");
    return { solutions, products };
  }
  if (raw.products === null) return { solutions, products: null };

  // Newer shape: a solution carrying a link is itself the product. None
  // carrying one is a real answer -- every fix here is behavioural.
  return { solutions, products: solutions.filter((solution) => solution.url !== null) };
}

function normaliseEntry(raw: unknown): ConclusionEntry {
  const entry = asRecord(raw);
  const anchor = asRecord(entry.anchor);
  const position = asRecord(entry.position ?? anchor.position);

  const coordinate = (key: "x" | "y" | "z") =>
    typeof position[key] === "number" ? (position[key] as number) : null;
  const [x, y, z] = [coordinate("x"), coordinate("y"), coordinate("z")];

  const { solutions, products } = normaliseFixes(entry);
  // The newer shape folds the explanation into the amount string; the older one
  // keeps it in its own field.
  const savings = parseSavings(entry.savings_10y_chf);

  return {
    title: asString(entry.title) ?? "Untitled",
    problem: asString(entry.problem) ?? "",
    solutions,
    products,
    savings: {
      amount: savings.amount,
      basis: savings.basis ?? asString(entry.savings_basis),
    },
    benefit: asString(entry.benefit),
    anchorLabel: asString(entry.anchor_label) ?? asString(anchor.label),
    position: x !== null && y !== null && z !== null ? { x, y, z } : null,
    placementReasoning: asString(entry.placement_reasoning),
  };
}

/** Absent, null, or a conclusion in either server's shape. */
function normaliseConclusion(raw: unknown): Conclusion | null {
  if (raw === null || raw === undefined) return null;

  const conclusion = asRecord(raw);
  // Older servers key the list "entries", newer ones "conclusions".
  const list = Array.isArray(conclusion.entries)
    ? conclusion.entries
    : Array.isArray(conclusion.conclusions)
      ? conclusion.conclusions
      : [];

  return {
    company: asString(conclusion.company) ?? asString(conclusion.company_name),
    created_at: asString(conclusion.created_at),
    problems: asString(conclusion.problems),
    entries: list.map(normaliseEntry),
  };
}

function normaliseOutput(raw: GeminiOutput): GeminiOutput {
  return {
    ...raw,
    description: typeof raw.description === "string" ? raw.description : "",
    conclusion: normaliseConclusion((raw as { conclusion?: unknown }).conclusion),
  };
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

export async function listGeminiOutputs() {
  const outputs = await request<GeminiOutput[]>("/gemini-outputs");
  return outputs.map(normaliseOutput);
}

export async function getGeminiOutput(batch: string) {
  return normaliseOutput(
    await request<GeminiOutput>(`/gemini-outputs/${encodeURIComponent(batch)}`),
  );
}

/** Raised when the server has no analysis endpoint at all, rather than failing one. */
export class ConclusionUnsupported extends Error {
  constructor() {
    super(
      "This server does not offer the analysis endpoint yet, so a conclusion " +
        "cannot be produced from here.",
    );
    this.name = "ConclusionUnsupported";
  }
}

/**
 * Run the analysis over a stored scan: problems first, then the solutions they
 * lead to. Slow -- several model calls -- and not every server offers it.
 */
export async function runConclusion(batch: string, company: string) {
  try {
    const raw = await request<unknown>(
      `/gemini-outputs/${encodeURIComponent(batch)}/conclusion`,
      { method: "POST", body: JSON.stringify({ company, company_name: company }) },
    );
    return normaliseConclusion(raw);
  } catch (cause) {
    if (cause instanceof ApiError && (cause.status === 404 || cause.status === 405))
      throw new ConclusionUnsupported();
    throw cause;
  }
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

/** Batch timestamps come back as ISO strings; show them readably. */
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
 * What the whole conclusion is worth. Null when no entry carried a usable
 * number, so the view can say so instead of showing a confident zero.
 */
export function totalSavings(conclusion: Conclusion): number | null {
  const amounts = conclusion.entries
    .map((entry) => entry.savings.amount)
    .filter((amount): amount is number => amount !== null);
  return amounts.length === 0 ? null : amounts.reduce((sum, amount) => sum + amount, 0);
}
