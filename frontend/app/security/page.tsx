"use client";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApp } from "@/components/Providers";
import { Alert, Spinner } from "@/components/ui";

/** Two-factor enrolment. Organization and platform administrators are sent here until it is done. */
export default function Security() {
  const { t, user, refresh } = useApp();
  const [setup, setSetup] = useState<{ secret: string; uri: string } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { if (user === null) window.location.href = "/login?next=/security"; }, [user]);
  useEffect(() => {
    if (user && !user.totp_enabled) api("/auth/totp/setup", { method: "POST" }).then(setSetup).catch((e: ApiError) => setError(String(e.detail)));
  }, [user]);
  if (!user) return <Spinner />;
  if (user.totp_enabled) {
    return (
      <div className="mx-auto max-w-md space-y-4">
        <h1 className="h1">{t("Two-factor authentication")}</h1>
        <Alert kind="success">{t("Two-factor authentication is active on your account.")}</Alert>
        <a className="btn-primary" href={user.role === "platform_admin" ? "/admin" : user.role === "recruiter" ? "/recruiter" : "/candidate"}>{t("Continue")}</a>
      </div>
    );
  }
  const activate = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault(); setError("");
    try {
      await api("/auth/totp/enable", { method: "POST", json: { code: new FormData(e.currentTarget).get("code") } });
      await refresh();
    } catch (err) { setError(t(String((err as ApiError).detail))); }
  };
  return (
    <div className="mx-auto max-w-md space-y-4">
      <h1 className="h1">{t("Set up two-factor authentication")}</h1>
      {user.totp_setup_required && <Alert kind="warning">{t("Mandatory for organization administrators.")} {t("Your account stays locked until you finish this step.")}</Alert>}
      {error && <Alert>{error}</Alert>}
      {!setup ? <Spinner /> : (
        <form onSubmit={activate} className="card space-y-3">
          <p className="text-sm">{t("Add this key to your authenticator app, then enter the 6-digit code.")}</p>
          <code id="totp-secret" className="block break-all rounded bg-slate-100 p-2 text-sm">{setup.secret}</code>
          <p className="muted break-all">{setup.uri}</p>
          <label className="label" htmlFor="code">{t("Authentication code")}</label>
          <input id="code" name="code" required inputMode="numeric" autoComplete="one-time-code" className="input" placeholder="123456" />
          <button className="btn-primary w-full">{t("Activate")}</button>
        </form>
      )}
    </div>
  );
}
