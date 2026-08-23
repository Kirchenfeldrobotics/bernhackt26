"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import AppShell from "@/components/AppShell";
import ConclusionList, { ConclusionTotals } from "@/components/ConclusionList";
import { formatBatchDate, getScan, type Scan } from "@/lib/api";

const BODY = "text-body-sm leading-body-sm tracking-body-sm";

const MONO_BADGE =
  "rounded-[4px] bg-white/5 px-1.5 font-mono text-[12px] leading-[1.4] tracking-[-0.013em] text-fog";

function message(cause: unknown) {
  return String(cause instanceof Error ? cause.message : cause);
}

function ScanDetail({ batch, company }: { batch: string; company: string }) {
  const [scan, setScan] = useState<Scan | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getScan(company, batch)
      .then(setScan)
      .catch((cause) => setError(message(cause)));
  }, [batch, company]);

  if (error !== null) return <p className={`${BODY} text-coral-red`}>{error}</p>;
  if (scan === undefined) return <p className={`${BODY} text-ash`}>Loading…</p>;

  return (
    <div className="max-w-[820px]">
      <Link
        href="/outputs"
        className="text-caption leading-caption text-fog transition-colors hover:text-mist"
      >
        ← Accepted solutions
      </Link>

      {scan === null ? (
        <>
          <h1 className="mt-6 text-heading-sm leading-heading-sm tracking-heading-sm text-paper">
            Nothing accepted
          </h1>
          <p className={`mt-3 ${BODY} text-fog`}>
            {company} has accepted nothing from scan{" "}
            <span className={MONO_BADGE}>{batch}</span>. Solutions are accepted in the
            headset, and appear here once they are.
          </p>
        </>
      ) : (
        <>
          <h1 className="mt-6 text-heading-sm leading-heading-sm tracking-heading-sm text-paper">
            {formatBatchDate(scan.createdAt)}
          </h1>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className={MONO_BADGE}>{scan.batch}</span>
          </div>

          <section className="mt-12">
            <h2 className="text-eyebrow leading-eyebrow tracking-eyebrow uppercase text-ash">
              Accepted for {company}
            </h2>
            <div className="mt-2">
              <ConclusionTotals entries={scan.entries} />
            </div>

            <div className="mt-6">
              <ConclusionList entries={scan.entries} />
            </div>
          </section>
        </>
      )}
    </div>
  );
}

export default function OutputPage() {
  const params = useParams<{ batch: string }>();
  return (
    <AppShell>
      {(company) => <ScanDetail batch={params.batch} company={company} />}
    </AppShell>
  );
}
