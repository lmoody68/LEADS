import { useRef, useState, useEffect } from "react";
import { assistantChat, type AssistantResult } from "../lib/api";

type Msg =
  | { role: "user"; content: string }
  | { role: "assistant"; content: string; tool?: string; why?: string; sources?: { citation: string; title: string }[] };

const SUGGESTIONS = [
  "Is it lawful for a landlord to pull a tenant's credit report?",
  "When may a debt collector contact a third party?",
  "Make flashcards on the FDCPA",
  "Explain 'summary judgment' in plain English",
  "Outline permissible purpose under the FCRA",
];

export default function AssistantView() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, loading]);

  async function send(text?: string) {
    const message = (text ?? input).trim();
    if (!message || loading) return;
    setErr(null);
    const history = msgs.slice(-6).map((m) => ({ role: m.role, content: m.content }));
    setMsgs((m) => [...m, { role: "user", content: message }]);
    setInput("");
    setLoading(true);
    try {
      const r: AssistantResult = await assistantChat(message, history);
      setMsgs((m) => [
        ...m,
        { role: "assistant", content: r.reply, tool: r.tool_used, why: r.why, sources: r.sources },
      ]);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex h-[70vh] flex-col">
      <div>
        <h2 className="text-xl font-semibold text-slate-800">Assistant</h2>
        <p className="text-sm text-slate-500">
          Ask anything in plain language — the assistant routes your request to the right tool
          (research, case brief, plain-English, compliance, citator, related authorities, flashcards,
          outline, or document type) and answers. General legal information, not legal advice.
        </p>
      </div>

      {/* Messages */}
      <div className="my-3 flex-1 space-y-3 overflow-y-auto rounded-lg border border-slate-200 bg-slate-50 p-3">
        {msgs.length === 0 && !loading && (
          <div className="space-y-2 p-2">
            <p className="text-sm text-slate-400">Try one of these:</p>
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => void send(s)}
                  className="rounded-full border border-slate-300 bg-white px-3 py-1 text-xs text-slate-600 hover:border-indigo-300 hover:text-indigo-700"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {msgs.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-indigo-600 px-3 py-2 text-sm text-white">
                {m.content}
              </div>
            </div>
          ) : (
            <div key={i} className="flex justify-start">
              <div className="max-w-[90%] rounded-2xl rounded-bl-sm border border-slate-200 bg-white px-3 py-2 text-sm">
                {m.tool && (
                  <div className="mb-1 flex items-center gap-2">
                    <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-indigo-600">
                      via {m.tool}
                    </span>
                    {m.why && <span className="text-[10px] text-slate-400">{m.why}</span>}
                  </div>
                )}
                <p className="whitespace-pre-wrap text-slate-800">{m.content}</p>
                {m.sources && m.sources.length > 0 && (
                  <div className="mt-2 border-t border-slate-100 pt-1">
                    <div className="text-[10px] uppercase tracking-wide text-slate-400">Sources</div>
                    <ul className="text-xs text-slate-600">
                      {m.sources.slice(0, 6).map((s, j) => (
                        <li key={j}>• {s.citation || s.title}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          )
        )}
        {loading && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-2xl rounded-bl-sm border border-slate-200 bg-white px-3 py-2 text-sm text-slate-500">
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
              thinking…
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {err && <div className="mb-2 rounded-lg border border-red-200 bg-red-50 p-2 text-sm text-red-700">{err}</div>}

      {/* Input */}
      <div className="flex gap-2">
        <input
          className="flex-1 rounded-lg border border-slate-300 p-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          placeholder="Ask the assistant anything…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void send()}
        />
        <button
          onClick={() => void send()}
          disabled={loading || !input.trim()}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          Send
        </button>
        <button
          onClick={() => {
            setMsgs([]);
            setErr(null);
          }}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
        >
          Clear
        </button>
      </div>
    </div>
  );
}
