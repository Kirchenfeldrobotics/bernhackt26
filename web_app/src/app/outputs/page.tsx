"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import AppShell from "@/components/AppShell";
import { formatBatchDate, listGeminiOutputs, type GeminiOutput } from "@/lib/api";

function OutputList() {
  const [outputs, setOutputs] = useState<GeminiOutput[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listGeminiOutputs()
      .then(setOutputs)
      .catch((cause) => setError(String(cause instanceof Error ? cause.message : cause)));
  }, []);

  if (error !== null) return <p className="text-body text-ember">{error}</p>;
  if (outputs === null) return <p className="text-body text-mid-gray">Loading…</p>;

  return (
    <div>
      <h1 className="text-heading font-semibold text-ink">Gemini outputs</h1>
      <p className="mt-2 text-body text-mid-gray">
        {outputs.length === 0
          ? "No scans have been sent from the headset yet."
          : `${outputs.length} scan${outputs.length === 1 ? "" : "s"} stored on the server.`}
      </p>

      <ul className="mt-6 flex flex-col gap-3">
        {outputs.map((output) => (
          <li key={output.batch}>
            <Link
              href={`/outputs/${output.batch}`}
              className="block rounded-3xl border border-hairline bg-paper p-5 shadow-card transition-colors hover:border-mid-gray"
            >
              <div className="flex flex-wrap items-baseline gap-3">
                <span className="text-body-lg font-medium text-ink">
                  {formatBatchDate(output.created_at)}
                </span>
                <span className="rounded-2xl bg-canvas px-2 py-0.5 font-mono text-caption text-ink-soft">
                  {output.batch}
                </span>
                <span className="text-caption text-mid-gray">
                  {output.images} images · {output.anchors} anchors
                </span>
              </div>
              <p className="mt-2 line-clamp-2 text-body text-mid-gray">
                {output.description}
              </p>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function OutputsPage() {
  return <AppShell>{() => <OutputList />}</AppShell>;
}
