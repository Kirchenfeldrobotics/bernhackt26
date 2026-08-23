# Design

The web app is one surface on the Linear dark system: a near-black canvas, cards
lifted by hairline borders rather than shadow, Inter Variable at 400–510 with
tight tracking, and a single chromatic accent used sparingly.

Tokens live in [`src/app/globals.css`](src/app/globals.css) inside `@theme`, so
every name below is a real Tailwind utility (`bg-carbon`, `text-body-sm`,
`border-graphite`). Nothing here should be re-derived as a raw hex or px value in
a component.

---

## The system

### Colour

| Token | Value | Used for |
| --- | --- | --- |
| `void` | `#08090a` | page canvas |
| `carbon` | `#0f1011` | cards, panels |
| `obsidian` | `#161718` | raised surfaces |
| `graphite` | `#23252a` | hairline borders, rules |
| `smoke` | `#383b3f` | hover borders, list markers |
| `ash` | `#62666d` | de-emphasised text, empty states |
| `fog` | `#8a8f98` | secondary text, labels |
| `mist` | `#d0d6e0` | body text |
| `bone` / `paper` | `#e5e5e6` / `#ffffff` | headings, emphasis |
| `acid-lime` | `#e4f222` | the primary action |
| `coral-red` | `#eb5757` | errors, destructive actions, the *problem* label |

**The chromatic rule: acid lime appears at most once per view.** It marks the one
action that view exists for — *Create* on the start page, *Save* in settings,
*Run analysis* on an unanalysed scan. Once a scan has a conclusion, its re-run
button drops to a ghost button, because the view's purpose is now reading the
list, not producing it.

Coral red is semantic, not decorative: something is wrong. That covers request
errors, the delete flow, and the `Problem` label in a conclusion entry — where it
is the label only, never the body text.

Everything else stays monochrome. The savings figures are the payoff of the whole
app and still get no colour; they earn attention through size and `text-paper`.

### Type

| Token | Size / leading / tracking |
| --- | --- |
| `eyebrow` | 11px / 1.2 / +0.08em, always uppercase |
| `caption` | 13px / 1.2 |
| `body-sm` | 15px / 1.6 / −0.165px |
| `body-lg` | 20px / 1.33 / −0.24px |
| `subheading` | 24px / 1.33 / −0.288px |
| `heading-sm` | 32px / 1.13 / −0.704px |
| `heading` | 48px / 1 / −1.056px |

Inter Variable is the interface face. Berkeley Mono is not freely
distributable, so JetBrains Mono stands in for it and is reserved for technical
metadata — batch stamps, entry indices, anchor labels, coordinates. If a value
is something a machine produced and a human only checks, it is monospaced.

`eyebrow` was added for the conclusion list: it is the label that names each part
of an entry without competing with the entry's own heading.

### Space, radius, elevation

Spacing stays on Tailwind's 4px base — `p-1 p-2 p-3 p-6 p-24` — which already is
the 4/8/12/24/96 ladder this system uses.

Radius: cards `rounded-xl` (12px), inputs and buttons `rounded-md` (6px), badges
4px, pills full.

Elevation is a hairline `border-graphite`, not a shadow stack. Cards sit on
`bg-carbon` against the `void` canvas; hovering a link card lifts its border to
`border-smoke` and nothing else moves.

---

## The conclusion list

The centrepiece of the app: what a scan concluded, as a list of fixes. It lives
in [`src/components/ConclusionList.tsx`](src/components/ConclusionList.tsx) and
is rendered by
[`src/app/outputs/[batch]/page.tsx`](src/app/outputs/[batch]/page.tsx).

### The five parts

Every entry is read in the same five parts, in this order. Each part maps onto
exactly one field of `ConclusionEntry` in
[`server/solutions.py`](../server/solutions.py) — the server's structure is the
source of truth, and the list never invents a field it does not serve.

