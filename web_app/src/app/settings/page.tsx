"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import AppShell from "@/components/AppShell";
import { clearSession, deleteCompany, getCompany, saveCompany } from "@/lib/api";

const FIELD =
  "rounded-md border border-white/[0.08] bg-white/[0.02] px-3.5 py-3 text-[14px] leading-[1.5] text-mist placeholder:text-ash outline-none transition-colors focus:border-mist";

const LABEL = "text-[12px] leading-[1.4] text-fog";

const GHOST =
  "rounded-md border border-graphite px-3 py-2 text-caption leading-caption transition-colors";

function message(cause: unknown) {
  return String(cause instanceof Error ? cause.message : cause);
}

function SettingsForm({ company }: { company: string }) {
  const [website, setWebsite] = useState("");
  const [details, setDetails] = useState("");
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCompany(company)
      .then((row) => {
        setWebsite(row.website ?? "");
        setDetails(row.details ?? "");
      })
      .catch((cause) => setError(message(cause)))
      .finally(() => setLoading(false));
  }, [company]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus(null);
    setError(null);
    try {
      await saveCompany({ name: company, website: website.trim(), details: details.trim() });
      setStatus("Saved");
    } catch (cause) {
      setError(message(cause));
    }
  }

  if (loading) return <p className="text-body-sm leading-body-sm text-ash">Loading…</p>;

  return (
    <form
      onSubmit={handleSubmit}
      className="mt-8 flex flex-col gap-6 rounded-xl border border-graphite bg-carbon p-6"
    >
      <div className="flex flex-col gap-2">
        <label htmlFor="name" className={LABEL}>
          Company name
        </label>
        {/* The name is the key every company row and prompt is looked up by,
            so it is shown but not editable here. */}
        <input id="name" type="text" value={company} disabled className={`${FIELD} text-ash`} />
      </div>

      <div className="flex flex-col gap-2">
        <label htmlFor="website" className={LABEL}>
          Website
        </label>
        <input
          id="website"
          type="url"
          value={website}
          onChange={(event) => setWebsite(event.target.value)}
          placeholder="https://example.com"
          className={FIELD}
        />
      </div>

      <div className="flex flex-col gap-2">
        <label htmlFor="details" className={LABEL}>
          Company description
        </label>
        <textarea
          id="details"
          value={details}
          onChange={(event) => setDetails(event.target.value)}
          rows={8}
          placeholder="What the company does, how it works day to day."
          className={`${FIELD} resize-y`}
        />
      </div>

      <div className="flex items-center gap-4">
        {/* The one chromatic element on this view. */}
        <button
          type="submit"
          className="rounded-md bg-acid-lime px-4 py-2.5 text-[14px] font-[510] tracking-[-0.011em] text-void"
        >
          Save
        </button>
        {status !== null && (
          <span className="text-body-sm leading-body-sm text-fog">{status}</span>
        )}
        {error !== null && (
          <span className="text-body-sm leading-body-sm text-coral-red">{error}</span>
        )}
      </div>
    </form>
  );
}

function DeleteCompany({ company }: { company: string }) {
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete() {
    setError(null);
    setBusy(true);
    try {
      await deleteCompany(company);
      // The signed-in company no longer exists, so the session cannot stand.
      clearSession();
      router.replace("/");
    } catch (cause) {
      setError(message(cause));
      setBusy(false);
    }
  }

  return (
    <section className="mt-6 rounded-xl border border-graphite bg-carbon p-6">
      <h2 className="text-[16px] font-[510] leading-[1.4] tracking-[-0.01em] text-paper">
        Delete company
      </h2>
      <p className="mt-2 text-body-sm leading-body-sm tracking-body-sm text-fog">
        Removes {company} along with its website and description, and signs you out. The
        scans stored on the server are kept — they are not tied to a company. This cannot
        be undone.
      </p>

      {confirming ? (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={handleDelete}
            disabled={busy}
            className={`${GHOST} border-coral-red/40 text-coral-red hover:bg-coral-red/10 disabled:opacity-40`}
          >
            {busy ? "Deleting…" : `Yes, delete ${company}`}
          </button>
          <button
            type="button"
            onClick={() => setConfirming(false)}
            disabled={busy}
            className={`${GHOST} text-mist hover:bg-white/5 disabled:opacity-40`}
          >
            Cancel
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setConfirming(true)}
          className={`${GHOST} mt-4 text-coral-red hover:border-coral-red/40`}
        >
          Delete company
        </button>
      )}

      {error !== null && (
        <p className="mt-4 text-body-sm leading-body-sm text-coral-red">{error}</p>
      )}
    </section>
  );
}

export default function SettingsPage() {
  return (
    <AppShell>
      {(company) => (
        <div className="max-w-[640px]">
          <h1 className="text-heading-sm leading-heading-sm tracking-heading-sm text-paper">
            Settings
          </h1>
          <SettingsForm company={company} />
          <DeleteCompany company={company} />
        </div>
      )}
    </AppShell>
  );
}
