export type Draft = {
  title: string; description: string; missions: string[]; city: string; country: string;
  remote: "onsite" | "hybrid" | "remote"; contract_type: string; min_years_experience: number; education_level: number;
  languages: { code: string; level: string }[]; skills_required: string[]; skills_nice: string[];
  requirements: { id: string; text: string; type: "requirement" | "knockout" }[];
  knockouts: { kind: string; value: string | number; level?: string | null }[];
  salary_min: number | null; salary_max: number | null; currency: string; lang: "fr" | "en" | "ar";
};
export const EMPTY_DRAFT: Draft = {
  title: "", description: "", missions: [], city: "", country: "", remote: "onsite", contract_type: "",
  min_years_experience: 0, education_level: 0, languages: [], skills_required: [], skills_nice: [], requirements: [],
  knockouts: [], salary_min: null, salary_max: null, currency: "", lang: "fr",
};
export type Quality = { score: number; publishable: boolean; warnings: { code: string; severity: string; term?: string }[] };
export type Job = {
  id: string; slug: string; status: string; title: string; city: string; country: string; remote: string;
  contract_type: string; version: number; blind_mode: boolean; applications: number;
  policy: { mode: "TOP_N" | "THRESHOLD" | "TOP_N_FLOOR"; n: number; threshold: number; cap: number | null };
  weights: Record<string, number>; published_at: string | null; created_at: string; draft?: Draft; quality?: Quality;
};
export type Row = {
  id: string; name: string; email: string | null; masked: boolean; status: string; processing: string; pinned: boolean;
  title: string; years: number; score: number | null; subscores: Record<string, number> | null; knockout_failed: boolean;
  flags: string[]; top_missing: string[]; human_review_requested: boolean; opened: boolean; pending_rejection: boolean;
  submitted_at: string; quality: number | null;
};
export const QUALITY_LABEL: Record<string, string> = {
  missing_title: "The title is missing", missing_description: "The description is too short (200 characters minimum)",
  missing_location: "Add a city and a country, or choose remote", missing_contract_type: "Choose a contract type",
  missing_skills_required: "Add at least one required skill", bias_age: "Wording that may discriminate by age",
  bias_gender: "Gendered wording", bias_origin: "Wording that may discriminate by origin",
  bias_jargon: "Jargon that discourages some candidates", bias_other: "Criterion unrelated to the job",
  too_many_required_skills: "More than 10 required skills: move some to nice-to-have",
  no_requirements: "No requirement listed: explanations will be less precise", no_salary: "No salary range (optional, but it attracts more candidates)",
  high_experience_bar: "Very high experience requirement",
};
export const SUBSCORE_LABEL: Record<string, string> = {
  skills: "Skills", requirements: "Requirements", experience: "Experience", semantic: "Overall similarity",
  education: "Education", languages: "Languages", location: "Location",
};
