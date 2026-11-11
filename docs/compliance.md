# Compliance

This is an engineering summary, not legal advice. Have a lawyer review the notices, the employer terms and the
processing register before opening the platform to the public.

## Roles

| Processing | Controller | Processor |
|---|---|---|
| Applications to a job | The recruiting company | The platform operator (needs an article 28 contract in the employer terms) |
| Candidate account, recommendations, job alerts, security and audit logs | The platform operator | Hosting, e-mail and AI providers |

Under the EU AI Act the platform operator is the **provider** of the system and each recruiting company a **deployer**.

## Lawful bases

| Processing | Basis |
|---|---|
| Application and its analysis | Steps at the candidate's request before a contract (GDPR 6.1.b) |
| Candidate account and profile | Performance of the service (6.1.b) |
| Visibility to recruiters, weekly job alerts | Consent (6.1.a), recorded with notice version and time, withdrawable in the profile |
| Security, audit log (IP address truncated) | Legitimate interest (6.1.f) |

Data minimisation: no photo, date of birth or nationality is requested; sensitive attributes are never inferred and
never enter the score.

## What the code provides

| Obligation | Where |
|---|---|
| No decision solely automated (GDPR art. 22, AI Act art. 14) | Only a recruiter can reject (`services.transition`); grouped rejection needs a reviewed list; a candidate can request a human review, which blocks batch rejection |
| Information on the logic | Public page "How the AI works", per-candidate explanation with quoted evidence |
| Access and portability | Candidate: `GET /api/candidate/export`; account-less: tracking page "Download my data" |
| Erasure | Tracking page, candidate account, or admin `execute_erasure`: deletes rows, profile, embedding, score and file |
| Rectification | Candidate profile editing |
| Consent records | `consent_records` (type, notice version, granted, time) |
| Retention | `RETENTION_MONTHS` (default 24): nightly purge of applications of closed jobs |
| Audit (AI Act art. 12) | Hash-chained, append-only `audit_events` (26 event kinds), admin screen and `audit-verify` |
| Human oversight, accuracy, robustness (art. 14, 15) | Explanations, evidence verification, hidden-text and injection removal, evaluation bench |
| Records of AI use (supervision, art. 72) | Admin *AI supervision*: calls, degraded rate, cost, recruiter disagreements |

## What the operator must do

1. **Complete the bracketed items** in `frontend/app/legal/privacy/page.tsx` (operator identity and contact, sub-processor
   list and locations) in each language, and have them reviewed. Bump `NOTICE_VERSION` when the text changes.
2. **Employer terms** with the article 28 processor clause, and a short notice for recruiters on their duties as deployers
   (use according to instructions, human oversight by trained people, inform candidates and staff representatives where required).
3. **Sub-processor register and data processing agreements** with every provider actually enabled. Typical set:

   | Provider | Purpose | Notes |
   |---|---|---|
   | Hosting (e.g. Hetzner) | VM, storage | EU region |
   | Mistral AI | LLM, OCR | Optional; receives CV text without name and contact details; request no-retention and no-training terms |
   | E-mail (e.g. Brevo) | Transactional e-mail | EU |
   | Backups (e.g. Backblaze B2) | Encrypted off-site backups | EU region |
   | Sentry, Grafana, Langfuse | Monitoring | Only if enabled; EU region |
   | Cloudflare Turnstile | Captcha | Not wired in the UI yet |
4. **Data Protection Impact Assessment**: mandatory (large-scale automated evaluation of people). Use the CNIL PIA tool; update it
   before launch and when the scoring changes. Not done yet.
5. **Register of processing activities** (kept outside the code base).
6. **Breach procedure**: see `docs/runbook.md` procedure 8 (72-hour notification).
7. **Morocco**: if the operator or users are in Morocco, Law 09-08 and a CNDP declaration or authorisation also apply.
   GDPR remains the design reference.

## EU AI Act position

Recruitment and candidate evaluation are high-risk systems (Annex III, point 4.a). The obligations apply from
**2 December 2027** under Regulation (EU) 2026/1744 (check this date before relying on it); the prohibited practices of
article 5 already apply. The design applies the requirements now. Out of scope of the code and required before a real
commercial launch: a formal quality management system, conformity assessment, registration in the EU database.

Excluded by design: emotion recognition, biometric categorisation, inference of protected attributes.

## Known fairness limits

- Fairness is checked on synthetic counterfactual pairs (same CV, another name), which the CI evaluation enforces
  (score gap below 0.03). Demographic data is deliberately not collected, so real-world disparate impact is **not measured**.
- Extraction quality may be lower for scanned CVs and for Arabic. Low-quality CVs go to a "to check" lane instead of being
  down-ranked, and all candidates stay visible.
- Publish a model card (intended use, excluded uses, data, metrics with confidence intervals, limits, contact) once a
  human-annotated evaluation exists. Not written yet.
