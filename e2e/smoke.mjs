// End-to-end smoke test: six journeys against a running stack, driven by a real browser.
//
//   BASE_URL=http://localhost ADMIN_EMAIL=... ADMIN_PASSWORD=... node e2e/smoke.mjs
//
// Needs the `playwright` package (preinstalled in the sandbox; elsewhere: npm i -D playwright).
// ADMIN_TOTP_SECRET is only needed when the admin already enrolled two-factor in an earlier run.
// The UI is checked in French, the default locale. Exits 1 on the first failed journey.
// Start the stack with RATE_LIMIT_ENABLED=false: the run registers several accounts from one IP,
// which the production limit (5 registrations/hour/IP) would block.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

import crypto from "node:crypto";
import { execSync } from "node:child_process";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const BASE = process.env.BASE_URL || "http://localhost";
const ADMIN_EMAIL = process.env.ADMIN_EMAIL;
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD;
const dir = path.dirname(fileURLToPath(import.meta.url));
const CV = path.join(dir, "fixtures/cv-lina.pdf");
const JOB_TEXT = (await import("node:fs")).readFileSync(path.join(dir, "fixtures/job-data-scientist.txt"), "utf8");
const run = Date.now().toString(36);
const PASSWORD = "correct-horse-battery-2026";

// ---- helpers: TOTP codes (RFC 6238) and reading e-mails from the stack logs (no SMTP in tests)
function totp(secretB32) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const ch of secretB32.replace(/=+$/, "").toUpperCase()) bits += alphabet.indexOf(ch).toString(2).padStart(5, "0");
  const key = Buffer.from(bits.match(/.{8}/g).map((b) => parseInt(b, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const h = crypto.createHmac("sha1", key).update(counter).digest();
  const o = h[19] & 15;
  return String(((h.readUInt32BE(o) & 0x7fffffff) % 1_000_000)).padStart(6, "0");
}

// Without SMTP the API logs every e-mail. E2E_MAIL_CMD can point at another log source.
function verificationToken(email) {
  const cmd = process.env.E2E_MAIL_CMD || "docker compose logs --no-color --tail 600 api worker";
  const logs = execSync(cmd, { encoding: "utf8", maxBuffer: 20_000_000 });
  const at = logs.lastIndexOf(`to=${email}`);
  assert.ok(at >= 0, `no e-mail logged for ${email}`);
  const m = /verify\?token=([\w.-]+)/.exec(logs.slice(at));
  assert.ok(m, `no verification link in the e-mail for ${email}`);
  return m[1];
}

// Enrol two-factor on the /security page; returns the secret.
async function enrolTotp(page) {
  await page.waitForURL("**/security");
  const secret = (await page.locator("#totp-secret").innerText()).trim();
  await page.getByLabel("Code d'authentification").fill(totp(secret));
  await page.getByRole("button", { name: "Activer" }).click();
  await page.getByText("L'authentification à deux facteurs est active").waitFor();
  return secret;
}

const browser = await chromium.launch();
const results = [];
let state = {};

async function newPage() {
  const ctx = await browser.newContext({ baseURL: BASE, viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  page.setDefaultTimeout(20000);
  page.on("pageerror", (e) => console.error("  [pageerror]", e.message));
  if (process.env.E2E_DEBUG) page.on("response", (r) => r.status() >= 400 && console.error("  [http]", r.status(), r.url()));
  return page;
}

async function journey(name, fn) {
  process.stdout.write(`- ${name} ... `);
  try {
    await fn();
    results.push([name, true]);
    console.log("ok");
  } catch (e) {
    results.push([name, false]);
    console.log("FAILED\n   ", e.message.split("\n")[0]);
    if (process.env.E2E_DEBUG) console.error(e);
    await browser.close();
    process.exit(1);
  }
}

// Poll an API-backed screen until the asynchronous scoring has finished.
async function waitFor(page, fn, what, tries = 40) {
  for (let i = 0; i < tries; i++) {
    if (await fn()) return;
    await page.waitForTimeout(1500);
    await page.reload();
    await page.waitForLoadState("networkidle");
  }
  const text = (await page.locator("main").innerText().catch(() => "")).replace(/\s+/g, " ").slice(0, 400);
  throw new Error(`timeout waiting for ${what}. Page says: ${text}`);
}

const recruiter = await newPage();

await journey("1. Employer registers, creates a job from pasted text, publishes it", async () => {
  await recruiter.goto("/register?role=recruiter");
  await recruiter.getByLabel("Nom complet").fill("Samira Alaoui");
  await recruiter.getByLabel("Nom de l'entreprise").fill(`Atlas Test ${run}`);
  await recruiter.getByLabel("E-mail").fill(`samira-${run}@e2e.example.org`);
  await recruiter.getByLabel("Mot de passe (10 caractères minimum)").fill(PASSWORD);
  await recruiter.getByRole("checkbox").check();
  await recruiter.getByRole("button", { name: "Créer mon compte" }).click();
  // An organization admin is locked to the two-factor setup page until it is done.
  await enrolTotp(recruiter);
  // Publishing needs a confirmed address: follow the link from the e-mail.
  await recruiter.goto(`/verify?token=${verificationToken(`samira-${run}@e2e.example.org`)}`);
  await recruiter.getByText("Votre adresse e-mail est confirmée.").waitFor();
  await recruiter.goto("/recruiter");
  await recruiter.getByRole("link", { name: "+ Nouvelle offre" }).waitFor();
  await recruiter.getByRole("link", { name: "+ Nouvelle offre" }).click();
  await recruiter.getByRole("tab", { name: "Coller un texte" }).click();
  await recruiter.getByLabel("Collez votre annonce existante").fill(JOB_TEXT);
  await recruiter.getByRole("button", { name: "Extraire l'offre" }).click();
  await recruiter.getByLabel("Intitulé du poste *").waitFor();
  assert.equal(await recruiter.getByLabel("Intitulé du poste *").inputValue(), "Data Scientist");
  assert.equal(await recruiter.getByLabel("Ville", { exact: true }).inputValue(), "Casablanca");
  await recruiter.getByRole("button", { name: "Vérifier la qualité et les biais" }).click();
  await recruiter.getByText(/Qualité de l'offre/).waitFor();
  await recruiter.getByRole("button", { name: "Publier", exact: true }).click();
  await recruiter.waitForURL(/\/recruiter\/jobs\/[0-9a-f-]{36}$/);
  state.jobUrl = recruiter.url();
  const href = await recruiter.getByRole("link", { name: /Page publique/ }).getAttribute("href");
  state.slug = href.split("/jobs/")[1];
  assert.ok(state.slug);
});

await journey("2. Visitor applies without an account with a PDF and opens the tracking link", async () => {
  const visitor = await newPage();
  await visitor.goto("/");
  await visitor.getByText("Dernières offres").waitFor();
  await visitor.goto(`/jobs/${state.slug}`);
  assert.match(await visitor.locator('script[type="application/ld+json"]').innerText(), /"JobPosting"/);
  await visitor.getByLabel("Nom complet").fill("Lina Benali");
  await visitor.getByLabel("E-mail").fill(`lina-${run}@e2e.example.org`);
  await visitor.locator("#file").setInputFiles(CV);
  await visitor.getByRole("checkbox").check();
  await visitor.getByRole("button", { name: "Envoyer ma candidature" }).click();
  await visitor.getByText(/Candidature reçue/).waitFor();
  await visitor.getByRole("link", { name: "Suivre ma candidature" }).click();
  await visitor.waitForURL(/\/track\//);
  await visitor.getByText("En cours d'examen").first().waitFor();
  state.trackUrl = visitor.url();
  await visitor.context().close();
});

await journey("3. Recruiter reads the explained shortlist, changes N, rejects with a reason, cancels, rejects again", async () => {
  await recruiter.goto(state.jobUrl);
  await waitFor(recruiter, async () => (await recruiter.getByRole("link", { name: "Lina Benali" }).count()) > 0
    && (await recruiter.getByText("Analyse en cours", { exact: false }).count()) === 0, "scored application");
  await recruiter.getByText("Shortlist", { exact: true }).first().waitFor();
  await recruiter.getByRole("button", { name: "5", exact: true }).click();   // shortlist size is a setting
  await recruiter.getByRole("button", { name: "20", exact: true }).click();
  await recruiter.getByRole("link", { name: "Lina Benali" }).click();
  await recruiter.getByText("Pourquoi ce score").waitFor();
  await recruiter.getByText(/Exigences, avec preuves/).waitFor();
  await recruiter.getByText("Ce qui ferait monter le score").waitFor();
  state.appUrl = recruiter.url();
  await recruiter.getByRole("button", { name: "Refuser…" }).click();
  await recruiter.getByRole("button", { name: "Confirmer le refus" }).click();
  await recruiter.getByRole("button", { name: "Annuler le refus" }).waitFor();
  await recruiter.getByRole("button", { name: "Annuler le refus" }).click();
  await recruiter.getByText("Refus annulé.").waitFor();
  await recruiter.getByRole("button", { name: "Refuser…" }).click();
  await recruiter.getByRole("button", { name: "Confirmer le refus" }).click();
  await recruiter.getByRole("button", { name: "Annuler le refus" }).waitFor();
});

await journey("4. Candidate registers, uploads a CV, gets recommendations, applies in one click", async () => {
  const cand = await newPage();
  await cand.goto("/register");
  await cand.getByLabel("Nom complet").fill("Karim Candidat");
  await cand.getByLabel("E-mail").fill(`karim-${run}@e2e.example.org`);
  await cand.getByLabel("Mot de passe (10 caractères minimum)").fill(PASSWORD);
  await cand.getByRole("checkbox").check();
  await cand.getByRole("button", { name: "Créer mon compte" }).click();
  await cand.waitForURL("**/candidate");
  await cand.getByText("Veuillez confirmer votre adresse e-mail").waitFor();     // banner for unverified accounts
  await cand.goto(`/verify?token=${verificationToken(`karim-${run}@e2e.example.org`)}`);
  await cand.getByText("Votre adresse e-mail est confirmée.").waitFor();
  await cand.goto("/candidate");
  assert.equal(await cand.getByText("Veuillez confirmer votre adresse e-mail").count(), 0);
  await cand.locator("#cv").setInputFiles(CV);
  await cand.getByText(/CV analysé/).waitFor();
  await cand.getByRole("button", { name: "Enregistrer et valider" }).click();
  await cand.getByText("Profil enregistré.").waitFor();
  await cand.getByRole("heading", { name: "Pour vous" }).waitFor();
  const card = cand.locator(`a[href="/jobs/${state.slug}"]`).first();
  await card.waitFor();
  await card.click();
  await cand.getByRole("button", { name: "Postuler en un clic" }).click();
  await cand.getByText(/Candidature reçue/).waitFor();
  await cand.goto("/candidate");
  await cand.getByText("Data Scientist").first().waitFor();
  // account screen: change the password; the caller stays signed in
  await cand.goto("/account");
  await cand.getByLabel("Mot de passe actuel").fill(PASSWORD);
  await cand.getByLabel("Nouveau mot de passe (10 caractères minimum)").fill("another-long-password-2026");
  await cand.getByRole("button", { name: "Changer mon mot de passe" }).click();
  await cand.getByText("Mot de passe modifié.").waitFor();
  await cand.goto("/candidate");
  await cand.getByRole("heading", { name: "Mon espace" }).waitFor();
  await cand.context().close();
});

await journey("4b. Visitor who lost the tracking link gets the same answer for any address", async () => {
  const v = await newPage();
  await v.goto("/track");
  await v.getByLabel("E-mail").fill(`lina-${run}@e2e.example.org`);
  await v.getByRole("button", { name: "M'envoyer mes liens" }).click();
  await v.getByText(/Si cette adresse a des candidatures/).waitFor();
  await v.goto("/track");
  await v.getByLabel("E-mail").fill(`nobody-${run}@e2e.example.org`);
  await v.getByRole("button", { name: "M'envoyer mes liens" }).click();
  await v.getByText(/Si cette adresse a des candidatures/).waitFor();
  const logs = execSync(process.env.E2E_MAIL_CMD || "docker compose logs --no-color --tail 800 api worker", { encoding: "utf8", maxBuffer: 20_000_000 });
  assert.ok(logs.includes(`to=lina-${run}@e2e.example.org subject=TalentMatch : vos liens de suivi`), "the address on file received the e-mail");
  assert.ok(!logs.includes(`to=nobody-${run}@e2e.example.org`), "an unknown address received nothing");
  await v.context().close();
});

await journey("5. Platform admin opens every tab and verifies the audit chain", async () => {
  assert.ok(ADMIN_EMAIL && ADMIN_PASSWORD, "ADMIN_EMAIL and ADMIN_PASSWORD are required");
  const admin = await newPage();
  await admin.goto("/login");
  await admin.getByLabel("E-mail").fill(ADMIN_EMAIL);
  await admin.getByLabel("Mot de passe").fill(ADMIN_PASSWORD);
  await admin.getByRole("button", { name: "Se connecter" }).click();
  // First login: forced two-factor enrolment. Later runs need ADMIN_TOTP_SECRET (printed the first time).
  const where = await Promise.race([
    admin.waitForURL("**/security").then(() => "enrol"),
    admin.getByLabel("Code d'authentification").waitFor().then(() => "code"),
  ]);
  if (where === "enrol") {
    console.log(`\n   admin two-factor enrolled; for later runs set ADMIN_TOTP_SECRET=${await enrolTotp(admin)}`);
  } else {
    assert.ok(process.env.ADMIN_TOTP_SECRET, "the admin already has two-factor enabled: set ADMIN_TOTP_SECRET");
    await admin.getByLabel("Code d'authentification").fill(totp(process.env.ADMIN_TOTP_SECRET));
    await admin.getByRole("button", { name: "Se connecter" }).click();
    await admin.waitForURL("**/admin");   // let the login finish before navigating, or the session cookie is lost
  }
  await admin.goto("/admin");
  await admin.getByRole("tab", { name: "Vue d'ensemble" }).waitFor();
  for (const tab of ["Organisations", "Offres", "Demandes RGPD", "Journal d'audit", "Supervision de l'IA", "Vue d'ensemble"]) {
    await admin.getByRole("tab", { name: tab }).click();
    await admin.waitForTimeout(600);
    // Next.js injects an empty role=alert route announcer; only count real error boxes.
    assert.equal(await admin.locator('[role="alert"]:not(#__next-route-announcer__)').count(), 0, `error on tab ${tab}`);
  }
  await admin.getByRole("tab", { name: "Journal d'audit" }).click();
  await admin.getByRole("button", { name: "Vérifier l'intégrité du journal" }).click();
  await admin.getByText(/Chaîne intacte/).waitFor();
  await admin.context().close();
});

await journey("6. Arabic switches the layout to right-to-left", async () => {
  const p = await newPage();
  await p.goto("/");
  assert.equal(await p.locator("html").getAttribute("dir"), "ltr");
  await p.getByLabel("Langue").selectOption("ar");
  await p.waitForTimeout(300);
  assert.equal(await p.locator("html").getAttribute("dir"), "rtl");
  await p.reload();
  assert.equal(await p.locator("html").getAttribute("dir"), "rtl");
  assert.equal(await p.locator("html").getAttribute("lang"), "ar");
  await p.getByRole("heading", { level: 1 }).waitFor();
  await p.context().close();
});

await browser.close();
console.log(`\n${results.filter(([, ok]) => ok).length}/${results.length} journeys passed`);
