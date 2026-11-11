import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-md py-16 text-center">
      <h1 className="h1">404</h1>
      <p className="muted mt-2">Page introuvable · Page not found · الصفحة غير موجودة</p>
      <Link href="/" className="btn-primary mt-6">TalentMatch</Link>
    </div>
  );
}
