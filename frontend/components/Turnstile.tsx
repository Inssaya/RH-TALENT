"use client";
import { useCallback, useEffect, useRef } from "react";

const SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY || "";

export function turnstileEnabled() { return !!SITE_KEY; }

declare global {
  interface Window { turnstile?: { render(el: HTMLElement, opts: Record<string, unknown>): string; reset(id: string): void; remove(id: string): void } }
}

export default function Turnstile({ onToken }: { onToken: (token: string) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const widgetId = useRef<string | null>(null);

  const render = useCallback(() => {
    if (!ref.current || !window.turnstile || widgetId.current) return;
    widgetId.current = window.turnstile.render(ref.current, {
      sitekey: SITE_KEY, callback: onToken, "refresh-expired": "auto",
    });
  }, [onToken]);

  useEffect(() => {
    if (!SITE_KEY) return;
    if (window.turnstile) { render(); return; }
    const existing = document.querySelector('script[src*="turnstile"]');
    if (!existing) {
      const s = document.createElement("script");
      s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?onload=__tcb&render=explicit";
      s.async = true;
      document.head.appendChild(s);
    }
    (window as unknown as Record<string, unknown>).__tcb = render;
    return () => { delete (window as unknown as Record<string, unknown>).__tcb; };
  }, [render]);

  if (!SITE_KEY) return null;
  return <div ref={ref} />;
}
