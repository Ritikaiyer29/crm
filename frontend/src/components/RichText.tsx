import { Fragment, type ReactNode } from "react";
import { Link } from "react-router-dom";

// Renders the small subset of formatting the bot uses (paragraphs, "- " lists, **bold**, [text](link)) as React
// elements, never as raw HTML, and only links to this site or https URLs.
const INLINE = /\[([^\]]+)\]\(([^)\s]+)\)|\*\*([^*]+)\*\*/g;

function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(INLINE)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    if (m[3] !== undefined) {
      out.push(<strong key={m.index}>{m[3]}</strong>);
    } else if (m[2].startsWith("/")) {
      out.push(
        <Link key={m.index} to={m[2]}>
          {m[1]}
        </Link>,
      );
    } else if (m[2].startsWith("https://")) {
      out.push(
        <a key={m.index} href={m[2]} target="_blank" rel="noreferrer">
          {m[1]}
        </a>,
      );
    } else {
      out.push(m[1]);
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const BULLET = /^\s*(?:[-*•]|\d+[.)])\s+/;

export function RichText({ text }: { text: string }) {
  const blocks = text.trim().split(/\n{2,}/);
  return (
    <>
      {blocks.map((block, i) => {
        const lines = block.split("\n");
        if (lines.every((l) => BULLET.test(l))) {
          return (
            <ul key={i}>
              {lines.map((l, j) => (
                <li key={j}>{inline(l.replace(BULLET, ""))}</li>
              ))}
            </ul>
          );
        }
        return (
          <p key={i}>
            {lines.map((l, j) => (
              <Fragment key={j}>
                {j > 0 && <br />}
                {inline(l)}
              </Fragment>
            ))}
          </p>
        );
      })}
    </>
  );
}
