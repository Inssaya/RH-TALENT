export type Section = { h: string; p?: string[]; ul?: string[] };

export default function Doc({ title, intro, sections }: { title: string; intro?: string; sections: Section[] }) {
  return (
    <article className="mx-auto max-w-3xl space-y-6">
      <h1 className="h1">{title}</h1>
      {intro && <p className="text-slate-700">{intro}</p>}
      {sections.map((s) => (
        <section key={s.h} className="card space-y-2">
          <h2 className="h2">{s.h}</h2>
          {s.p?.map((x) => <p key={x} className="text-sm leading-relaxed text-slate-700">{x}</p>)}
          {s.ul && <ul className="list-disc space-y-1 ps-5 text-sm text-slate-700">{s.ul.map((x) => <li key={x}>{x}</li>)}</ul>}
        </section>
      ))}
    </article>
  );
}
