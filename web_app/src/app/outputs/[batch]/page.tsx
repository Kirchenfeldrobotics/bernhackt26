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

  if (error !== null) return <p className="text-body text-ember">{error}</p>;
  if (output === null) return <p className="text-body text-mid-gray">Loading…</p>;

  return (
    <div className="max-w-3xl">
      <Link href="/outputs" className="text-body text-mid-gray hover:text-ink">
        ← Outputs
      </Link>

      <h1 className="mt-4 text-heading font-semibold text-ink">
        {formatBatchDate(output.created_at)}
      </h1>
      <p className="mt-2 text-body text-mid-gray">
        <span className="font-mono">{output.batch}</span> · {output.images} images ·{" "}
        {output.anchors} anchors
      </p>

      <div className="mt-6 rounded-3xl border border-hairline bg-paper p-5 shadow-card">
        <p className="whitespace-pre-wrap text-body text-ink">{output.description}</p>
      </div>
    </div>
  );
}

export default function OutputPage() {
  const params = useParams<{ batch: string }>();
  return <AppShell>{() => <OutputDetail batch={params.batch} />}</AppShell>;
}
