"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import AppShell from "@/components/AppShell";
import { formatBatchDate, getGeminiOutput, type GeminiOutput } from "@/lib/api";

function OutputDetail({ batch }: { batch: string }) {
  const [output, setOutput] = useState<GeminiOutput | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getGeminiOutput(batch)
      .then(setOutput)
      .catch((cause) => setError(String(cause instanceof Error ? cause.message : cause)));
  }, [batch]);

  if (error !== null)
    return <p className="text-body-sm leading-body-sm text-coral-red">{error}</p>;
  if (output === null)
    return <p className="text-body-sm leading-body-sm text-ash">Loading…</p>;

  return (
    <div className="max-w-[820px]">
      <Link
        href="/outputs"
        className="text-caption leading-caption text-fog transition-colors hover:text-mist"
      >
        ← Outputs
      </Link>

      <h1 className="mt-6 text-heading-sm leading-heading-sm tracking-heading-sm text-paper">
        {formatBatchDate(output.created_at)}
      </h1>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="rounded-[4px] bg-white/5 px-1.5 font-mono text-[12px] leading-[1.4] tracking-[-0.013em] text-fog">
          {output.batch}
        </span>
        <span className="rounded-[4px] bg-white/5 px-1.5 text-[12px] leading-[1.4] text-fog">
          {output.images} images
        </span>
        <span className="rounded-[4px] bg-white/5 px-1.5 text-[12px] leading-[1.4] text-fog">
          {output.anchors} anchors
        </span>
      </div>

      <div className="mt-8 rounded-xl border border-graphite bg-carbon p-6">
        <p className="whitespace-pre-wrap text-body-sm leading-body-sm tracking-body-sm text-mist">
          {output.description}
        </p>
      </div>
    </div>
  );
}

export default function OutputPage() {
  const params = useParams<{ batch: string }>();
  return <AppShell>{() => <OutputDetail batch={params.batch} />}</AppShell>;
}
