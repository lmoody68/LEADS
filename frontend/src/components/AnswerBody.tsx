import { Fragment, type ReactNode } from "react";

/**
 * Lightweight answer renderer: renders the LLM/extractive answer with basic
 * markdown (paragraphs, **bold**, bullet lists) and turns inline citation
 * markers like [1] or [2; 15 U.S.C. § 1692c(b)] into clickable chips that
 * scroll to + highlight the matching source card (#source-N).
 */

function scrollToSource(n: number) {
  const el = document.getElementById(`source-${n}`);
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    // briefly flash a ring
    el.classList.add("ring-2", "ring-indigo-400");
    window.setTimeout(() => el.classList.remove("ring-2", "ring-indigo-400"), 1600);
  }
}

// Citation pattern: [N] or [N; anything]. Captures the leading number.
const CITE_RE = /\[(\d+)(?:;[^\]]*)?\]/g;

function renderInline(text: string, keyBase: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  CITE_RE.lastIndex = 0;
  while ((m = CITE_RE.exec(text)) !== null) {
    if (m.index > last) {
      nodes.push(
        <Fragment key={`${keyBase}-t${i}`}>{renderBold(text.slice(last, m.index), `${keyBase}-b${i}`)}</Fragment>
      );
    }
    const n = parseInt(m[1], 10);
    nodes.push(
      <button
        key={`${keyBase}-c${i}`}
        onClick={() => scrollToSource(n)}
        title="Jump to source"
        className="mx-0.5 inline-flex items-center rounded bg-indigo-100 px-1.5 text-xs font-semibold text-indigo-700 align-baseline hover:bg-indigo-200"
      >
        {n}
      </button>
    );
    last = m.index + m[0].length;
    i++;
  }
  if (last < text.length) {
    nodes.push(
      <Fragment key={`${keyBase}-tend`}>{renderBold(text.slice(last), `${keyBase}-bend`)}</Fragment>
    );
  }
  return nodes;
}

// Render **bold** spans.
function renderBold(text: string, keyBase: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) {
      return (
        <strong key={`${keyBase}-${i}`} className="font-semibold text-slate-900">
          {p.slice(2, -2)}
        </strong>
      );
    }
    return <Fragment key={`${keyBase}-${i}`}>{p}</Fragment>;
  });
}

export default function AnswerBody({ text }: { text: string }) {
  const blocks = text.split(/\n{2,}/);
  return (
    <div className="space-y-3 text-sm leading-relaxed text-slate-800">
      {blocks.map((block, bi) => {
        const lines = block.split("\n");
        const isList = lines.every((l) => /^\s*([-*•]|\d+\.)\s+/.test(l));
        if (isList) {
          return (
            <ul key={bi} className="list-disc space-y-1 pl-5">
              {lines.map((l, li) => (
                <li key={li}>{renderInline(l.replace(/^\s*([-*•]|\d+\.)\s+/, ""), `${bi}-${li}`)}</li>
              ))}
            </ul>
          );
        }
        return (
          <p key={bi} className="whitespace-pre-wrap">
            {renderInline(block, `p${bi}`)}
          </p>
        );
      })}
    </div>
  );
}
