"""Query installed Python package versions against OSV; never send source or secrets."""
import argparse
import importlib.metadata
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    if args.output.exists():
        raise SystemExit('Refusing to overwrite previous audit evidence')
    packages=sorted([{'name':d.metadata['Name'],'version':d.version} for d in importlib.metadata.distributions()],key=lambda p:p['name'].lower())
    body={'queries':[{'package':{'name':p['name'],'ecosystem':'PyPI'},'version':p['version']} for p in packages]}
    url='https://api.osv.dev/v1/querybatch'
    req=urllib.request.Request(url,data=json.dumps(body).encode(),headers={'Content-Type':'application/json','User-Agent':'VRA-dependency-audit'})
    with urllib.request.urlopen(req,timeout=30) as response:
        result=json.load(response)
    if len(result['results'])!=len(packages):
        raise ValueError('Incomplete vulnerability response')
    rows=[{**p,'vulnerabilities':v.get('vulns',[])} for p,v in zip(packages,result['results'])]
    findings=[r for r in rows if r['vulnerabilities']]
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'checked_at':datetime.now(timezone.utc).isoformat(),'source':url,
                                     'scope':'installed Python packages; OSV version matches, not a penetration test',
                                     'packages':rows},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'packages':len(rows),'affected_packages':len(findings),'findings':findings}))
    if findings:
        raise SystemExit(1)


if __name__=='__main__':
    main()
