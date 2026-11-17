"""Check i18n coverage. Without flags: fail if a key used by t() is missing from French.
With --locale ar: warn about Arabic gaps (exit 0, only prints).
"""
import argparse, re, glob, sys
p=argparse.ArgumentParser(); p.add_argument("--locale"); args=p.parse_args()
def load(path):
    t=open(path).read()
    keys=re.findall(r'"((?:[^"\\]|\\.)+)"\s*:\s*"',t)
    return keys, set(keys)
fr_keys,fr=load('lib/dict.fr.ts')
dup={k for k in fr_keys if fr_keys.count(k)>1}
used=set()
rx=re.compile(r'\bt\(\s*"((?:[^"\\]|\\.)+)"')
for f in glob.glob('app/**/*.tsx',recursive=True)+glob.glob('components/*.tsx'):
    used.update(rx.findall(open(f).read()))
for f,names in [('lib/labels.ts',['CONTRACT','REMOTE','EDUCATION','LANGS']),('lib/types.ts',['QUALITY_LABEL','SUBSCORE_LABEL']),('components/ui.tsx',['STATUS_LABEL','FLAG_LABEL']),('components/TrackingDetail.tsx',['REASON']),('app/recruiter/applications/[id]/page.tsx',['REASONS','REQ_LABEL','HOW']),('app/recruiter/jobs/[id]/page.tsx',['REASONS'])]:
    s=open(f).read()
    for n in names:
        m=re.search(r'(?:const|export const) '+n+r'[^=]*=\s*\{(.*?)\};',s,re.S)
        used.update(re.findall(r':\s*"([^"]+)"',m.group(1)))
for f in ['app/recruiter/jobs/new/page.tsx','app/recruiter/jobs/[id]/page.tsx','app/admin/page.tsx','app/page.tsx','app/recruiter/org/page.tsx']:
    s=open(f).read()
    used.update(re.findall(r'\["[a-z_]+",\s*"([^"]+)"\]',s))
    for m in re.finditer(r'^\s*\["([^"]+)",\s*"([^"]+)"\],$',s,re.M): used.update(m.groups())
    used.update(re.findall(r'\["(?:name|sector|size|city|country|website)", "([^"]+)"\]',s))
used={u.replace('\\"','"') for u in used}
if args.locale=="ar":
    _,ar=load('lib/dict.ar.ts')
    ar_dup_keys=[k for k in re.findall(r'"((?:[^"\\]|\\.)+)"\s*:\s*"',open('lib/dict.ar.ts').read()) if re.findall(r'"((?:[^"\\]|\\.)+)"\s*:\s*"',open('lib/dict.ar.ts').read()).count(k)>1]
    ar_dup=set(ar_dup_keys)
    missing_ar=sorted(u for u in used if u not in ar)
    print(f"duplicate ar keys: {sorted(ar_dup)}")
    print(f"{len(used)} keys used; {len(missing_ar)} missing from ar:")
    print("\n".join(missing_ar))
    sys.exit(0)
missing=sorted(u for u in used if u not in fr)
print("duplicate fr keys:",sorted(dup))
print(len(used),"keys used;",len(missing),"missing from fr:")
print("\n".join(missing))
sys.exit(1 if missing or dup else 0)
