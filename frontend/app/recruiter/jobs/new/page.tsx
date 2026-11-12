"use client";
import { useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApp } from "@/components/Providers";
import JobForm, { QualityReport } from "@/components/JobForm";
import { Alert, Spinner, useGuard } from "@/components/ui";
import { Draft, EMPTY_DRAFT, Quality } from "@/lib/types";

type Msg = { role: "assistant" | "user"; text: string };
type Channel = "chat" | "paste" | "file" | "form";

export default function NewJob() {
  const { t, locale } = useApp();
  const user = useGuard("recruiter");
  const [channel, setChannel] = useState<Channel>("chat");
  const [draft, setDraft] = useState<Draft>({ ...EMPTY_DRAFT, lang: locale });
  const [quality, setQuality] = useState<Quality | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [asked, setAsked] = useState<string | null>("title");
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [listening, setListening] = useState(false);
  const recRef = useRef<any>(null);

  if (!user) return <Spinner />;
  const fail = (e: unknown) => setError(e instanceof ApiError ? t(String(e.detail)) : t("Something went wrong"));

  const send = async () => {
    const message = input.trim();
    if (!message) return;
    setInput(""); setBusy(true); setError("");
    setMessages((m) => [...m, { role: "user", text: message }]);
    try {
      const r = await api("/jobs/chat", { method: "POST", json: { draft, message, asked_field: asked, locked: [] } });
      setDraft(r.draft); setQuality(r.quality); setAsked(r.asked_field);
      setMessages((m) => [...m, { role: "assistant", text: r.reply }]);
    } catch (e) { fail(e); } finally { setBusy(false); }
  };

  // Voice dictation uses the browser's speech recognition: the audio never reaches our servers.
  const dictate = () => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) { setError(t("Voice dictation is not supported by this browser.")); return; }
    if (listening) { recRef.current?.stop(); return; }
    const rec = new SR();
    rec.lang = locale === "ar" ? "ar-MA" : locale === "en" ? "en-US" : "fr-FR";
    rec.interimResults = false;
    rec.onresult = (ev: any) => setInput((v) => (v + " " + Array.from(ev.results).map((r: any) => r[0].transcript).join(" ")).trim());
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recRef.current = rec; setListening(true); rec.start();
  };

  const extract = async (body: RequestInit & { json?: unknown }) => {
    setBusy(true); setError("");
    try {
      const r = await api("/jobs/extract", { method: "POST", ...body });
      setDraft(r.draft); setQuality(r.quality); setChannel("form");
    } catch (e) { fail(e); } finally { setBusy(false); }
  };

  const check = async () => { try { setQuality(await api("/jobs/quality", { method: "POST", json: draft })); } catch (e) { fail(e); } };

  const save = async (publish: boolean) => {
    setBusy(true); setError("");
    try {
      const job = await api("/jobs", { method: "POST", json: draft });
      if (publish) await api(`/jobs/${job.id}/publish`, { method: "POST" });
      window.location.href = `/recruiter/jobs/${job.id}`;
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) await check();
      fail(e); setBusy(false);
    }
  };

  const tabs: [Channel, string][] = [["chat", "Assistant"], ["paste", "Paste a text"], ["file", "Import a file"], ["form", "Form"]];
  return (
    <div className="space-y-5">
      <h1 className="h1">{t("New job post")}</h1>
      <p className="muted">{t("Every channel fills the same form. Review it before publishing.")}</p>
      <div className="flex flex-wrap gap-2" role="tablist">
        {tabs.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={channel === k} className={channel === k ? "btn-primary" : "btn-secondary"} onClick={() => setChannel(k)}>{t(label)}</button>
        ))}
      </div>
      {error && <Alert>{error}</Alert>}
      <div className="grid gap-5 lg:grid-cols-[1fr_20rem]">
        <div className="card">
          {channel === "chat" && (
            <div className="space-y-3">
              <div className="max-h-96 min-h-40 space-y-2 overflow-y-auto" aria-live="polite">
                <div className="max-w-[85%] rounded-lg bg-slate-100 px-3 py-2 text-sm">{t("Hello! Tell me about the job you want to fill: title, missions, location, contract, key skills. You can also dictate.")}</div>
                {messages.map((m, i) => (
                  <div key={i} className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${m.role === "user" ? "ms-auto bg-brand-600 text-white" : "bg-slate-100"}`}>{m.text}</div>
                ))}
                {busy && <div className="muted">…</div>}
              </div>
              <div className="flex gap-2">
                <label className="sr-only" htmlFor="chat">{t("Your message")}</label>
                <textarea id="chat" className="input min-h-12 flex-1" value={input} onChange={(e) => setInput(e.target.value)} placeholder={t("Your message")}
                          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
                <button type="button" className={listening ? "btn-danger" : "btn-secondary"} onClick={dictate} aria-pressed={listening} title={t("Dictate")}>{listening ? "■" : "🎤"}</button>
                <button className="btn-primary" onClick={send} disabled={busy || !input.trim()}>{t("Send")}</button>
              </div>
              <button className="text-sm text-brand-700 underline" onClick={() => setChannel("form")}>{t("Review the form")} →</button>
            </div>
          )}
          {channel === "paste" && (
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); extract({ json: { text: new FormData(e.currentTarget).get("text") } }); }}>
              <label className="label" htmlFor="text">{t("Paste your existing job description")}</label>
              <textarea id="text" name="text" required minLength={30} className="input min-h-64" />
              <button className="btn-primary" disabled={busy}>{t("Extract the job post")}</button>
            </form>
          )}
          {channel === "file" && (
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); extract({ body: new FormData(e.currentTarget) }); }}>
              <label className="label" htmlFor="file">{t("Job description file (PDF, Word, text)")}</label>
              <input id="file" name="file" type="file" required className="input" accept=".pdf,.docx,.odt,.rtf,.txt" />
              <button className="btn-primary" disabled={busy}>{t("Extract the job post")}</button>
            </form>
          )}
          {channel === "form" && <JobForm draft={draft} onChange={setDraft} />}
        </div>
        <aside className="space-y-4">
          <div className="card space-y-3">
            <h2 className="h2">{t("Preview")}</h2>
            <dl className="space-y-1 text-sm">
              <div><dt className="muted inline">{t("Job title")}: </dt><dd className="inline font-medium">{draft.title || "—"}</dd></div>
              <div><dt className="muted inline">{t("Location")}: </dt><dd className="inline">{[draft.city, draft.country].filter(Boolean).join(", ") || (draft.remote === "remote" ? t("Remote") : "—")}</dd></div>
              <div><dt className="muted inline">{t("Contract")}: </dt><dd className="inline">{draft.contract_type || "—"}</dd></div>
              <div><dt className="muted inline">{t("Required skills")}: </dt><dd className="inline">{draft.skills_required.join(", ") || "—"}</dd></div>
              <div><dt className="muted inline">{t("Requirements")}: </dt><dd className="inline">{draft.requirements.length}</dd></div>
            </dl>
            <button className="btn-secondary w-full" onClick={check}>{t("Check quality and bias")}</button>
            <QualityReport quality={quality} />
          </div>
          <div className="card space-y-2">
            <button className="btn-primary w-full" onClick={() => save(true)} disabled={busy || !user.email_verified}>{t("Publish")}</button>
            {!user.email_verified && <Alert kind="warning">{t("Confirm your e-mail address to publish a job. Drafts are always allowed.")}</Alert>}
            <button className="btn-secondary w-full" onClick={() => save(false)} disabled={busy}>{t("Save as draft")}</button>
          </div>
        </aside>
      </div>
    </div>
  );
}
