import { cookies } from "next/headers";
import { Locale, translate } from "./i18n";

export async function getLocale(): Promise<Locale> {
  const v = (await cookies()).get("tm_locale")?.value;
  return v === "en" || v === "ar" ? v : "fr";
}

export async function getT() {
  const locale = await getLocale();
  return { locale, t: (k: string, vars?: Record<string, string | number>) => translate(locale, k, vars) };
}
