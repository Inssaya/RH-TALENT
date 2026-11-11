"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApp } from "./Providers";

/** Shown to signed-in users whose e-mail address is not confirmed yet. */
export default function VerifyBanner() {
  const { t, user } = useApp();
  const [sent, setSent] = useState(false);
  if (!user || user.email_verified || user.role === "platform_admin") return null;
  return (
    <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900" role="status">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3">
        <span>{t("Please confirm your e-mail address: we sent you a link.")}</span>
        {sent
          ? <span className="font-medium">{t("Link sent.")}</span>
          : <button className="font-medium underline" onClick={() => api("/auth/resend-verification", { method: "POST" }).then(() => setSent(true)).catch(() => setSent(false))}>{t("Send the link again")}</button>}
      </div>
    </div>
  );
}
