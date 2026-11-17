"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useApp } from "./Providers";

type Msg = { role: "user" | "assistant"; content: string };
type Proposal = { action: string; params: Record<string, unknown>; summary: string };
type TurnResult = {
  llm: boolean;
  reply?: string;
  steps?: string[];
  proposals?: Proposal[];
  cards?: Record<string, unknown>[];
};

const QUICK_ACTIONS = [
  { key: "summarise", label: "Summarise this job", tool: "job_overview" },
  { key: "first", label: "Who should I look at first?", tool: "get_shortlist" },
  { key: "missing", label: "What is missing most often?", tool: "job_analytics" },
  { key: "check", label: "Check my job post", tool: "check_job_quality" },
];

export default function Assistant({ jobId }: { jobId?: string }) {
  const { t } = useApp();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [steps, setSteps] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollBottom = useCallback(() => {
    requestAnimationFrame(() => scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight));
  }, []);

  useEffect(() => { if (open) { scrollBottom(); inputRef.current?.focus(); } }, [open, scrollBottom]);
  useEffect(scrollBottom, [messages, scrollBottom]);

  const send = async (text: string) => {
    const next: Msg[] = [...messages, { role: "user", content: text }];
    setMessages(next);
    setInput("");
    setLoading(true);
    setProposals([]);
    setSteps([]);
    try {
      const res = await api<TurnResult>("/assistant/chat", {
        method: "POST",
        json: { messages: next.slice(-20), job_id: jobId || null },
      });
      if (!res.llm) {
        setMessages((m) => [...m, { role: "assistant", content: t("The assistant is not available right now. You can still use the quick actions below.") }]);
      } else {
        if (res.reply) setMessages((m) => [...m, { role: "assistant", content: res.reply! }]);
        if (res.proposals?.length) setProposals(res.proposals);
        if (res.steps?.length) setSteps(res.steps);
      }
    } catch {
      setMessages((m) => [...m, { role: "assistant", content: t("Something went wrong") }]);
    } finally {
      setLoading(false);
    }
  };

  const quickAction = async (tool: string) => {
    setLoading(true);
    setProposals([]);
    setSteps([]);
    try {
      const args: Record<string, unknown> = {};
      if (jobId) args.job_id = jobId;
      const res = await api<Record<string, unknown>>("/assistant/tool", {
        method: "POST",
        json: { name: tool, arguments: args },
      });
      const text = typeof res === "object" ? JSON.stringify(res, null, 2) : String(res);
      setMessages((m) => [...m, { role: "assistant", content: text }]);
    } catch {
      setMessages((m) => [...m, { role: "assistant", content: t("Something went wrong") }]);
    } finally {
      setLoading(false);
    }
  };

  const confirmProposal = async (p: Proposal) => {
    setLoading(true);
    try {
      if (p.action === "update_policy" && jobId) {
        await api(`/jobs/${jobId}/policy`, { method: "PUT", json: p.params });
      } else if (p.action === "update_weights" && jobId) {
        await api(`/jobs/${jobId}/weights`, { method: "PUT", json: p.params });
      } else if (p.action === "update_draft" && jobId) {
        await api(`/jobs/${jobId}`, { method: "PUT", json: p.params });
      }
      setMessages((m) => [...m, { role: "assistant", content: `${t("Done")}: ${p.summary}` }]);
      setProposals((pp) => pp.filter((x) => x !== p));
      window.location.reload();
    } catch {
      setMessages((m) => [...m, { role: "assistant", content: t("Something went wrong") }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (input.trim() && !loading) send(input.trim());
    }
  };

  return (
    <>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label={t("Assistant")}
        aria-expanded={open}
        className="fixed bottom-4 end-4 z-40 flex h-12 w-12 items-center justify-center rounded-full bg-brand-600 text-white shadow-lg hover:bg-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2"
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
      </button>

      {open && (
        <div
          role="dialog"
          aria-label={t("Assistant")}
          className="fixed bottom-20 end-4 z-40 flex max-h-[min(70vh,36rem)] w-[min(24rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl"
        >
          {/* header */}
          <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
            <h2 className="text-sm font-semibold">{t("Assistant")}</h2>
            <button onClick={() => setOpen(false)} aria-label={t("Close the assistant")} className="text-slate-400 hover:text-slate-600">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12" /></svg>
            </button>
          </div>

          {/* messages */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-3" aria-live="polite">
            {messages.length === 0 && (
              <p className="text-center text-sm text-slate-500">{t("Ask a question about your jobs and candidates.")}</p>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[85%] rounded-xl px-3 py-2 text-sm whitespace-pre-wrap ${
                  m.role === "user" ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-800"
                }`}>
                  {m.content}
                </div>
              </div>
            ))}

            {/* steps */}
            {steps.length > 0 && (
              <details className="text-xs text-slate-500">
                <summary className="cursor-pointer">{t("I looked up: {items}", { items: steps.join(", ") })}</summary>
              </details>
            )}

            {/* proposals */}
            {proposals.map((p, i) => (
              <div key={i} className="rounded-lg border border-brand-200 bg-brand-50 p-3 text-sm">
                <p className="font-medium">{p.summary}</p>
                <div className="mt-2 flex gap-2">
                  <button
                    className="rounded bg-brand-600 px-3 py-1 text-xs font-medium text-white hover:bg-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-500"
                    onClick={() => confirmProposal(p)}
                    disabled={loading}
                  >{t("Confirm")}</button>
                  <button
                    className="rounded bg-slate-200 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-300"
                    onClick={() => setProposals((pp) => pp.filter((x) => x !== p))}
                  >{t("Ignore")}</button>
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex justify-start">
                <div className="rounded-xl bg-slate-100 px-3 py-2 text-sm text-slate-500" role="status">{t("Thinking…")}</div>
              </div>
            )}
          </div>

          {/* quick actions */}
          {jobId && messages.length === 0 && (
            <div className="flex flex-wrap gap-1.5 border-t border-slate-100 px-3 py-2">
              {QUICK_ACTIONS.map((a) => (
                <button
                  key={a.key}
                  onClick={() => quickAction(a.tool)}
                  disabled={loading}
                  className="rounded-full border border-slate-200 px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-brand-500"
                >{t(a.label)}</button>
              ))}
            </div>
          )}

          {/* input */}
          <div className="border-t border-slate-200 p-3">
            <div className="flex gap-2">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKey}
                placeholder={t("Ask the assistant…")}
                rows={1}
                disabled={loading}
                className="flex-1 resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                aria-label={t("Message")}
              />
              <button
                onClick={() => input.trim() && !loading && send(input.trim())}
                disabled={!input.trim() || loading}
                aria-label={t("Send")}
                className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-40 focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="m22 2-7 20-4-9-9-4z" /><path d="m22 2-11 11" /></svg>
              </button>
            </div>
            <p className="mt-1.5 text-center text-[11px] text-slate-400">{t("AI decision support. The recruiter always decides.")}</p>
          </div>
        </div>
      )}
    </>
  );
}
