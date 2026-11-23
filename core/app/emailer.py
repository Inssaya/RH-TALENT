"""Transactional e-mail. SMTP when configured (e.g. Brevo), console log otherwise."""
import logging
import smtplib
from email.message import EmailMessage

from .config import get_settings

log = logging.getLogger("tm.mail")
outbox: list[dict] = []  # filled in test and development mode


def send(to: str, subject: str, body: str) -> None:
    s = get_settings()
    if not s.smtp_host:
        outbox.append({"to": to, "subject": subject, "body": body})
        del outbox[:-200]
        log.info("MAIL to=%s subject=%s\n%s", to, subject, body)
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.mail_from, to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
            smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
    except Exception:
        log.exception("could not send e-mail to %s", to)


_T = {
    "received": {
        "fr": ("Candidature reçue : {job}", "Bonjour {name},\n\nNous avons bien reçu votre candidature pour « {job} » chez {org}.\nSuivez-la, retirez-la ou exercez vos droits ici :\n{link}\n\nCe lien est personnel et valable {days} jours.\n\nTalentMatch"),
        "en": ("Application received: {job}", "Hello {name},\n\nWe received your application for \"{job}\" at {org}.\nTrack it, withdraw it or exercise your rights here:\n{link}\n\nThis link is personal and valid for {days} days.\n\nTalentMatch"),
        "ar": ("تم استلام طلبك: {job}", "مرحبا {name}،\n\nلقد استلمنا طلبك لوظيفة «{job}» لدى {org}.\nتابع طلبك أو اسحبه أو مارس حقوقك من هنا:\n{link}\n\nهذا الرابط شخصي وصالح لمدة {days} يوما.\n\nTalentMatch"),
    },
    "rejected": {
        "fr": ("Votre candidature : {job}", "Bonjour {name},\n\nAprès examen par l'équipe de recrutement de {org}, votre candidature pour « {job} » n'a pas été retenue.\n{message}\nVous pouvez consulter le détail et demander un réexamen humain ici :\n{link}\n\nTalentMatch"),
        "en": ("Your application: {job}", "Hello {name},\n\nAfter review by the recruitment team at {org}, your application for \"{job}\" was not selected.\n{message}\nYou can see the details and request a human review here:\n{link}\n\nTalentMatch"),
        "ar": ("طلبك: {job}", "مرحبا {name}،\n\nبعد دراسة طلبك من طرف فريق التوظيف لدى {org}، لم يتم قبول ترشيحك لوظيفة «{job}».\n{message}\nيمكنك الاطلاع على التفاصيل وطلب مراجعة بشرية من هنا:\n{link}\n\nTalentMatch"),
    },
    "status": {
        "fr": ("Du nouveau pour votre candidature : {job}", "Bonjour {name},\n\nVotre candidature pour « {job} » chez {org} avance : {status}.\nSuivi : {link}\n\nTalentMatch"),
        "en": ("News about your application: {job}", "Hello {name},\n\nYour application for \"{job}\" at {org} is moving forward: {status}.\nTracking: {link}\n\nTalentMatch"),
        "ar": ("جديد بخصوص طلبك: {job}", "مرحبا {name}،\n\nطلبك لوظيفة «{job}» لدى {org} يتقدم: {status}.\nالمتابعة: {link}\n\nTalentMatch"),
    },
}


def send_template(kind: str, locale: str, to: str, **kw) -> None:
    subject, body = _T[kind].get(locale, _T[kind]["fr"])
    send(to, subject.format(**kw), body.format(**kw))
