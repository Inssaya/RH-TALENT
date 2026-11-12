"use client";
import Link from "next/link";
import { useApp } from "./Providers";
import { Locale } from "@/lib/i18n";

export default function Header() {
  const { t, user, logout, locale, setLocale } = useApp();
  const home = user?.role === "recruiter" ? "/recruiter" : user?.role === "platform_admin" ? "/admin" : "/candidate";
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
        <Link href="/" className="text-lg font-bold tracking-tight text-brand-700">Talent<span className="text-ink">Match</span></Link>
        <nav className="flex flex-1 flex-wrap items-center gap-4 text-sm" aria-label="Main">
          <Link href="/jobs" className="hover:text-brand-700">{t("Jobs")}</Link>
          {user?.role === "recruiter" && <Link href="/recruiter" className="hover:text-brand-700">{t("My job posts")}</Link>}
          {user?.role === "recruiter" && <Link href="/recruiter/org" className="hover:text-brand-700">{t("Organization")}</Link>}
          {user?.role === "candidate" && <Link href="/candidate" className="hover:text-brand-700">{t("My space")}</Link>}
          {user?.role === "platform_admin" && <Link href="/admin" className="hover:text-brand-700">{t("Administration")}</Link>}
          <Link href="/how-ai-works" className="hover:text-brand-700">{t("How the AI works")}</Link>
        </nav>
        <div className="flex items-center gap-3 text-sm">
          <select aria-label={t("Language")} className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs"
                  value={locale} onChange={(e) => setLocale(e.target.value as Locale)}>
            <option value="fr">Français</option>
            <option value="en">English</option>
            <option value="ar">العربية</option>
          </select>
          {user === undefined ? null : user ? (
            <>
              <Link href={home} className="hidden font-medium sm:inline">{user.full_name}</Link>
              <Link href="/account" className="hover:text-brand-700">{t("Account")}</Link>
              <button className="btn-secondary" onClick={logout}>{t("Sign out")}</button>
            </>
          ) : (
            <>
              <Link href="/login" className="btn-secondary">{t("Sign in")}</Link>
              <Link href="/register?role=recruiter" className="btn-primary">{t("Post a job")}</Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
