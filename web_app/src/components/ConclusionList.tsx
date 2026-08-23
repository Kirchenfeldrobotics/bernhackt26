import {
  formatChf,
  totalSavings,
  type Conclusion,
  type ConclusionEntry,
  type Product,
} from "@/lib/api";

/**
 * The conclusion, as a list of fixes.
 *
 * Every entry is read in the same five parts, in this order, and each part maps
 * onto exactly one field of `ConclusionEntry` in `server/solutions.py`:
 *
 *   1. Title         `title`            what the fix is
 *   2. Problem       `problem`          the negative impact it removes
 *   3. Solutions     `solutions[]`      how to do it
 *   4. Products      `products[] | null` what to buy, and where
 *   5. Money saving  `savings_10y_chf`  what the company earns by doing it
 *
 * The rest of the entry is placement data the VR app needs; it sits in the
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

/** 4. Products. Null and empty mean different things, so they read differently. */
function Products({ products }: { products: Product[] | null }) {
  if (products === null)
    return (
      <p className={`${BODY} text-ash`}>
        Not sourced yet — the analysis leaves this empty until a product catalogue
        is wired up.
      </p>
    );

  if (products.length === 0)
    return <p className={`${BODY} text-ash`}>Nothing to buy for this one.</p>;

  return (
    <ul className="flex flex-col gap-1">
      {products.map((product) => (
        <li key={product.url}>
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
        </li>
      ))}
    </ul>
  );
}

function Entry({ entry, index }: { entry: ConclusionEntry; index: number }) {
  const { x, y, z } = entry.position;

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
      <p className={`mt-2 ${BODY} text-fog`}>{entry.benefit}</p>

      {/* 2. Problem — the negative impact. Coral red is the system's colour for
          something being wrong, used here on the label alone. */}
      <Part label="Problem" tone="text-coral-red/80">
        <p className={`${BODY} text-mist`}>{entry.problem}</p>
      </Part>

      {/* 3. Solutions. */}
      <Part label="Solutions">
        <ul className={`flex list-disc flex-col gap-1.5 pl-5 marker:text-smoke ${BODY} text-mist`}>
          {entry.solutions.map((solution, solutionIndex) => (
            <li key={solutionIndex}>{solution}</li>
          ))}
        </ul>
      </Part>

      {/* 4. Products — links out, or null. */}
      <Part label="Products">
        <Products products={entry.products} />
      </Part>

      {/* 5. Money saving. The payoff, so it gets the largest type on the card. */}
      <Part label="Money saving">
        <p className="flex flex-wrap items-baseline gap-2">
          <span className="text-subheading leading-subheading tracking-subheading text-paper">
            {formatChf(entry.savings_10y_chf)}
          </span>
          <span className={`${BODY} text-fog`}>over ten years</span>
        </p>
        <p className={`mt-1 ${BODY} text-ash`}>{entry.savings_basis}</p>
      </Part>

      {/* Where the VR app floats this panel. Metadata, so it stays monospaced
          and out of the reading order of the five parts above. */}
      <div className="mt-6 flex flex-wrap items-center gap-2 border-t border-graphite pt-4">
        <span className={BADGE}>{entry.anchor_label}</span>
        <span className={BADGE}>
          {x.toFixed(2)}, {y.toFixed(2)}, {z.toFixed(2)}
        </span>
        <span className="text-caption leading-caption text-ash">
          {entry.placement_reasoning}
        </span>
      </div>
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
        <Entry key={`${entry.title}-${index}`} entry={entry} index={index} />
      ))}
    </ul>
  );
}

/** What the whole conclusion adds up to: how many fixes, and what they are worth. */
export function ConclusionTotals({ conclusion }: { conclusion: Conclusion }) {
  const count = conclusion.entries.length;

  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
      <span className="text-heading-sm leading-heading-sm tracking-heading-sm text-paper">
        {formatChf(totalSavings(conclusion))}
      </span>
      <span className={`${BODY} text-fog`}>
        over ten years, across {count} {count === 1 ? "fix" : "fixes"}
      </span>
    </div>
  );
}
