import type { Metadata } from "next";
import Doc, { Section } from "@/components/Doc";
import { getLocale } from "@/lib/locale";

export const metadata: Metadata = { title: "How the AI works" };

const C: Record<string, { title: string; intro: string; sections: Section[] }> = {
  en: {
    title: "How the AI works",
    intro: "TalentMatch uses AI to read, rank and explain applications. It never decides for a person: every rejection, interview and hire is a human action.",
    sections: [
      { h: "What is automated, and what is not", ul: [
        "Automated: reading the CV, extracting skills and experience, computing a score, proposing a shortlist, writing the explanation.",
        "Never automated: rejecting a candidate, inviting to an interview, hiring. A recruiter does this, and the action is recorded.",
        "A candidate can always ask for a human review of their application." ] },
      { h: "How a CV is read", p: [
        "The file is checked (type, size, antivirus when enabled), then its text is extracted. Scans and photos go through character recognition. Text hidden in the file and sentences that look like instructions to the AI are removed and reported to the recruiter.",
        "If a CV is hard to read, it is not down-ranked: it goes to a “to check manually” lane." ] },
      { h: "How the score is computed", p: [
        "The score out of 100 is a weighted sum of seven criteria. Default weights: skills 30%, job requirements 25%, relevant experience 15%, overall similarity 15%, education 5%, languages 5%, location 5%. Recruiters can adjust them; no criterion may exceed 60%.",
        "For each requirement, the system looks for evidence in the CV and quotes it. A quotation that cannot be found in the CV is discarded. The language model, when enabled, only identifies facts and evidence; the ranking is a transparent formula, so the same CV and job always give the same score." ] },
      { h: "Fairness safeguards", ul: [
        "Name, e-mail, phone, photo, age, gender and nationality play no part in the score. Contact details and the name are removed before any text is sent to an AI provider.",
        "Over-qualification is never penalised. Career gaps are never penalised: experience is counted in cumulative years.",
        "Location has a low weight because it can correlate with origin.",
        "Tests check that changing only the name on a CV does not change the score.",
        "Recruiters can screen anonymously: identities stay hidden until a candidate is advanced." ] },
      { h: "Limits you should know", ul: [
        "Extraction can miss information, especially in scanned or unusually formatted CVs and in Arabic. This is why every candidate remains visible and can be reviewed by a person.",
        "Without a configured language model, the platform works with rules: requirement assessment is then less nuanced, and this is indicated on each application.",
        "Fairness is verified on synthetic test pairs, because we deliberately do not collect demographic data. This does not prove the absence of all bias in real conditions." ] },
      { h: "Your rights", p: [
        "You can track, withdraw or erase your application, download your data, and ask for a human review, from your tracking link or your account. See the privacy notice." ] },
    ],
  },
  fr: {
    title: "Comment fonctionne l'IA",
    intro: "TalentMatch utilise l'IA pour lire, classer et expliquer les candidatures. Elle ne décide jamais à la place d'une personne : chaque refus, entretien ou embauche est une action humaine.",
    sections: [
      { h: "Ce qui est automatisé, et ce qui ne l'est pas", ul: [
        "Automatisé : lecture du CV, extraction des compétences et de l'expérience, calcul d'un score, proposition d'une shortlist, rédaction de l'explication.",
        "Jamais automatisé : refuser un candidat, inviter à un entretien, embaucher. Un recruteur le fait, et l'action est enregistrée.",
        "Un candidat peut toujours demander un réexamen humain de sa candidature." ] },
      { h: "Comment un CV est lu", p: [
        "Le fichier est contrôlé (type, taille, antivirus s'il est activé), puis son texte est extrait. Les scans et photos passent par une reconnaissance de caractères. Le texte caché dans le fichier et les phrases qui ressemblent à des instructions adressées à l'IA sont retirés et signalés au recruteur.",
        "Si un CV est difficile à lire, il n'est pas déclassé : il est placé dans un couloir « à vérifier manuellement »." ] },
      { h: "Comment le score est calculé", p: [
        "Le score sur 100 est une somme pondérée de sept critères. Pondérations par défaut : compétences 30 %, exigences du poste 25 %, expérience pertinente 15 %, similarité globale 15 %, formation 5 %, langues 5 %, localisation 5 %. Le recruteur peut les ajuster ; aucun critère ne peut dépasser 60 %.",
        "Pour chaque exigence, le système cherche une preuve dans le CV et la cite. Une citation introuvable dans le CV est écartée. Le modèle de langage, lorsqu'il est activé, ne fait que relever des faits et des preuves ; le classement est une formule transparente : le même CV et la même offre donnent toujours le même score." ] },
      { h: "Garde-fous d'équité", ul: [
        "Le nom, l'e-mail, le téléphone, la photo, l'âge, le genre et la nationalité n'entrent pas dans le score. Les coordonnées et le nom sont retirés avant tout envoi de texte à un fournisseur d'IA.",
        "La surqualification n'est jamais pénalisée. Les trous de parcours non plus : l'expérience est comptée en années cumulées.",
        "La localisation a un poids faible, car elle peut être corrélée à l'origine.",
        "Des tests vérifient que changer seulement le nom sur un CV ne change pas le score.",
        "Le recruteur peut présélectionner à l'aveugle : les identités restent masquées jusqu'à ce qu'il fasse avancer un candidat." ] },
      { h: "Limites à connaître", ul: [
        "L'extraction peut manquer des informations, surtout pour les CV scannés, les mises en page inhabituelles et l'arabe. C'est pourquoi chaque candidat reste visible et peut être examiné par une personne.",
        "Sans modèle de langage configuré, la plateforme fonctionne avec des règles : l'évaluation des exigences est alors moins fine, et c'est indiqué sur chaque candidature.",
        "L'équité est vérifiée sur des paires de test synthétiques, car nous ne collectons volontairement aucune donnée démographique. Cela ne prouve pas l'absence de tout biais en conditions réelles." ] },
      { h: "Vos droits", p: [
        "Vous pouvez suivre, retirer ou effacer votre candidature, télécharger vos données et demander un réexamen humain, depuis votre lien de suivi ou votre compte. Voir la notice de confidentialité." ] },
    ],
  },
  ar: {
    title: "كيف يعمل الذكاء الاصطناعي",
    intro: "تستخدم TalentMatch الذكاء الاصطناعي لقراءة طلبات التوظيف وترتيبها وشرحها. لا يتخذ القرار مكان الإنسان أبدا: كل رفض أو مقابلة أو توظيف هو إجراء بشري.",
    sections: [
      { h: "ما هو آلي وما ليس آليا", ul: [
        "آلي: قراءة السيرة الذاتية، استخراج المهارات والخبرة، حساب النتيجة، اقتراح قائمة مختصرة، كتابة الشرح.",
        "غير آلي أبدا: رفض مترشح، الدعوة إلى مقابلة، التوظيف. يقوم بها المسؤول عن التوظيف ويتم تسجيلها.",
        "يمكن للمترشح دائما طلب مراجعة بشرية لطلبه." ] },
      { h: "كيف تُحسب النتيجة", p: [
        "النتيجة من 100 هي مجموع مرجح لسبعة معايير: المهارات 30٪، متطلبات الوظيفة 25٪، الخبرة 15٪، التشابه العام 15٪، التكوين 5٪، اللغات 5٪، الموقع 5٪.",
        "لكل متطلب يبحث النظام عن دليل في السيرة الذاتية ويقتبسه. الاقتباس غير الموجود في السيرة يُستبعد. نفس السيرة ونفس العرض يعطيان دائما نفس النتيجة." ] },
      { h: "ضمانات الإنصاف", ul: [
        "الاسم والبريد والهاتف والصورة والعمر والجنس والجنسية لا تدخل في النتيجة.",
        "لا تُعاقب المؤهلات الزائدة ولا فترات الانقطاع في المسار المهني.",
        "السيرة الصعبة القراءة لا تُنزَّل في الترتيب: توضع في مسار «للتحقق يدويا»." ] },
      { h: "حدود يجب معرفتها", ul: [
        "قد يفوّت الاستخراج بعض المعلومات، خاصة في السير الممسوحة ضوئيا وباللغة العربية. لذلك يبقى كل مترشح ظاهرا ويمكن أن يراجعه إنسان.",
        "يتم التحقق من الإنصاف على أزواج اختبار اصطناعية، وهذا لا يثبت غياب كل تحيز في الظروف الحقيقية." ] },
      { h: "حقوقك", p: ["يمكنك متابعة طلبك أو سحبه أو محوه، وتنزيل بياناتك، وطلب مراجعة بشرية، من رابط المتابعة أو من حسابك."] },
    ],
  },
};

export default async function Page() {
  const c = C[await getLocale()];
  return <Doc {...c} />;
}
