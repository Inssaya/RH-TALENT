import { ar } from "./dict.ar";
import { fr } from "./dict.fr";

export type Locale = "fr" | "en" | "ar";

const DICT: Record<Locale, Record<string, string>> = { fr, ar, en: {} };

/** The English sentence is the key. English returns it unchanged; fr and ar fall back to the key. */
export function translate(locale: Locale, key: string, vars?: Record<string, string | number>): string {
  const text = locale === "en" ? key : DICT[locale][key] ?? key;
  return vars ? text.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m)) : text;
}
