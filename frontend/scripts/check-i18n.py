"""Fail if a key used by t() is missing from the French dictionary, or a dictionary has duplicate keys."""
import re, glob, sys
fe=open('lib/dict.fr.ts').read()
dkeys=re.findall(r'"((?:[^"\\]|\\.)+)"\s*:\s*"',fe)
dup={k for k in dkeys if dkeys.count(k)>1}
print("duplicate fr keys:",sorted(dup))
fr=set(dkeys)
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
missing=sorted(u for u in used if u not in fr)
print(len(used),"keys used;",len(missing),"missing from fr:")
print("\n".join(missing))
sys.exit(1 if missing or dup else 0)
