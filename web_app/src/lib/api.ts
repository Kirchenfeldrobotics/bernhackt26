// The deployed server. Point NEXT_PUBLIC_API_URL at http://localhost:8000 in
// .env.local to develop against a local one instead.
export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "https://bernhackt26.kirchenfeldrobotics.ch";

/** A row of the `companies` table, as `/companies` returns it. */
export type Company = {
  id: string;
  name: string;
  website: string | null;
  details: string | null;
  created_at: string;
};

/** `Product` in `server/solutions.py`: something to buy, and where to buy it. */
export type Product = {
  name: string;
  url: string;
};

/** `Position` in `server/solutions.py`: metres, in the MRUK anchors' space. */
export type Position = {
  x: number;
  y: number;
  z: number;
};

/**
 * `ConclusionEntry` in `server/solutions.py`: one fix, with everything the
 * list shows about it.
 *
 * The five parts the entry is read in, in order: `title`, `problem` (the
 * negative impact), `solutions` (how to fix it), `products` (what to buy) and
 * `savings_10y_chf` (what it earns). `products` is null on every entry the
 * server writes today — Gemini has no catalogue, so the field waits for a real
 * product source instead of being filled with invented shop URLs.
 */
export type ConclusionEntry = {
  title: string;
  problem: string;
  solutions: string[];
  benefit: string;
  savings_10y_chf: number;
  savings_basis: string;
  anchor_label: string;
  position: Position;
  placement_reasoning: string;
  products: Product[] | null;
};

/** `StoredConclusion` in `server/main.py`: one batch's finished analysis. */
export type Conclusion = {
  company: string;
  created_at: string;
  problems: string;
  entries: ConclusionEntry[];
};

/** One Gemini answer stored on the server by `/receive-data`. */
export type GeminiOutput = {
  batch: string;
  created_at: string;
  images: number;
  anchors: number;
  description: string;
  /** Null until the analysis has been run for this batch. */
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

/** FastAPI reports failures as {"detail": ...}; show that rather than raw JSON. */
function errorMessage(body: string, response: Response): string {
  try {
    const detail = JSON.parse(body).detail;
    if (typeof detail === "string") return detail;
    if (detail !== undefined) return JSON.stringify(detail);
  } catch {
    // not JSON; fall through to the body itself
  }
  return body || `${response.status} ${response.statusText}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    throw new ApiError(errorMessage(await response.text(), response), response.status);
  }
  return response.json() as Promise<T>;
}

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

export function listGeminiOutputs() {
  return request<GeminiOutput[]>("/gemini-outputs");
}

export function getGeminiOutput(batch: string) {
  return request<GeminiOutput>(`/gemini-outputs/${encodeURIComponent(batch)}`);
}

/** The stored conclusion for a batch, or null if it has not been run yet. */
export async function findConclusion(batch: string): Promise<Conclusion | null> {
  try {
    return await request<Conclusion>(
      `/gemini-outputs/${encodeURIComponent(batch)}/conclusion`,
    );
  } catch (cause) {
    if (cause instanceof ApiError && cause.status === 404) return null;
    throw cause;
  }
}

/**
 * Run the analysis over a stored scan: problems first, then the solutions they
 * lead to. Slow — two Gemini calls — and replaces whatever was concluded before.
 */
export function runConclusion(batch: string, company: string) {
  return request<Conclusion>(
    `/gemini-outputs/${encodeURIComponent(batch)}/conclusion`,
    { method: "POST", body: JSON.stringify({ company }) },
  );
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
  return window.localStorage.getItem(SESSION_KEY);
}

export function writeSession(name: string) {
  window.localStorage.setItem(SESSION_KEY, name);
  listeners.forEach((listener) => listener());
}

export function clearSession() {
  window.localStorage.removeItem(SESSION_KEY);
  listeners.forEach((listener) => listener());
}

/** Batch timestamps come back as ISO strings; show them readably. */
export function formatBatchDate(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

/**
 * Savings as Swiss francs. Fixed to de-CH rather than the visitor's locale: the
 * number is francs whoever is reading it, and the apostrophe grouping is how it
 * is written here. Rappen are dropped — these are ten-year estimates.
 */
const CHF = new Intl.NumberFormat("de-CH", {
  style: "currency",
  currency: "CHF",
  maximumFractionDigits: 0,
});

export function formatChf(amount: number) {
  return CHF.format(amount);
}

/** What the whole conclusion is worth: every entry's ten-year saving added up. */
export function totalSavings(conclusion: Conclusion) {
  return conclusion.entries.reduce((sum, entry) => sum + entry.savings_10y_chf, 0);
}
