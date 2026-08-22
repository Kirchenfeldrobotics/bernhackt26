"use client";

import { useEffect, useState } from "react";

import AppShell from "@/components/AppShell";
import { getCompany, saveCompany } from "@/lib/api";

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
      .catch((cause) => setError(String(cause instanceof Error ? cause.message : cause)))
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
      setError(String(cause instanceof Error ? cause.message : cause));
    }
  }

  if (loading) return <p className="text-body text-mid-gray">Loading…</p>;

  return (
    <div className="max-w-2xl">
      <h1 className="text-heading font-semibold text-ink">Settings</h1>

      <form
        onSubmit={handleSubmit}
        className="mt-6 flex flex-col gap-5 rounded-3xl border border-hairline bg-paper p-5 shadow-card"
      >
        <div className="flex flex-col gap-2">
          <label htmlFor="name" className="text-caption font-medium uppercase text-mid-gray">
            Company name
          </label>
          {/* The name is the key every company row and prompt is looked up by,
              so it is shown but not editable here. */}
          <input
            id="name"
            type="text"
            value={company}
            disabled
            className="rounded-2xl bg-canvas px-3 py-2 text-body text-mid-gray"
          />
        </div>

        <div className="flex flex-col gap-2">
          <label htmlFor="website" className="text-caption font-medium uppercase text-mid-gray">
            Website
          </label>
          <input
            id="website"
            type="url"
            value={website}
            onChange={(event) => setWebsite(event.target.value)}
            placeholder="https://example.com"
            className="rounded-2xl bg-canvas px-3 py-2 text-body text-ink placeholder:text-mid-gray outline-none focus:ring-1 focus:ring-hairline"
          />
        </div>

        <div className="flex flex-col gap-2">
          <label htmlFor="details" className="text-caption font-medium uppercase text-mid-gray">
            Company description
          </label>
          <textarea
            id="details"
            value={details}
            onChange={(event) => setDetails(event.target.value)}
            rows={8}
            placeholder="What the company does, how it works day to day."
            className="resize-y rounded-2xl bg-canvas px-3 py-2 text-body text-ink placeholder:text-mid-gray outline-none focus:ring-1 focus:ring-hairline"
          />
        </div>

        <div className="flex items-center gap-3">
          <button
            type="submit"
            className="rounded-2xl bg-ink px-4 py-2 text-body font-medium text-surface-alt"
          >
            Save
          </button>
          {status !== null && <span className="text-body text-mid-gray">{status}</span>}
          {error !== null && <span className="text-body text-ember">{error}</span>}
        </div>
      </form>
    </div>
  );
}

export default function SettingsPage() {
  return <AppShell>{(company) => <SettingsForm company={company} />}</AppShell>;
}
