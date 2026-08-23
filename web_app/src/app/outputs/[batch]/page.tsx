"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import AppShell from "@/components/AppShell";
import ConclusionList, { ConclusionTotals } from "@/components/ConclusionList";
import Markdown from "@/components/Markdown";
import {
  formatBatchDate,
  getGeminiOutput,
  runConclusion,
  type Conclusion,
  type GeminiOutput,
} from "@/lib/api";

const BADGE =
  "rounded-[4px] bg-white/5 px-1.5 text-[12px] leading-[1.4] text-fog";

const MONO_BADGE = `${BADGE} font-mono tracking-[-0.013em]`;

const GHOST =
  "rounded-md border border-graphite px-3 py-2 text-caption leading-caption text-mist transition-colors hover:bg-white/5 disabled:opacity-40";

// The one chromatic element this view is allowed.
const PRIMARY =
  "rounded-md bg-acid-lime px-4 py-2.5 text-[14px] font-[510] tracking-[-0.011em] text-void transition-opacity disabled:opacity-40";

function message(cause: unknown) {
  return String(cause instanceof Error ? cause.message : cause);
}

/**
 * The conclusion for one scan: the five-part list of fixes, the problems it was
 * derived from, and the button that produces both.
 */
function ConclusionPanel({
  batch,
  company,
  initial,
}: {
  batch: string;
  company: string;
  initial: Conclusion | null;
}) {
  const [conclusion, setConclusion] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setError(null);
    setBusy(true);
    try {
      setConclusion(await runConclusion(batch, company));
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  }

  if (conclusion === null)
    return (
      <section className="mt-8 rounded-xl border border-graphite bg-carbon p-6">
        <h2 className="text-[16px] font-[510] leading-[1.4] tracking-[-0.01em] text-paper">
          Conclusion
        </h2>
        <p className="mt-2 text-body-sm leading-body-sm tracking-body-sm text-fog">
          This scan has not been analysed yet. Running the analysis reads the room
          description together with {company}&rsquo;s own description, names the
          problems it finds, and turns each one into a fix with a price on it.
        </p>
        <button type="button" onClick={run} disabled={busy} className={`${PRIMARY} mt-4`}>
          {busy ? "Analysing…" : "Run analysis"}
        </button>
        {busy && (
          <p className="mt-3 text-body-sm leading-body-sm text-ash">
            Two model calls, so this takes a moment.
          </p>
        )}
        {error !== null && (
          <p className="mt-3 text-body-sm leading-body-sm text-coral-red">{error}</p>
        )}
      </section>
    );

  return (
    <section className="mt-12">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-eyebrow leading-eyebrow tracking-eyebrow uppercase text-ash">
            Conclusion
          </h2>
          <div className="mt-2">
            <ConclusionTotals conclusion={conclusion} />
          </div>
          <p className="mt-2 text-caption leading-caption text-ash">
            Analysed for {conclusion.company} on{" "}
            {formatBatchDate(conclusion.created_at)}
          </p>
        </div>

        <button type="button" onClick={run} disabled={busy} className={GHOST}>
          {busy ? "Analysing…" : "Re-run analysis"}
        </button>
      </div>

      {error !== null && (
        <p className="mt-3 text-body-sm leading-body-sm text-coral-red">{error}</p>
      )}

      <div className="mt-6">
        <ConclusionList conclusion={conclusion} />
      </div>

      {/* The problems step 1 found, kept verbatim. Folded away by default: the
          fixes above are the answer, this is the working behind them. */}
      <details className="mt-2 rounded-xl border border-graphite bg-carbon p-6">
        <summary className="cursor-pointer list-none text-caption leading-caption text-fog transition-colors hover:text-mist">
          Problems this was derived from
        </summary>
        <Markdown source={conclusion.problems} className="mt-4" />
      </details>
    </section>
  );
}

function OutputDetail({ batch, company }: { batch: string; company: string }) {
  const [output, setOutput] = useState<GeminiOutput | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getGeminiOutput(batch)
      .then(setOutput)
      .catch((cause) => setError(message(cause)));
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
        <span className={MONO_BADGE}>{output.batch}</span>
        <span className={BADGE}>{output.images} images</span>
        <span className={BADGE}>{output.anchors} anchors</span>
      </div>

      <ConclusionPanel batch={batch} company={company} initial={output.conclusion} />

      <section className="mt-12">
        <h2 className="text-eyebrow leading-eyebrow tracking-eyebrow uppercase text-ash">
          Room description
        </h2>
        <div className="mt-4 rounded-xl border border-graphite bg-carbon p-6">
          <Markdown source={output.description} />
        </div>
      </section>
    </div>
  );
}

export default function OutputPage() {
  const params = useParams<{ batch: string }>();
  return (
    <AppShell>
      {(company) => <OutputDetail batch={params.batch} company={company} />}
    </AppShell>
  );
}
