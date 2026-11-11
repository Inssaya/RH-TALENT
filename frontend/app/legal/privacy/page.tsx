import type { Metadata } from "next";
import Doc, { Section } from "@/components/Doc";
import { getLocale } from "@/lib/locale";

export const metadata: Metadata = { title: "Privacy and your rights" };

// Template notice. The operator must complete the bracketed items and have it reviewed by a lawyer
// before opening the platform to the public (see docs/compliance.md).
const C: Record<string, { title: string; intro: string; sections: Section[] }> = {
  en: {
    title: "Privacy and your rights",
    intro: "This notice explains what happens to your data when you apply or create an account. Version 2026-11.",
    sections: [
      { h: "Who is responsible", p: [
        "For an application: the company you apply to is the data controller. TalentMatch processes your application on its behalf.",
        "For your candidate account, recommendations and platform security: the operator of TalentMatch is the controller. Contact: [operator name and contact address]." ] },
      { h: "What we process and why", ul: [
        "Application: name, e-mail, phone, CV and the profile extracted from it, the score and its explanation. Purpose: assessing your application for the job. Legal basis: steps taken at your request before a contract.",
        "Account, profile, recommendations: legal basis: performance of the service you signed up for.",
        "Visibility to recruiters and job alerts: only with your consent, which you can withdraw at any time.",
        "Security and audit logs (truncated IP address): legitimate interest in protecting the platform.",
        "We do not ask for a photo, date of birth or nationality, and we do not infer them." ] },
      { h: "Automated analysis and human decision", p: [
        "An automated analysis ranks applications and explains the ranking. No decision about you is taken solely by automated means: a person decides, and you can ask for a human review and contest the outcome. See “How the AI works”." ] },
      { h: "Who receives your data", ul: [
        "The recruiters of the company you applied to.",
        "Our technical providers, under contract: hosting and storage, e-mail delivery, and, when enabled, an AI provider that receives CV text with name and contact details removed, without the right to retain it or train on it. [List of sub-processors and their locations.]" ] },
      { h: "How long we keep it", ul: [
        "Applications: deleted at the latest 24 months after the job closes, or as soon as you ask.",
        "Account and profile: until you delete your account.",
        "Erasure removes the database rows, the extracted profile, the score and the stored file; backups are purged within 35 days." ] },
      { h: "Your rights", p: [
        "Access and portability (download your data), rectification, erasure, withdrawal of consent, objection, human review. Use your tracking link or your account, or write to the contact above. You can also lodge a complaint with your data protection authority." ] },
    ],
  },
  fr: {
    title: "Confidentialité et vos droits",
    intro: "Cette notice explique ce que deviennent vos données lorsque vous postulez ou créez un compte. Version 2026-11.",
    sections: [
      { h: "Qui est responsable", p: [
        "Pour une candidature : l'entreprise à laquelle vous postulez est responsable du traitement. TalentMatch traite votre candidature pour son compte.",
        "Pour votre compte candidat, les recommandations et la sécurité de la plateforme : l'exploitant de TalentMatch est responsable. Contact : [nom de l'exploitant et adresse de contact]." ] },
      { h: "Ce que nous traitons et pourquoi", ul: [
        "Candidature : nom, e-mail, téléphone, CV et profil qui en est extrait, score et explication. Finalité : évaluer votre candidature pour l'offre. Base légale : mesures précontractuelles prises à votre demande.",
        "Compte, profil, recommandations : base légale : exécution du service auquel vous vous êtes inscrit.",
        "Visibilité auprès des recruteurs et alertes emploi : uniquement avec votre consentement, retirable à tout moment.",
        "Sécurité et journaux d'audit (adresse IP tronquée) : intérêt légitime à protéger la plateforme.",
        "Nous ne demandons ni photo, ni date de naissance, ni nationalité, et nous ne les déduisons pas." ] },
      { h: "Analyse automatisée et décision humaine", p: [
        "Une analyse automatisée classe les candidatures et explique ce classement. Aucune décision vous concernant n'est prise par des moyens exclusivement automatisés : une personne décide, et vous pouvez demander un réexamen humain et contester le résultat. Voir « Comment fonctionne l'IA »." ] },
      { h: "Qui reçoit vos données", ul: [
        "Les recruteurs de l'entreprise à laquelle vous avez postulé.",
        "Nos prestataires techniques, sous contrat : hébergement et stockage, envoi d'e-mails et, lorsqu'il est activé, un fournisseur d'IA qui reçoit le texte du CV sans nom ni coordonnées, sans droit de le conserver ni d'entraîner ses modèles. [Liste des sous-traitants et de leur localisation.]" ] },
      { h: "Combien de temps nous les conservons", ul: [
        "Candidatures : supprimées au plus tard 24 mois après la clôture de l'offre, ou dès que vous le demandez.",
        "Compte et profil : jusqu'à la suppression de votre compte.",
        "L'effacement supprime les lignes en base, le profil extrait, le score et le fichier stocké ; les sauvegardes sont purgées sous 35 jours." ] },
      { h: "Vos droits", p: [
        "Accès et portabilité (téléchargement de vos données), rectification, effacement, retrait du consentement, opposition, réexamen humain. Utilisez votre lien de suivi ou votre compte, ou écrivez au contact ci-dessus. Vous pouvez aussi saisir votre autorité de protection des données." ] },
    ],
  },
  ar: {
    title: "الخصوصية وحقوقك",
    intro: "يوضح هذا الإشعار ما يحدث لبياناتك عند التقدم لوظيفة أو إنشاء حساب. النسخة 2026-11.",
    sections: [
      { h: "من المسؤول", p: [
        "بالنسبة لطلب التوظيف: الشركة التي تتقدم إليها هي المسؤولة عن المعالجة، وتعالج TalentMatch طلبك لحسابها.",
        "بالنسبة لحسابك والتوصيات وأمن المنصة: مشغل TalentMatch هو المسؤول. الاتصال: [اسم المشغل وعنوان الاتصال]." ] },
      { h: "ما نعالجه ولماذا", ul: [
        "الطلب: الاسم، البريد الإلكتروني، الهاتف، السيرة الذاتية والملف المستخرج منها، النتيجة وشرحها، لتقييم طلبك.",
        "الظهور للمسؤولين عن التوظيف وتنبيهات الوظائف: بموافقتك فقط، ويمكن سحبها في أي وقت.",
        "لا نطلب صورة ولا تاريخ ميلاد ولا جنسية." ] },
      { h: "التحليل الآلي والقرار البشري", p: [
        "يرتب تحليل آلي الطلبات ويشرح الترتيب. لا يُتخذ أي قرار بشأنك بوسائل آلية حصرا: يقرر إنسان، ويمكنك طلب مراجعة بشرية والاعتراض." ] },
      { h: "مدة الحفظ", ul: [
        "الطلبات: تُحذف في أجل أقصاه 24 شهرا بعد إغلاق العرض، أو فور طلبك.",
        "الحساب والملف: إلى أن تحذف حسابك." ] },
      { h: "حقوقك", p: [
        "الاطلاع على بياناتك وتنزيلها، التصحيح، المحو، سحب الموافقة، الاعتراض، المراجعة البشرية. استخدم رابط المتابعة أو حسابك." ] },
    ],
  },
};

export default async function Page() {
  const c = C[await getLocale()];
  return <Doc {...c} />;
}
