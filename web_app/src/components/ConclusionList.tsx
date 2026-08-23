import {
  formatChf,
  totalSavings,
  type Conclusion,
  type ConclusionEntry,
  type EntrySolution,
} from "@/lib/api";

/**
 * The conclusion, as a list of fixes.
 *
 * Every entry is read in the same five parts, in this order:
 *
 *   1. Title         what the fix is
 *   2. Problem       the negative impact it removes
 *   3. Solutions     how to do it
 *   4. Products      what to buy, and where -- null until anything is sourced
 *   5. Money saving  what the company earns by doing it
 *
 * The entries arrive already normalised by `lib/api`, so this component renders
 * one shape no matter which server generation answered. Everything optional is
 * genuinely optional here: an entry missing a field is shown without it rather
 * than taking the view down.
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

/** 3. Solutions. Each carries its own description when the server sent one. */
function Solutions({ solutions }: { solutions: EntrySolution[] }) {
  if (solutions.length === 0)
    return <p className={`${BODY} text-ash`}>No solutions were proposed.</p>;

  return (
    <ul className={`flex list-disc flex-col gap-2 pl-5 marker:text-smoke ${BODY} text-mist`}>
      {solutions.map((solution, index) => (
        <li key={index}>
          {solution.name}
          {solution.description !== null && (
            <span className="block text-ash">{solution.description}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

/**
 * 4. Products. Null means nothing was sourced; an empty list means these fixes
 * need no purchase at all. A URL is never invented, so a product without one is
 * still shown -- just not as a link.
 */
function Products({ products }: { products: EntrySolution[] | null }) {
  if (products === null)
    return (
      <p className={`${BODY} text-ash`}>
        Not sourced yet — the analysis leaves this empty until a product catalogue
        is wired up.
      </p>
    );

  if (products.length === 0)
    return (
      <p className={`${BODY} text-ash`}>Nothing to buy — these fixes are behavioural.</p>
    );

  return (
    <ul className="flex flex-col gap-1">
      {products.map((product, index) => (
        <li key={index}>
          {product.url === null ? (
            <span className={`${BODY} text-mist`}>{product.name}</span>
          ) : (
            <a
              href={product.url}
              target="_blank"
              rel="noreferrer noopener"
              className={`${BODY} text-mist underline decoration-smoke underline-offset-2 transition-colors hover:text-paper hover:decoration-fog`}
            >
              {product.name}
              <span aria-hidden className="ml-1 text-ash">
                ↗
              </span>
            </a>
          )}
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
      {entry.benefit !== null && <p className={`mt-2 ${BODY} text-fog`}>{entry.benefit}</p>}

      {/* 2. Problem — the negative impact. Coral red is the system's colour for
          something being wrong, used here on the label alone. */}
      {entry.problem !== "" && (
        <Part label="Problem" tone="text-coral-red/80">
          <p className={`${BODY} text-mist`}>{entry.problem}</p>
        </Part>
      )}

      {/* 3. Solutions. */}
      <Part label="Solutions">
        <Solutions solutions={entry.solutions} />
      </Part>

      {/* 4. Products — links out, or nothing sourced. */}
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
          {entry.placementReasoning !== null && (
            <span className="text-caption leading-caption text-ash">
              {entry.placementReasoning}
            </span>
          )}
        </div>
      )}
    </li>
  );
}

export default function ConclusionList({ conclusion }: { conclusion: Conclusion }) {
  if (conclusion.entries.length === 0)
    return (
      <p className={`${BODY} text-ash`}>
        The analysis found nothing to fix in this room.
      </p>
    );

  return (
    <ul className="flex flex-col gap-2">
      {conclusion.entries.map((entry, index) => (
        <Entry key={index} entry={entry} index={index} />
      ))}
    </ul>
  );
}

/** What the whole conclusion adds up to: how many fixes, and what they are worth. */
export function ConclusionTotals({ conclusion }: { conclusion: Conclusion }) {
  const count = conclusion.entries.length;
  const total = totalSavings(conclusion);

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
