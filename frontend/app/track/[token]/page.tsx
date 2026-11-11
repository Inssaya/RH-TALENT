"use client";
import { use, useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useApp } from "@/components/Providers";
import { Alert, Spinner, StatusChip } from "@/components/ui";
import TrackingDetail, { Tracking } from "@/components/TrackingDetail";

export default function Track({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const { t } = useApp();
  const [data, setData] = useState<Tracking | null>(null);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api<Tracking>(`/public/track/${token}`).then(setData).catch((e: ApiError) => setError(String(e.detail)));
  }, [token]);

  const act = async (path: string, confirmMsg?: string) => {
    if (confirmMsg && !window.confirm(t(confirmMsg))) return;
    try {
      const r = await api(`/public/track/${token}/${path}`, { method: "POST" });
      if (path === "erase") { setData(null); setMsg(t("Your application and your data have been erased.")); return; }
      setData(r);
    } catch (e) { setError(String((e as ApiError).detail)); }
  };
  const exportData = async () => {
    const blob = new Blob([JSON.stringify(await api(`/public/track/${token}/export`), null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = "talentmatch-my-data.json"; a.click();
  };

  if (msg) return <div className="mx-auto max-w-xl"><Alert kind="success">{msg}</Alert></div>;
  if (error) return <div className="mx-auto max-w-xl"><Alert>{t(error)}</Alert></div>;
  if (!data) return <Spinner />;
  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <h1 className="h1">{t("My application")}</h1>
      <div className="card space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <Link href={`/jobs/${data.job.slug}`} className="font-semibold hover:underline">{data.job.title}</Link>
            <p className="muted">{data.job.organization}</p>
          </div>
          <StatusChip status={data.status} />
        </div>
        <TrackingDetail data={data} onHumanReview={() => act("human-review")} />
      </div>
      <div className="card space-y-3">
        <h2 className="h2">{t("Your rights")}</h2>
        <div className="flex flex-wrap gap-2">
          <button className="btn-secondary" onClick={exportData}>{t("Download my data")}</button>
          {data.can_withdraw && <button className="btn-secondary" onClick={() => act("withdraw", "Withdraw this application?")}>{t("Withdraw my application")}</button>}
          <button className="btn-danger" onClick={() => act("erase", "Erase this application and all related data? This cannot be undone.")}>{t("Erase my data")}</button>
        </div>
      </div>
    </div>
  );
}
