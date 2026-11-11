import type { MetadataRoute } from "next";
import { SITE_URL, serverApi } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const jobs = (await serverApi<{ slug: string; at: string | null }[]>("/public/sitemap", 600)) || [];
  return [
    { url: SITE_URL, changeFrequency: "daily" },
    { url: `${SITE_URL}/jobs`, changeFrequency: "hourly" },
    ...jobs.map((j) => ({ url: `${SITE_URL}/jobs/${j.slug}`, lastModified: j.at || undefined })),
  ];
}
