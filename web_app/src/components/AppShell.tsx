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
      <header className="border-b border-graphite">
        <div className="mx-auto flex w-full max-w-[1200px] items-center gap-8 px-6 py-4">
          <span className="text-[16px] font-[510] tracking-[-0.01em] text-paper">
            {company}
          </span>

          <nav className="flex items-center gap-1">
            {NAV.map((item) => {
              const active =
                pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`rounded-md px-3 py-2 text-caption leading-caption transition-colors ${
                    active
                      ? "bg-white/5 text-paper"
                      : "text-mist hover:bg-white/[0.03] hover:text-paper"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <button
            type="button"
            onClick={signOut}
            className="ml-auto rounded-md px-3 py-2 text-caption leading-caption text-fog transition-colors hover:text-mist"
          >
            Sign out
          </button>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1200px] flex-1 px-6 py-16">
        {children(company)}
      </main>
    </div>
  );
}
