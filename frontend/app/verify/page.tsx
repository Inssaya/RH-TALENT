"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApp } from "@/components/Providers";
import { Alert, Spinner } from "@/components/ui";

export default function Verify() {
  const { t, refresh } = useApp();
  const [state, setState] = useState<"working" | "ok" | "error">("working");
  const [error, setError] = useState("");
  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get("token") || "";
    api("/auth/verify", { method: "POST", json: { token } })
      .then(() => { setState("ok"); refresh(); })
      .catch((e: ApiError) => { setError(String(e.detail)); setState("error"); });
  }, [refresh]);
  return (
    <div className="mx-auto max-w-md space-y-4">
      <h1 className="h1">{t("E-mail confirmation")}</h1>
      {state === "working" && <Spinner />}
      {state === "ok" && <><Alert kind="success">{t("Your e-mail address is confirmed.")}</Alert><Link href="/candidate" className="btn-primary">{t("Continue")}</Link></>}
      {state === "error" && <Alert>{t(error)} {t("Sign in and request a new link from the banner at the top of the page.")}</Alert>}
    </div>
  );
}
