"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApp } from "@/components/Providers";
import { Alert } from "@/components/ui";

export default function Forgot() {
  const { t } = useApp();
  const [sent, setSent] = useState(false);
  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    await api("/auth/forgot", { method: "POST", json: { email: new FormData(e.currentTarget).get("email") } }).catch(() => {});
    setSent(true);
  };
  return (
    <div className="mx-auto max-w-sm space-y-4">
      <h1 className="h1">{t("Forgot password?")}</h1>
      {sent ? <Alert kind="success">{t("If an account exists for this address, a reset link has been sent.")}</Alert> : (
        <form onSubmit={submit} className="card space-y-3">
          <div><label className="label" htmlFor="email">{t("E-mail")}</label><input id="email" name="email" type="email" required className="input" /></div>
          <button className="btn-primary w-full">{t("Send the reset link")}</button>
        </form>
      )}
    </div>
  );
}
