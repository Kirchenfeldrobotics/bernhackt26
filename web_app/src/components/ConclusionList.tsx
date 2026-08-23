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
 * Every entry is read in the same five parts, in this order, and each maps onto
 * one field of what `/get-accepted-solutions` returns:
 *
 *   1. Title         `conclusion.title`
 *   2. Problem       `conclusion.problem`          the negative impact
 *   3. Solutions     the accepted `solution` rows  name + description
 *   4. Products      those carrying a `url`
 *   5. Money saving  `conclusion.savings_10y_chf`  "|amount|explanation"
 *
 * `conclusion.anchor` is where the VR app floats the panel; it sits in the
 * card's footer rather than being dropped.
 */

const EYEBROW = "text-eyebrow leading-eyebrow tracking-eyebrow uppercase";

const BADGE =
  "rounded-[4px] bg-white/5 px-1.5 font-mono text-[12px] leading-[1.4] tracking-[-0.013em] text-fog";

const BODY = "text-body-sm leading-body-sm tracking-body-sm";

/** One of the five parts: a hairline-quiet label over its content. */
function Part({
  label,
  tone = "text-ash",
  children,
}: {
  label: string;
  tone?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-6">
      <h4 className={`${EYEBROW} ${tone}`}>{label}</h4>
      <div className="mt-2">{children}</div>
    </section>
  );
}

/** 3. Solutions. Only the ones actually accepted in VR come back. */
function Solutions({ solutions }: { solutions: EntrySolution[] }) {
  if (solutions.length === 0)
    return <p className={`${BODY} text-ash`}>No solutions were accepted for this one.</p>;

  return (
    <ul className={`flex list-disc flex-col gap-2 pl-5 marker:text-smoke ${BODY} text-mist`}>
      {solutions.map((solution, index) => (
        <li key={solution.id ?? index}>
          {solution.name}
          {solution.description !== null && (
            <Markdown source={solution.description} className="mt-0.5 text-ash" />
          )}
        </li>
      ))}
    </ul>
  );
}

/**
 * 4. Products. A solution carrying a link is a thing to buy; one without is a
 * behavioural fix. A URL is never invented, so an empty list is a real answer.
 */
function Products({ products }: { products: EntrySolution[] }) {
  if (products.length === 0)
    return (
      <p className={`${BODY} text-ash`}>Nothing to buy — these fixes are behavioural.</p>
    );

  return (
    <ul className="flex flex-col gap-1">
      {products.map((product, index) => (
        <li key={product.id ?? index}>
          <a
            href={product.url as string}
            target="_blank"
            rel="noreferrer noopener"
            className={`${BODY} text-mist underline decoration-smoke underline-offset-2 transition-colors hover:text-paper hover:decoration-fog`}
          >
            {product.name}
            <span aria-hidden className="ml-1 text-ash">
              ↗
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}

function Entry({ entry, index }: { entry: ConclusionEntry; index: number }) {
  const { position } = entry;

  return (
    <li className="rounded-xl border border-graphite bg-carbon p-6">
      {/* 1. Title. The index is technical metadata, so it is monospaced. */}
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-mono text-[12px] leading-[1.4] tracking-[-0.013em] text-ash">
          {String(index + 1).padStart(2, "0")}
        </span>
        <h3 className="text-body-lg leading-body-lg tracking-body-lg text-paper">
          {entry.title}
        </h3>
      </div>

      {/* 2. Problem — the negative impact. Coral red is the system's colour for
          something being wrong, used here on the label alone. */}
      {entry.problem !== "" && (
        <Part label="Problem" tone="text-coral-red/80">
          <Markdown source={entry.problem} />
        </Part>
      )}

      {/* 3. Solutions. */}
      <Part label="Solutions">
        <Solutions solutions={entry.solutions} />
      </Part>

      {/* 4. Products — links out, or nothing to buy. */}
      <Part label="Products">
        <Products products={entry.products} />
      </Part>

      {/* 5. Money saving. The payoff, so it gets the largest type on the card. */}
      <Part label="Money saving">
        <p className="flex flex-wrap items-baseline gap-2">
          <span className="text-subheading leading-subheading tracking-subheading text-paper">
            {formatChf(entry.savings.amount)}
          </span>
          {entry.savings.amount !== null && (
            <span className={`${BODY} text-fog`}>over ten years</span>
          )}
        </p>
        {entry.savings.basis !== null && (
          <p className={`mt-1 ${BODY} text-ash`}>{entry.savings.basis}</p>
        )}
      </Part>

      {/* Where the VR app floats this panel. Metadata, so it stays monospaced
          and out of the reading order of the five parts above. */}
      {(entry.anchorLabel !== null || position !== null) && (
        <div className="mt-6 flex flex-wrap items-center gap-2 border-t border-graphite pt-4">
          {entry.anchorLabel !== null && <span className={BADGE}>{entry.anchorLabel}</span>}
          {position !== null && (
            <span className={BADGE}>
              {position.x.toFixed(2)}, {position.y.toFixed(2)}, {position.z.toFixed(2)}
            </span>
          )}
        </div>
      )}
    </li>
  );
}

export default function ConclusionList({ entries }: { entries: ConclusionEntry[] }) {
  if (entries.length === 0)
    return (
      <p className={`${BODY} text-ash`}>
        Nothing has been accepted for this scan yet.
      </p>
    );

  return (
    <ul className="flex flex-col gap-2">
      {entries.map((entry, index) => (
        <Entry key={entry.id ?? index} entry={entry} index={index} />
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
      <span className={`${BODY} text-fog`}>
        {total === null
          ? "no savings figure given"
          : `over ten years, across ${count} ${count === 1 ? "fix" : "fixes"}`}
      </span>
    </div>
  );
}
