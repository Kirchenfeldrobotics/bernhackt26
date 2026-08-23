"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import AppShell from "@/components/AppShell";
import ConclusionList, { ConclusionTotals } from "@/components/ConclusionList";
import { formatBatchDate, getScan, type Scan } from "@/lib/api";

const BODY = "text-body-sm leading-body-sm tracking-body-sm text-paper";

const HEADING = "text-heading-sm leading-heading-sm tracking-heading-sm text-paper";

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

  if (error !== null) return <p className={BODY}>{error}</p>;
  if (scan === undefined) return <p className={BODY}>Loading…</p>;

  // The scan's own heading is the first conclusion's title. A batch stamp is an
  // id, and a date is not what the scan is about.
  const title = scan?.entries[0]?.title ?? null;
  // With one conclusion the card would only repeat the heading above it.
  const several = (scan?.entries.length ?? 0) > 1;

  return (
    <div className="max-w-[820px]">
      <Link
        href="/outputs"
        className="text-caption leading-caption text-paper transition-opacity hover:opacity-70"
      >
        ← Accepted solutions
      </Link>

      {scan === null || title === null ? (
        <>
          <h1 className={`mt-6 ${HEADING}`}>Nothing accepted</h1>
          <p className={`mt-3 ${BODY}`}>
            {company} has accepted nothing from this scan. Solutions are accepted in
            the headset, and appear here once they are.
          </p>
        </>
      ) : (
        <>
          <h1 className={`mt-6 ${HEADING}`}>{title}</h1>
          <p className="mt-2 text-caption leading-caption text-paper">
            {formatBatchDate(scan.createdAt)}
          </p>

          {several && (
            <div className="mt-8">
              <ConclusionTotals entries={scan.entries} />
            </div>
          )}

          <div className="mt-8">
            <ConclusionList entries={scan.entries} showTitles={several} />
          </div>
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
