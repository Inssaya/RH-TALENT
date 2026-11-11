import type { Metadata } from "next";
import Doc, { Section } from "@/components/Doc";
import { getLocale } from "@/lib/locale";

export const metadata: Metadata = { title: "Help" };

const C: Record<string, { title: string; sections: Section[] }> = {
  en: { title: "Help", sections: [
    { h: "Recruiters: publish a job", ul: [
      "Create an account as an employer, then “New job post”.",
      "Describe the job to the assistant, dictate it, paste an existing description, import a file, or fill in the form. All channels fill the same form.",
      "Run “Check quality and bias”, fix the points marked as blocking, then publish. Share the public page link." ] },
    { h: "Recruiters: read the shortlist", ul: [
      "Choose the rule: the N best, everyone above a score, or both. Change it at any time; previous shortlists are kept.",
      "Open a candidate to see the score by criterion, the evidence quoted from the CV and what is missing.",
      "Candidates under “To check manually” had a CV that was hard to read: look at them yourself.",
      "Move candidates forward or reject them. A rejection needs a reason; the e-mail leaves after 10 minutes, during which you can cancel. For a grouped rejection you must review the list first." ] },
    { h: "Candidates", ul: [
      "Apply without an account from the job page with your CV (PDF, Word, photo or scan). Keep the tracking link you receive by e-mail.",
      "With an account, upload your CV once, check the extracted profile, then apply in one click and get recommendations.",
      "If you are not selected, the tracking page shows which requirements were not demonstrated, and lets you ask for a human review." ] },
    { h: "Frequent questions", ul: [
      "Does the AI reject candidates? No. It ranks and explains; a person decides.",
      "Can I see my rank? No. You see your status and, if not selected, the reasons.",
      "My CV is a photo: is that a problem? No, it is read by character recognition. If it is hard to read, a recruiter checks it manually.",
      "How do I delete my data? From the tracking page or your account, section “Your rights”." ] },
  ] },
  fr: { title: "Aide", sections: [
    { h: "Recruteurs : publier une offre", ul: [
      "Créez un compte employeur, puis « Nouvelle offre ».",
      "Décrivez le poste à l'assistant, dictez-le, collez une annonce existante, importez un fichier ou remplissez le formulaire. Tous les canaux alimentent le même formulaire.",
      "Lancez « Vérifier la qualité et les biais », corrigez les points bloquants, puis publiez. Partagez le lien de la page publique." ] },
    { h: "Recruteurs : lire la shortlist", ul: [
      "Choisissez la règle : les N meilleurs, tous ceux au-dessus d'un score, ou les deux. Modifiable à tout moment ; les shortlists précédentes sont conservées.",
      "Ouvrez un candidat pour voir le score par critère, les preuves citées du CV et ce qui manque.",
      "Les candidats « À vérifier manuellement » ont un CV difficile à lire : regardez-les vous-même.",
      "Faites avancer les candidats ou refusez-les. Un refus exige un motif ; l'e-mail part après 10 minutes, pendant lesquelles vous pouvez annuler. Pour un refus groupé, vous devez d'abord relire la liste." ] },
    { h: "Candidats", ul: [
      "Postulez sans compte depuis la page de l'offre avec votre CV (PDF, Word, photo ou scan). Conservez le lien de suivi reçu par e-mail.",
      "Avec un compte, déposez votre CV une fois, vérifiez le profil extrait, puis postulez en un clic et recevez des recommandations.",
      "Si vous n'êtes pas retenu, la page de suivi indique les exigences non démontrées et permet de demander un réexamen humain." ] },
    { h: "Questions fréquentes", ul: [
      "L'IA refuse-t-elle des candidats ? Non. Elle classe et explique ; une personne décide.",
      "Puis-je voir mon classement ? Non. Vous voyez votre statut et, si vous n'êtes pas retenu, les motifs.",
      "Mon CV est une photo : est-ce un problème ? Non, il est lu par reconnaissance de caractères. S'il est difficile à lire, un recruteur le vérifie manuellement.",
      "Comment supprimer mes données ? Depuis la page de suivi ou votre compte, rubrique « Vos droits »." ] },
  ] },
  ar: { title: "مساعدة", sections: [
    { h: "المسؤولون عن التوظيف", ul: [
      "أنشئ حساب مشغّل ثم «عرض جديد». صف الوظيفة للمساعد أو أملِها أو الصق نصا أو استورد ملفا أو املأ النموذج.",
      "اختر قاعدة القائمة المختصرة: أفضل N، أو كل من تجاوز نتيجة معينة. افتح مترشحا لرؤية الأدلة وما ينقصه.",
      "الرفض يتطلب سببا، ويُرسل البريد بعد 10 دقائق يمكنك خلالها الإلغاء." ] },
    { h: "المترشحون", ul: [
      "تقدم بدون حساب من صفحة العرض بسيرتك الذاتية (PDF أو Word أو صورة). احتفظ برابط المتابعة.",
      "إذا لم يتم قبولك، تعرض صفحة المتابعة المتطلبات غير المثبتة وتتيح طلب مراجعة بشرية.",
      "لحذف بياناتك: من صفحة المتابعة أو من حسابك، قسم «حقوقك»." ] },
  ] },
};

export default async function Page() {
  const c = C[await getLocale()];
  return <Doc {...c} />;
}
