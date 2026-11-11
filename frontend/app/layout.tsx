import type { Metadata } from "next";
import Link from "next/link";
import Header from "@/components/Header";
import Providers from "@/components/Providers";
import VerifyBanner from "@/components/VerifyBanner";
import { translate } from "@/lib/i18n";
import { getLocale } from "@/lib/locale";
import { SITE_URL } from "@/lib/api";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: "TalentMatch", template: "%s · TalentMatch" },
  description: "Recruitment platform with explainable AI screening. The AI sorts and explains; a human always decides.",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await getLocale();
  const t = (k: string) => translate(locale, k);
  return (
    <html lang={locale} dir={locale === "ar" ? "rtl" : "ltr"}>
      <body className="flex min-h-screen flex-col">
        <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:m-2 focus:rounded focus:bg-white focus:p-2">{t("Skip to content")}</a>
        <Providers initialLocale={locale}>
          <Header />
          <VerifyBanner />
          <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">{children}</main>
          <footer className="border-t border-slate-200 bg-white">
            <div className="mx-auto flex max-w-6xl flex-wrap gap-x-6 gap-y-2 px-4 py-5 text-sm text-slate-500">
              <span>© TalentMatch</span>
              <Link href="/how-ai-works" className="hover:underline">{t("How the AI works")}</Link>
              <Link href="/legal/privacy" className="hover:underline">{t("Privacy and your rights")}</Link>
              <Link href="/help" className="hover:underline">{t("Help")}</Link>
            </div>
          </footer>
        </Providers>
      </body>
    </html>
  );
}
