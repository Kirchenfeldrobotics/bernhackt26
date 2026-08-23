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
| `coral-red` | `#eb5757` | errors and destructive actions, outside the conclusion views |

**The chromatic rule: acid lime appears at most once per view.** It marks the one
action that view exists for — *Create* on the start page, *Save* in settings,
*Run analysis* on an unanalysed scan. Once a scan has a conclusion, its re-run
button drops to a ghost button, because the view's purpose is now reading the
list, not producing it.

Coral red is semantic, not decorative: something is wrong. That covers request
errors and the delete flow on the start and settings pages.

The conclusion views take no colour at all — not even for a failure, not even on
the `Problem` label. Every word on them is `text-paper`, and hierarchy is carried
by size and weight alone. The savings figures are the payoff of the whole app and
still get no colour; they earn attention through size.

### Type

| Token | Size / leading / tracking |
| --- | --- |
| `caption` | 13px / 1.2 |
| `body-sm` | 15px / 1.6 / −0.165px |
| `body-lg` | 20px / 1.33 / −0.24px |
| `subheading` | 24px / 1.33 / −0.288px |
| `heading-sm` | 32px / 1.13 / −0.704px |
| `heading` | 48px / 1 / −1.056px |

Inter Variable is the interface face. Berkeley Mono is not freely
distributable, so JetBrains Mono stands in for it and is reserved for values that
really are code — inline `code` in rendered markdown. The conclusion views show
no machine metadata at all, so nothing else on them is monospaced.

The label naming each part of an entry sits on `caption`, in `font-[510]`:
sentence case, no letter-spacing, one step below the body it introduces. Nothing
in these views is set in capitals.

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

The centrepiece of the app: the fixes a company accepted in VR, as a list. It is
fed by one call -- `POST /get-accepted-solutions` with `{"company_name": …}` --
which answers with one row per accepted solution, each carrying the conclusion
around it. A conclusion with several accepted solutions therefore repeats across
rows, so `lib/api.ts` regroups the whole list by conclusion, then by scan, and
the components never see the repetition. Only *accepted* solutions come back: a
fix nobody took in the headset is not in the answer at all.

It lives
in [`src/components/ConclusionList.tsx`](src/components/ConclusionList.tsx) and
is rendered by
[`src/app/outputs/[batch]/page.tsx`](src/app/outputs/[batch]/page.tsx).

### The four parts

One card holds a conclusion's whole text. Every entry is read in the same four
parts, in this order, and each maps onto one field of what
`POST /get-accepted-solutions` returns:

| # | Part | Field | Rendering |
| --- | --- | --- | --- |
| 1 | **Problem** | `conclusion.problem` | The negative impact. Label and body both `text-paper`. |
| 2 | **Solutions** | the accepted `solution` rows | One bullet per fix, `list-disc`, each with its description beneath. |
| 3 | **Products** | the solutions carrying a `url` | Links out to where each thing is bought. |
| 4 | **Money saving** | `conclusion.savings_10y_chf` | `subheading`, the largest type on the card, with the basis beneath. |

`conclusion.title` sits above them at `body-lg` — or, when a scan holds a single
conclusion, as the page's own `heading-sm` instead, so it is never printed twice.

What is *not* shown is as deliberate. `conclusion.id`, the batch stamp, the entry
index and `conclusion.anchor` — its label and room coordinates — are what the VR
app needs to float a panel in space. They tell whoever reads this page nothing,
so none of them is rendered.

### Products

A URL is never invented. A solution carrying one is a thing to buy; one without
is a behavioural fix, so an empty product list is a real answer, not a gap.

| State | Shown as |
| --- | --- |
| no product carries a link | "Nothing to buy — these fixes are behavioural." |
| a product with a URL | `text-paper` underlined in `decoration-white/30`, with a `↗` — set apart by the underline, never by a colour |

Product links open in a new tab with `rel="noreferrer noopener"`.

### Totals

Above the list, `ConclusionTotals` states what a scan is worth: the sum of every
entry's savings at `heading-sm`, then the count of fixes. It appears only when a
scan holds more than one conclusion — with one, it would just restate that card's
own *Money saving*. The scan list at `/outputs` shows the same figure per row, so
the value of a scan is visible before opening it.

### Money

