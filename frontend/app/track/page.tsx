"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApp } from "@/components/Providers";
import { Alert } from "@/components/ui";

/** Lost tracking link: the answer is always the same, whether or not the address has applications. */
export default function LostLink() {
  const { t } = useApp();
  const [sent, setSent] = useState(false);
  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    await api("/public/track/resend", { method: "POST", json: { email: new FormData(e.currentTarget).get("email") } }).catch(() => {});
    setSent(true);
  };
  return (
    <div className="mx-auto max-w-md space-y-4">
      <h1 className="h1">{t("I lost my tracking link")}</h1>
      {sent ? <Alert kind="success">{t("If this address has applications, an e-mail with the links has been sent.")}</Alert> : (
        <form onSubmit={submit} className="card space-y-3">
          <p className="muted">{t("Enter the e-mail address you applied with. We only ever send the links to that address.")}</p>
          <div><label className="label" htmlFor="email">{t("E-mail")}</label><input id="email" name="email" type="email" required className="input" autoComplete="email" /></div>
          <button className="btn-primary w-full">{t("Send me my links")}</button>
        </form>
      )}
    </div>
  );
}
