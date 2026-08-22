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
    <div className="flex flex-1 items-center justify-center px-6 py-16">
      <div className="w-full max-w-[420px] rounded-xl border border-graphite bg-carbon p-6">
        <h1 className="text-subheading leading-subheading tracking-subheading text-paper">
          Choose your company
        </h1>
        <p className="mt-2 text-body-sm leading-body-sm tracking-body-sm text-fog">
          No password needed. Pick a company, or create a new one.
        </p>

        {companies === null ? (
          <p className="mt-6 text-body-sm leading-body-sm text-ash">Loading…</p>
        ) : companies.length === 0 ? (
          <p className="mt-6 text-body-sm leading-body-sm text-ash">
            No companies yet. Create the first one below.
          </p>
        ) : (
          <ul className="mt-6 flex max-h-[260px] flex-col gap-1 overflow-y-auto">
            {companies.map((company) => (
              <li key={company.id}>
                <button
                  type="button"
                  onClick={() => signIn(company.name)}
                  className="w-full rounded-md px-3 py-2 text-left text-body-sm leading-body-sm tracking-body-sm text-mist transition-colors hover:bg-white/5 hover:text-paper"
                >
                  {company.name}
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="my-6 flex items-center gap-3">
          <span className="h-px flex-1 bg-graphite" />
          <span className="text-[12px] leading-[1.4] text-ash">or</span>
          <span className="h-px flex-1 bg-graphite" />
        </div>

        <form onSubmit={handleCreate} className="flex flex-col gap-2">
          <label htmlFor="name" className="text-[12px] leading-[1.4] text-fog">
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
              className="min-w-0 flex-1 rounded-md border border-white/[0.08] bg-white/[0.02] px-3.5 py-3 text-[14px] leading-[1.4] text-mist placeholder:text-ash outline-none transition-colors focus:border-mist"
            />
            {/* The one chromatic element on this view. */}
            <button
              type="submit"
              disabled={busy || name.trim() === ""}
              className="shrink-0 rounded-md bg-acid-lime px-4 py-2.5 text-[14px] font-[510] tracking-[-0.011em] text-void transition-opacity disabled:opacity-40"
            >
              {busy ? "Creating…" : "Create"}
            </button>
          </div>
        </form>

        {error !== null && (
          <p className="mt-4 text-body-sm leading-body-sm text-coral-red">{error}</p>
        )}
      </div>
    </div>
  );
}
