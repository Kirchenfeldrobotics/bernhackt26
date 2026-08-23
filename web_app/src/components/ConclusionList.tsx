import Markdown from "@/components/Markdown";
import {
  formatChf,
  totalSavings,
  type ConclusionEntry,
  type EntrySolution,
} from "@/lib/api";

/**
 * The conclusions a company has accepted solutions for, as a list of fixes.
 *
 * One card per conclusion, holding the whole text. Every entry is read in the
 * same four parts, in this order, and each maps onto one field of what
 * `/get-accepted-solutions` returns:
 *
 *   1. Problem       `conclusion.problem`          the negative impact
 *   2. Solutions     the accepted `solution` rows  name + description
 *   3. Products      those carrying a `url`
 *   4. Money saving  `conclusion.savings_10y_chf`  "|amount|explanation"
 *
 * The title sits above them, unless the page already carries it as its heading.
 * `conclusion.id` and `conclusion.anchor` are the VR app's business -- an id and
 * a set of room coordinates say nothing to whoever reads this -- so neither is
 * shown.
 *
 * Everything is white: hierarchy is size and weight, never colour.
 */

/** A part's label: smaller than the body it introduces, and heavier. */
const LABEL = "text-caption leading-caption font-[510] text-paper";

const BODY = "text-body-sm leading-body-sm tracking-body-sm text-paper";

/** One of the four parts: a quiet label over its content. */
function Part({ label, children }: { label: string; children: React.ReactNode }) {
  // first:mt-0 so the card sits tight whether or not a title precedes this.
  return (
    <section className="mt-6 first:mt-0">
      <h4 className={LABEL}>{label}</h4>
      <div className="mt-2">{children}</div>
    </section>
  );
}

/** 2. Solutions. Only the ones actually accepted in VR come back. */
function Solutions({ solutions }: { solutions: EntrySolution[] }) {
  if (solutions.length === 0)
    return <p className={BODY}>No solutions were accepted for this one.</p>;

  return (
    <ul className={`flex list-disc flex-col gap-2 pl-5 marker:text-paper ${BODY}`}>
      {solutions.map((solution, index) => (
        <li key={solution.id ?? index}>
          {solution.name}
          {solution.description !== null && (
            <Markdown source={solution.description} className="mt-0.5" />
          )}
        </li>
      ))}
    </ul>
  );
}

/**
 * 3. Products. A solution carrying a link is a thing to buy; one without is a
 * behavioural fix. A URL is never invented, so an empty list is a real answer.
 */
function Products({ products }: { products: EntrySolution[] }) {
  if (products.length === 0)
    return <p className={BODY}>Nothing to buy — these fixes are behavioural.</p>;

  return (
    <ul className="flex flex-col gap-1">
      {products.map((product, index) => (
        <li key={product.id ?? index}>
          {/* A link is set apart by its underline rather than by a colour. */}
          <a
            href={product.url as string}
            target="_blank"
            rel="noreferrer noopener"
            className={`${BODY} underline decoration-white/30 underline-offset-2 transition-colors hover:decoration-white`}
          >
            {product.name}
            <span aria-hidden className="ml-1">
              ↗
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}

function Entry({ entry, showTitle }: { entry: ConclusionEntry; showTitle: boolean }) {
  return (
    <li className="rounded-xl border border-graphite bg-carbon p-6">
      {showTitle && (
        <h3 className="mb-6 text-body-lg leading-body-lg tracking-body-lg text-paper">
          {entry.title}
        </h3>
      )}

      {/* 1. Problem — the negative impact. */}
      {entry.problem !== "" && (
        <Part label="Problem">
          <Markdown source={entry.problem} />
        </Part>
      )}

      {/* 2. Solutions. */}
      <Part label="Solutions">
        <Solutions solutions={entry.solutions} />
      </Part>

      {/* 3. Products — links out, or nothing to buy. */}
      <Part label="Products">
        <Products products={entry.products} />
      </Part>

      {/* 4. Money saving. The payoff, so it gets the largest type on the card. */}
      <Part label="Money saving">
        <p className="flex flex-wrap items-baseline gap-2">
          <span className="text-subheading leading-subheading tracking-subheading text-paper">
            {formatChf(entry.savings.amount)}
          </span>
          {entry.savings.amount !== null && (
            <span className={BODY}>over ten years</span>
          )}
        </p>
        {entry.savings.basis !== null && (
          <p className={`mt-1 ${BODY}`}>{entry.savings.basis}</p>
        )}
      </Part>
    </li>
  );
}

export default function ConclusionList({
  entries,
  showTitles = true,
}: {
  entries: ConclusionEntry[];
  /** Off when the page heading is already this conclusion's title. */
  showTitles?: boolean;
}) {
  if (entries.length === 0)
    return <p className={BODY}>Nothing has been accepted for this scan yet.</p>;

  return (
    <ul className="flex flex-col gap-2">
      {entries.map((entry, index) => (
        <Entry key={entry.id ?? index} entry={entry} showTitle={showTitles} />
      ))}
    </ul>
  );
}

/** What a set of conclusions adds up to: how many fixes, and what they are worth. */
export function ConclusionTotals({ entries }: { entries: ConclusionEntry[] }) {
  const count = entries.length;
  const total = totalSavings(entries);

  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
      <span className="text-heading-sm leading-heading-sm tracking-heading-sm text-paper">
        {total === null ? `${count} ${count === 1 ? "fix" : "fixes"}` : formatChf(total)}
      </span>
      <span className={BODY}>
        {total === null
          ? "no savings figure given"
          : `over ten years, across ${count} ${count === 1 ? "fix" : "fixes"}`}
      </span>
    </div>
  );
}
