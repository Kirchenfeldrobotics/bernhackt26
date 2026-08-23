import React from "react";

/**
 * The markdown the analysis prompts actually emit, rendered in the design
 * system's type scale: headings, bold, italic, inline code, links, bulleted and
 * numbered lists, rules and paragraphs.
 *
 * Deliberately not a full parser — no HTML, no tables, no nested lists. Model
 * output is prose with a little structure, and anything unrecognised falls
 * through as the plain text it already is, which is the right failure mode
 * here: nothing is ever swallowed.
 */

type Block =
  | { kind: "heading"; level: number; text: string }
  | { kind: "list"; ordered: boolean; items: string[] }
  | { kind: "rule" }
  | { kind: "paragraph"; text: string };

const HEADING = /^(#{1,6})\s+(.*)$/;
const BULLET = /^\s*[-*+]\s+(.*)$/;
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/;
const RULE = /^\s*(?:-{3,}|_{3,}|\*{3,})\s*$/;

/** Bold, italic, inline code and links, in one pass so they cannot nest. */
const INLINE = /(\*\*[^*]+\*\*|__[^_]+__|\*[^*\n]+\*|`[^`\n]+`|\[[^\]\n]+\]\([^)\s]+\))/g;

const LINK = /^\[([^\]\n]+)\]\(([^)\s]+)\)$/;

/**
 * Model output is not trusted markup: only these schemes become a real link, so
 * a `javascript:` or `data:` href can never be rendered as clickable.
 */
function isSafeHref(url: string) {
  return /^(https?:\/\/|mailto:)/i.test(url);
}

function renderInline(text: string, keyPrefix: string): React.ReactNode[] {
  return text.split(INLINE).filter(Boolean).map((token, index) => {
    const key = `${keyPrefix}-${index}`;

    if (token.startsWith("**") && token.endsWith("**"))
      return (
        <strong key={key} className="font-[510] text-paper">
          {token.slice(2, -2)}
        </strong>
      );

    if (token.startsWith("__") && token.endsWith("__"))
      return (
        <strong key={key} className="font-[510] text-paper">
          {token.slice(2, -2)}
        </strong>
      );

    if (token.startsWith("*") && token.endsWith("*") && token.length > 2)
      return (
        <em key={key} className="italic">
          {token.slice(1, -1)}
        </em>
      );

    if (token.startsWith("`") && token.endsWith("`"))
      return (
        <code
          key={key}
          className="rounded-[4px] bg-white/5 px-1 font-mono text-[0.9em] text-paper"
        >
          {token.slice(1, -1)}
        </code>
      );

    const link = LINK.exec(token);
    if (link !== null && isSafeHref(link[2]))
      return (
        <a
          key={key}
          href={link[2]}
          target="_blank"
          rel="noreferrer noopener"
          className="text-paper underline decoration-white/30 underline-offset-2 transition-colors hover:decoration-white"
        >
          {link[1]}
        </a>
      );

    return <React.Fragment key={key}>{token}</React.Fragment>;
  });
}

/** Soft line breaks inside a paragraph are kept: the prompts lay lines out. */
function renderParagraph(text: string, keyPrefix: string): React.ReactNode[] {
  return text.split("\n").flatMap((line, index) => [
    ...(index > 0 ? [<br key={`${keyPrefix}-br-${index}`} />] : []),
    ...renderInline(line, `${keyPrefix}-${index}`),
  ]);
}

function parse(source: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];

  function flush() {
    if (paragraph.length > 0) {
      blocks.push({ kind: "paragraph", text: paragraph.join("\n") });
      paragraph = [];
    }
  }

  for (const line of source.replace(/\r\n/g, "\n").split("\n")) {
    if (line.trim() === "") {
      flush();
      continue;
    }

    if (RULE.test(line)) {
      flush();
      blocks.push({ kind: "rule" });
      continue;
    }

    const heading = HEADING.exec(line);
    if (heading !== null) {
      flush();
      blocks.push({ kind: "heading", level: heading[1].length, text: heading[2] });
      continue;
    }

    const bullet = BULLET.exec(line);
    const numbered = bullet === null ? NUMBERED.exec(line) : null;
    const item = bullet ?? numbered;
    if (item !== null) {
      flush();
      const ordered = numbered !== null;
      const last = blocks[blocks.length - 1];
      // Consecutive items of the same kind belong to one list.
      if (last !== undefined && last.kind === "list" && last.ordered === ordered) {
        last.items.push(item[1]);
      } else {
        blocks.push({ kind: "list", ordered, items: [item[1]] });
      }
      continue;
    }

    paragraph.push(line);
  }

  flush();
  return blocks;
}

const HEADING_CLASS: Record<number, string> = {
  1: "text-subheading leading-subheading tracking-subheading text-paper",
  2: "text-[16px] font-[510] leading-[1.4] tracking-[-0.01em] text-paper",
  3: "text-body-sm leading-body-sm font-[510] text-paper",
};

export default function Markdown({
  source,
  className = "",
}: {
  source: string;
  className?: string;
}) {
  const blocks = parse(source);

  return (
    // Blocks carry their own top margin, so a card can sit tight around this.
    <div
      className={`text-body-sm leading-body-sm tracking-body-sm text-paper [&>*:first-child]:mt-0 ${className}`}
    >
      {blocks.map((block, index) => {
        const key = `b-${index}`;

        if (block.kind === "rule")
          return <hr key={key} className="mt-6 border-0 border-t border-graphite" />;

        if (block.kind === "heading") {
          const Tag = `h${Math.min(block.level, 6)}` as React.ElementType;
          return (
            <Tag
              key={key}
              className={`mt-6 ${HEADING_CLASS[block.level] ?? HEADING_CLASS[3]}`}
            >
              {renderInline(block.text, key)}
            </Tag>
          );
        }

        if (block.kind === "list") {
          const Tag = block.ordered ? "ol" : "ul";
          return (
            <Tag
              key={key}
              className={`mt-3 flex flex-col gap-1 pl-5 marker:text-paper ${
                block.ordered ? "list-decimal" : "list-disc"
              }`}
            >
              {block.items.map((item, itemIndex) => (
                <li key={`${key}-${itemIndex}`}>
                  {renderInline(item, `${key}-${itemIndex}`)}
                </li>
              ))}
            </Tag>
          );
        }

        return (
          <p key={key} className="mt-3">
            {renderParagraph(block.text, key)}
          </p>
        );
      })}
    </div>
  );
}
