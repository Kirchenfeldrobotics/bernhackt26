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

const BODY = "text-body-sm leading-body-sm tracking-body-sm text-paper";

const CAPTION = "text-caption leading-caption text-paper";

function message(cause: unknown) {
  return String(cause instanceof Error ? cause.message : cause);
}

/**
 * One card per scan, named by what was found rather than by when it ran. The
 * batch stamp and the fix count are bookkeeping, so neither is shown.
 */
function ScanCard({ scan }: { scan: Scan }) {
  const total = totalSavings(scan.entries);
  const [first, ...rest] = scan.entries;

  return (
    <Link
      href={`/outputs/${scan.batch}`}
      className="block rounded-xl border border-graphite bg-carbon p-6 transition-colors hover:border-smoke"
    >
      <h2 className="text-body-lg leading-body-lg tracking-body-lg text-paper">
        {first?.title ?? "Nothing accepted"}
      </h2>

      {rest.length > 0 && (
        <p className={`mt-2 line-clamp-2 ${BODY}`}>
          {rest.map((entry) => entry.title).join(" · ")}
        </p>
      )}

      <p className={`mt-3 ${BODY}`}>
        {total === null
          ? "No savings figure given"
          : `${formatChf(total)} over ten years`}
      </p>

      <p className={`mt-2 ${CAPTION}`}>{formatBatchDate(scan.createdAt)}</p>
    </Link>
  );
}

function ScanList({ company }: { company: string }) {
  const [scans, setScans] = useState<Scan[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listScans(company)
      .then(setScans)
      .catch((cause) => setError(message(cause)));
  }, [company]);

  if (error !== null) return <p className={BODY}>{error}</p>;
  if (scans === null) return <p className={BODY}>Loading…</p>;

  return (
    <div>
      <h1 className="text-heading-sm leading-heading-sm tracking-heading-sm text-paper">
        Accepted solutions
      </h1>

      {scans.length === 0 && (
        <p className={`mt-3 ${BODY}`}>
          Nothing has been accepted for {company} yet. Solutions are accepted in the
          headset, and show up here once they are.
        </p>
      )}

      <ul className="mt-8 flex flex-col gap-2">
        {scans.map((scan) => (
          <li key={scan.batch}>
            <ScanCard scan={scan} />
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function OutputsPage() {
  return <AppShell>{(company) => <ScanList company={company} />}</AppShell>;
}
