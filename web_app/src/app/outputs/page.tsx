"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import AppShell from "@/components/AppShell";
import {
  formatBatchDate,
  formatChf,
  listScans,
  totalSavings,
  type Scan,
} from "@/lib/api";

const BODY = "text-body-sm leading-body-sm tracking-body-sm";

const BADGE = "rounded-[4px] bg-white/5 px-1.5 text-[12px] leading-[1.4] text-fog";

const MONO_BADGE = `${BADGE} font-mono tracking-[-0.013em]`;

function message(cause: unknown) {
  return String(cause instanceof Error ? cause.message : cause);
}

function ScanList({ company }: { company: string }) {
  const [scans, setScans] = useState<Scan[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listScans(company)
      .then(setScans)
      .catch((cause) => setError(message(cause)));
  }, [company]);

  if (error !== null)
    return <p className={`${BODY} text-coral-red`}>{error}</p>;
  if (scans === null) return <p className={`${BODY} text-ash`}>Loading…</p>;

  return (
    <div>
      <h1 className="text-heading-sm leading-heading-sm tracking-heading-sm text-paper">
        Accepted solutions
      </h1>
      <p className={`mt-3 ${BODY} text-fog`}>
        {scans.length === 0
          ? `Nothing has been accepted for ${company} yet. Solutions are accepted in the headset, and show up here once they are.`
          : `${scans.length} scan${scans.length === 1 ? "" : "s"} with something accepted.`}
      </p>

      <ul className="mt-8 flex flex-col gap-2">
        {scans.map((scan) => {
          const total = totalSavings(scan.entries);
          const count = scan.entries.length;

          return (
            <li key={scan.batch}>
              <Link
                href={`/outputs/${scan.batch}`}
                className="block rounded-xl border border-graphite bg-carbon p-6 transition-colors hover:border-smoke"
              >
                <div className="flex flex-wrap items-center gap-3">
                  <span className="text-body-lg leading-body-lg tracking-body-lg text-paper">
                    {formatBatchDate(scan.createdAt)}
                  </span>
                  {/* Batch stamps are technical metadata: monospaced, like an issue ID. */}
                  <span className={MONO_BADGE}>{scan.batch}</span>
                  <span className={BADGE}>
                    {count} {count === 1 ? "fix" : "fixes"}
                  </span>
                </div>

                {total === null ? (
                  <p className={`mt-3 ${BODY} text-ash`}>No savings figure given</p>
                ) : (
                  <p className={`mt-3 ${BODY} text-fog`}>
                    <span className="text-paper">{formatChf(total)}</span> over ten years
                  </p>
                )}

                <p className={`mt-2 line-clamp-2 ${BODY} text-ash`}>
                  {scan.entries.map((entry) => entry.title).join(" · ")}
                </p>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default function OutputsPage() {
  return <AppShell>{(company) => <ScanList company={company} />}</AppShell>;
}