Savings render through `formatChf` in [`src/lib/api.ts`](src/lib/api.ts), fixed
to `de-CH` rather than the visitor's locale: the number is francs whoever reads
it, and apostrophe grouping (`CHF 4'820`) is how it is written here. Rappen are
dropped — these are ten-year estimates, and decimals would imply precision the
number does not have.

An unparseable amount shows as "Unknown", and a conclusion where no entry
carried a usable number falls back to the count of fixes. Neither ever renders
as `CHF NaN` or as a confident zero.

### States of the view

| State | View |
| --- | --- |
| nothing accepted anywhere | The list says so, and explains that solutions are accepted in the headset. |
| nothing accepted for this scan | The detail view says the same. |
| failed | The server's `detail` message, in `text-paper` like everything else here. |
| has conclusions | The title, the date beneath it, then the cards. |

A scan is named on both views by its first conclusion's title, never by its date
or its batch stamp: what was found is what identifies it. The date stays as a
`caption` line under the title, which is the one thing that tells two similar
scans apart.

There is no *Run analysis* button. Conclusions are produced by the headset
through `/receive-data` and accepted in VR; this app reads what came of that,
it does not start it. That leaves these views with no primary action, so they
stay fully monochrome.

---

## Markdown

`conclusion.problem` and each solution's `description` are model-written prose,
so they are rendered as markdown rather than dumped into a
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
- Links stay monochrome — `text-paper` underlined in `decoration-white/30` — so
  markdown can never spend the view's one chromatic accent.

Blocks carry their own top margin and the first child's is stripped, so a card
can sit tight around a `<Markdown>` without a stray gap at the top.

---

## Reaching the API

The browser calls the API directly, at the routes the server actually serves.
FastAPI mounts them at its root — `/companies`, `/get-accepted-solutions`,
`/gemini-outputs` — so those are the paths
[`src/lib/api.ts`](src/lib/api.ts) asks for, appended to the host and nothing
else. There is no `/api` prefix anywhere in this app, because there is none on
the server: `/api/companies` is a 404.

`NEXT_PUBLIC_API_URL` is the one place the host is written down, defaulting to
the deployed server. Set it to point a deployment or a dev session somewhere
else.

The cost of calling directly is that CORS applies. Whatever server this points
at has to list the origin the app is served from in its `ALLOWED_ORIGINS`, or
the browser refuses each request before sending it — which surfaces here as
"Could not reach …". That is a line in the server's `.env`, not something to
work around from this side.

## When the API fails

The API sits behind a proxy that answers with its own HTML error page, and it is
not always up. Every request goes through one place in
[`src/lib/api.ts`](src/lib/api.ts) that turns any of that into one readable
sentence — `coral-red` on the start and settings pages, `text-paper` on the
conclusion views, which carry no colour. Never a wall of markup, never a bare
"Failed to fetch".

| Failure | Shown as |
| --- | --- |
| FastAPI error | its own `detail` message |
| 502 / 503 / 504 | what is actually wrong, e.g. "The API is not reachable right now. The service behind the proxy is down or restarting." |
| any other HTML or empty body | the status line, never the page |
| no response at all — offline, DNS, TLS, CORS | "Could not reach the API at …" naming the URL |
| no answer within 30s | the request is aborted and says so, rather than leaving a "Loading…" forever |

Two rules behind this:

- **Never assume a field is there.** A server that omits `conclusion` sends no
  key at all, not `null` — and `undefined !== null` is true, which is exactly
  how a missing field turns into a blank page. Responses are normalised on the
  way in so every reader sees `null`.
- **Degrade, don't disappear.** An empty room description, a missing savings
  figure, an entry without placement data: each is shown as what it is, and none
  of them takes the view down.

---

## Files

| Path | What it holds |
| --- | --- |
| [`next.config.ts`](next.config.ts) | where the API is, and the forwarding that avoids CORS |
| [`src/app/globals.css`](src/app/globals.css) | every design token |
| [`src/components/AppShell.tsx`](src/components/AppShell.tsx) | header, nav, session gate |
| [`src/components/ConclusionList.tsx`](src/components/ConclusionList.tsx) | the five-part entry, and the totals line |
| [`src/components/Markdown.tsx`](src/components/Markdown.tsx) | markdown in the type scale |
| [`src/lib/api.ts`](src/lib/api.ts) | server types, requests, `formatChf`, `totalSavings` |
