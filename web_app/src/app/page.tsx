"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  findCompany,
  listCompanies,
  readSession,
  saveCompany,
  writeSession,
  type Company,
} from "@/lib/api";

function message(cause: unknown) {
  return String(cause instanceof Error ? cause.message : cause);
}

export default function StartPage() {
  const router = useRouter();
  const [companies, setCompanies] = useState<Company[] | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (readSession() !== null) {
      router.replace("/outputs");
      return;
    }
    listCompanies().then(setCompanies).catch((cause) => setError(message(cause)));
  }, [router]);

  function signIn(company: string) {
    writeSession(company);
    router.replace("/outputs");
  }

  async function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const wanted = name.trim();
    setError(null);
    setBusy(true);
    try {
      // POST /companies is an upsert, so it would silently sign you in to an
      // existing company instead of creating one. Check the name first.
      if ((await findCompany(wanted)) !== null) {
        setError(`${wanted} already exists — choose it from the list.`);
        setBusy(false);
        return;
      }
      const created = await saveCompany({ name: wanted });
      signIn(created.name);
    } catch (cause) {
      setError(message(cause));
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-1 items-center justify-center px-6 py-12">
      <div className="w-full max-w-md rounded-3xl border border-hairline bg-paper p-5 shadow-card">
        <h1 className="text-heading-sm font-semibold text-ink">Choose your company</h1>
        <p className="mt-2 text-body text-mid-gray">
          No password needed. Pick a company, or create a new one.
        </p>

        {companies === null ? (
          <p className="mt-6 text-body text-mid-gray">Loading…</p>
        ) : companies.length === 0 ? (
          <p className="mt-6 text-body text-mid-gray">
            No companies yet. Create the first one below.
          </p>
        ) : (
          <ul className="mt-6 flex max-h-64 flex-col gap-1 overflow-y-auto">
            {companies.map((company) => (
              <li key={company.id}>
                <button
                  type="button"
                  onClick={() => signIn(company.name)}
                  className="w-full rounded-2xl px-3 py-2 text-left text-body text-ink transition-colors hover:bg-canvas"
                >
                  {company.name}
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="my-5 flex items-center gap-3">
          <span className="h-px flex-1 bg-hairline" />
          <span className="text-caption uppercase text-mid-gray">or</span>
          <span className="h-px flex-1 bg-hairline" />
        </div>

        <form onSubmit={handleCreate} className="flex flex-col gap-2">
          <label htmlFor="name" className="text-caption font-medium uppercase text-mid-gray">
            New company
          </label>
          <div className="flex gap-2">
            <input
              id="name"
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
              placeholder="Beispiel AG"
              className="min-w-0 flex-1 rounded-2xl bg-canvas px-3 py-2 text-body text-ink placeholder:text-mid-gray outline-none focus:ring-1 focus:ring-hairline"
            />
            <button
              type="submit"
              disabled={busy || name.trim() === ""}
              className="shrink-0 rounded-2xl bg-ink px-4 py-2 text-body font-medium text-surface-alt transition-opacity disabled:opacity-40"
            >
              {busy ? "Creating…" : "Create"}
            </button>
          </div>
        </form>

        {error !== null && <p className="mt-4 text-body text-ember">{error}</p>}
      </div>
    </div>
  );
}
