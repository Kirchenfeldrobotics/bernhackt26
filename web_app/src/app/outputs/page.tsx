"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import AppShell from "@/components/AppShell";
import {
  formatBatchDate,
  formatChf,
  listGeminiOutputs,
  totalSavings,
  type GeminiOutput,
} from "@/lib/api";

function OutputList() {
  const [outputs, setOutputs] = useState<GeminiOutput[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listGeminiOutputs()
      .then(setOutputs)
      .catch((cause) => setError(String(cause instanceof Error ? cause.message : cause)));
  }, []);

  if (error !== null)
    return <p className="text-body-sm leading-body-sm text-coral-red">{error}</p>;
  if (outputs === null)
    return <p className="text-body-sm leading-body-sm text-ash">Loading…</p>;

  return (
    <div>
      <h1 className="text-heading-sm leading-heading-sm tracking-heading-sm text-paper">
        Gemini outputs
      </h1>
      <p className="mt-3 text-body-sm leading-body-sm tracking-body-sm text-fog">
        {outputs.length === 0
          ? "No scans have been sent from the headset yet."
          : `${outputs.length} scan${outputs.length === 1 ? "" : "s"} stored on the server.`}
      </p>

      <ul className="mt-8 flex flex-col gap-2">
        {outputs.map((output) => (
          <li key={output.batch}>
            <Link
              href={`/outputs/${output.batch}`}
              className="block rounded-xl border border-graphite bg-carbon p-6 transition-colors hover:border-smoke"
            >
              <div className="flex flex-wrap items-center gap-3">
                <span className="text-body-lg leading-body-lg tracking-body-lg text-paper">
                  {formatBatchDate(output.created_at)}
                </span>
                {/* Batch stamps are technical metadata: monospaced, like an issue ID. */}
                <span className="rounded-[4px] bg-white/5 px-1.5 font-mono text-[12px] leading-[1.4] tracking-[-0.013em] text-fog">
                  {output.batch}
                </span>
                <span className="rounded-[4px] bg-white/5 px-1.5 text-[12px] leading-[1.4] text-fog">
                  {output.images} images
                </span>
                <span className="rounded-[4px] bg-white/5 px-1.5 text-[12px] leading-[1.4] text-fog">
                  {output.anchors} anchors
                </span>
                {output.conclusion !== null && (
                  <span className="rounded-[4px] bg-white/5 px-1.5 text-[12px] leading-[1.4] text-fog">
                    {output.conclusion.entries.length}{" "}
                    {output.conclusion.entries.length === 1 ? "fix" : "fixes"}
                  </span>
                )}
              </div>

              {/* What the scan is worth once it has been analysed; the raw
                  description is what there is to show until then. */}
              {output.conclusion !== null ? (
                <p className="mt-3 text-body-sm leading-body-sm tracking-body-sm text-fog">
                  <span className="text-paper">
                    {formatChf(totalSavings(output.conclusion))}
                  </span>{" "}
                  over ten years
                </p>
              ) : (
                <p className="mt-3 text-body-sm leading-body-sm tracking-body-sm text-ash">
                  Not analysed yet
                </p>
              )}

              <p className="mt-2 line-clamp-2 text-body-sm leading-body-sm tracking-body-sm text-ash">
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