| # | Part | Server field | Type | Rendering |
| --- | --- | --- | --- | --- |
| 1 | **Title** | `title` | `str` | `body-lg` in `text-paper`, preceded by a monospaced index (`01`, `02`, …). `benefit` follows as a `body-sm` line in `text-fog`. |
| 2 | **Problem** | `problem` | `str` | The negative impact. Label in `coral-red/80`, body in `text-mist`. |
| 3 | **Solutions** | `solutions` | `str[]` | Two to four bullets, `list-disc` with `marker:text-smoke`. |
| 4 | **Products** | `products` | `Product[] \| null` | Links out to where each thing is bought. See the states below. |
| 5 | **Money saving** | `savings_10y_chf` | `float` | `subheading` in `text-paper`, the largest type on the card, with "over ten years" beside it and `savings_basis` beneath in `text-ash`. |

The remaining fields — `anchor_label`, `position`, `placement_reasoning` — are
placement data the VR app needs to float the panel in the room. They are not
dropped: they sit in a footer below a `border-graphite` rule, monospaced, out of
the reading order of the five parts.

### Products, and why it is null

`products` is `null` on every entry the server writes today. Gemini has no
product catalogue, so the field is deliberately kept out of the schema it answers
with — anything it wrote there would be an invented shop URL. The slot waits for
a real product source.

Null and empty are different states and read differently:

| State | Shown as |
| --- | --- |
| `null` | "Not sourced yet — the analysis leaves this empty until a product catalogue is wired up." in `text-ash` |
| `[]` | "Nothing to buy for this one." in `text-ash` |
| non-empty | one link per product, `text-mist` underlined in `decoration-smoke`, with a `↗` in `text-ash` |

Product links open in a new tab with `rel="noreferrer noopener"`.

### Totals

Above the list, `ConclusionTotals` states what the whole conclusion is worth: the
sum of every entry's `savings_10y_chf` at `heading-sm`, then the count of fixes.
The scan list at `/outputs` shows the same figure per row, so the value of a scan
is visible before opening it.

### Money

Savings render through `formatChf` in [`src/lib/api.ts`](src/lib/api.ts), fixed
to `de-CH` rather than the visitor's locale: the number is francs whoever reads
it, and apostrophe grouping (`CHF 4'820`) is how it is written here. Rappen are
dropped — these are ten-year estimates, and decimals would imply precision the
number does not have.

### States of the view

| State | View |
| --- | --- |
| no conclusion | A single card: what the analysis does, and `Run analysis` in acid lime — the view's one chromatic element. |
| running | Button reads "Analysing…" and is disabled, with a line noting it is two model calls. |
| failed | The server's `detail` message in `coral-red` under the button, which re-enables. |
| has a conclusion | Totals, a ghost `Re-run analysis`, the entry list, then the problems it was derived from, folded away. |

The problems text is folded into a `<details>` on purpose: the fixes are the
answer, and the problem list is the working behind them.

---

## Markdown

Model output is markdown, so it is rendered as markdown rather than dumped into a
`whitespace-pre-wrap` block.
[`src/components/Markdown.tsx`](src/components/Markdown.tsx) covers the subset
the prompts actually emit — headings, bold, italic, inline code, links, bulleted
and numbered lists, rules, and paragraphs with their soft line breaks kept, since
the prompts lay lines out deliberately (`Observed:` / `Problem:`).

It is deliberately not a full parser. No HTML, no tables, no nested lists.
Anything unrecognised falls through as the plain text it already was, so nothing
a model writes can be swallowed silently.

Two rules it does enforce:

- Only `http:`, `https:` and `mailto:` become clickable links. A `javascript:`
  or `data:` href in model output renders as text.
- Links stay monochrome — `text-mist` underlined in `decoration-smoke` — so
  markdown can never spend the view's one chromatic accent.

Blocks carry their own top margin and the first child's is stripped, so a card
can sit tight around a `<Markdown>` without a stray gap at the top.

---

## Files

| Path | What it holds |
| --- | --- |
| [`src/app/globals.css`](src/app/globals.css) | every design token |
| [`src/components/AppShell.tsx`](src/components/AppShell.tsx) | header, nav, session gate |
| [`src/components/ConclusionList.tsx`](src/components/ConclusionList.tsx) | the five-part entry, and the totals line |
| [`src/components/Markdown.tsx`](src/components/Markdown.tsx) | markdown in the type scale |
| [`src/lib/api.ts`](src/lib/api.ts) | server types, requests, `formatChf`, `totalSavings` |
