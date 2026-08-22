"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { readSession, saveCompany, writeSession } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (readSession() !== null) router.replace("/outputs");
  }, [router]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      // There is no password: naming the company signs you in, and creates it
      // on the server the first time.
      const company = await saveCompany({ name: name.trim() });
      writeSession(company.name);
      router.replace("/outputs");
    } catch (cause) {
      setError(String(cause instanceof Error ? cause.message : cause));
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-1 items-center justify-center px-6 py-12">
      <div className="w-full max-w-md rounded-3xl border border-hairline bg-paper p-5 shadow-card">
        <h1 className="text-heading-sm font-semibold text-ink">Sign in</h1>
        <p className="mt-2 text-body text-mid-gray">
          Enter your company name. No password needed.
        </p>

        <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-2">
          <label htmlFor="name" className="text-caption font-medium uppercase text-mid-gray">
            Company name
          </label>
          <input
            id="name"
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
            autoFocus
            placeholder="Beispiel AG"
            className="rounded-2xl bg-canvas px-3 py-2 text-body text-ink placeholder:text-mid-gray outline-none focus:ring-1 focus:ring-hairline"
          />
          <button
            type="submit"
            disabled={busy || name.trim() === ""}
            className="mt-2 rounded-2xl bg-ink px-4 py-2 text-body font-medium text-surface-alt transition-opacity disabled:opacity-40"
          >
            {busy ? "Signing in…" : "Continue"}
          </button>
        </form>

        {error !== null && <p className="mt-4 text-body text-ember">{error}</p>}
      </div>
    </div>
  );
}
