"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";

import { clearSession, readSession, subscribeSession } from "@/lib/api";

const NAV = [
  { href: "/outputs", label: "Outputs" },
  { href: "/settings", label: "Settings" },
] as const;

// localStorage does not exist while the page is rendered on the server, so the
// session has three states, not two: not known yet, signed out, signed in.
const LOADING = Symbol("loading");

function useSession() {
  return useSyncExternalStore<string | null | typeof LOADING>(
    subscribeSession,
    readSession,
    () => LOADING,
  );
}

/**
 * Frame for every signed-in page: sends visitors without a company back to the
 * login, and renders the header once one is known.
 */
export default function AppShell({
  children,
}: {
  children: (company: string) => React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const company = useSession();

  useEffect(() => {
    if (company === null) router.replace("/");
  }, [company, router]);

  // Nothing to show until the browser has told us who is signed in.
  if (company === LOADING || company === null) return null;

  function signOut() {
    clearSession();
    router.replace("/");
  }

  return (
    <div className="flex flex-1 flex-col">
      <header className="border-b border-hairline bg-surface-alt">
        <div className="mx-auto flex w-full max-w-[1280px] items-center gap-6 px-6 py-4">
          <span className="text-body font-medium text-ink">{company}</span>
          <nav className="flex items-center gap-1">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-2xl px-3 py-1.5 text-body transition-colors ${
                  pathname === item.href || pathname.startsWith(`${item.href}/`)
                    ? "bg-canvas font-medium text-ink"
                    : "text-mid-gray hover:text-ink"
                }`}
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <button
            type="button"
            onClick={signOut}
            className="ml-auto rounded-2xl px-3 py-1.5 text-body text-mid-gray transition-colors hover:text-ink"
          >
            Sign out
          </button>
        </div>
      </header>
      <main className="mx-auto w-full max-w-[1280px] flex-1 px-6 py-12">
        {children(company)}
      </main>
    </div>
  );
}
