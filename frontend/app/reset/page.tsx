"use client";
import Link from "next/link";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApp } from "@/components/Providers";
import { Alert } from "@/components/ui";

export default function Reset() {
  const { t } = useApp();
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const token = new URLSearchParams(window.location.search).get("token") || "";
    try {
      await api("/auth/reset", { method: "POST", json: { token, password: new FormData(e.currentTarget).get("password") } });
      setDone(true);
    } catch (err) { setError(t(String((err as ApiError).detail))); }
  };
  return (
    <div className="mx-auto max-w-sm space-y-4">
      <h1 className="h1">{t("Choose a new password")}</h1>
      {done ? <><Alert kind="success">{t("Password updated.")}</Alert><Link href="/login" className="btn-primary">{t("Sign in")}</Link></> : (
        <form onSubmit={submit} className="card space-y-3">
          {error && <Alert>{error}</Alert>}
          <div><label className="label" htmlFor="password">{t("Password (10 characters minimum)")}</label><input id="password" name="password" type="password" required minLength={10} className="input" autoComplete="new-password" /></div>
          <button className="btn-primary w-full">{t("Save")}</button>
        </form>
      )}
    </div>
  );
}
