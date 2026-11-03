"""Bounded, reproducible public literature discovery. Outputs are unreviewed, not products.

Example: python scripts/collect_material_sources.py --output ../material-source-intake
Raw abstracts/full text stay in the specified local directory; no credentials required.
"""
import argparse
import concurrent.futures
import hashlib
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

CROSSREF = [
    'lanthanum hexaboride solar control glazing', 'cerium oxide cement mortar',
    'yttrium oxide radiative cooling coating', 'cerium oxide corrosion coating',
    'rare earth phase change thermal storage', 'neodymium permanent magnet heat pump compressor',
    'lanthanum cerium thermal insulation aerogel', 'rare earth luminescent solar concentrator window',
    'rare earth life cycle assessment recycling permanent magnet',
]
EPMC = [
    '(TITLE:lanthanum OR TITLE:hexaboride) AND (TITLE:solar OR TITLE:window OR TITLE:infrared)',
    '(TITLE:cerium OR TITLE:ceria) AND (TITLE:cement OR TITLE:concrete OR TITLE:mortar)',
    '(TITLE:yttrium OR TITLE:cerium OR TITLE:"rare earth") AND (TITLE:"radiative cooling" OR TITLE:coating)',
    '(TITLE:lanthanum OR TITLE:cerium OR TITLE:"rare earth") AND (TITLE:"phase change" OR TITLE:aerogel OR TITLE:insulation)',
    '(TITLE:europium OR TITLE:terbium OR TITLE:neodymium) AND (TITLE:"solar concentrator" OR TITLE:window OR TITLE:magnet)',
]
PMC = [
    '"lanthanum hexaboride"[Title]',
    '("cerium oxide"[Title] OR ceria[Title]) AND (cement[Title] OR concrete[Title] OR coating[Title])',
    '"radiative cooling"[Title] AND (yttrium OR cerium OR "rare earth")',
    '"luminescent solar concentrator"[Title] AND (europium OR terbium OR lanthanide OR "rare earth")',
]


def plain(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]*>', ' ', value or ''))).strip()


def identity(doi, title):
    return doi.casefold().strip().removeprefix('https://doi.org/') if doi else 'title:' + plain(title).casefold()


def candidate(row):
    title = row['title'].casefold()
    rare = re.search(r'lanthan|hexabor|cerium|ceria|yttri|europ|terbi|neodym|rare[- ]earth|ceo2|lab6|y2o3', title)
    scope = re.search(r'solar|glaz|window|radiativ|coating|cement|concrete|mortar|thermal|aerogel|insulat|phase.change|heat.pump|compressor|life.cycle|recycl|magnet', title)
    excluded = re.search(r'dental|endodont|trioxide aggregate|implant|cancer|bone|tumor|wound|cytotoxic|photocatalytic degradation of', title)
    return bool(rare and scope and not excluded)


def retrieve(output, source, queries, until, use_cache=False):
    records, audit = [], []
    base = 'https://api.crossref.org/works' if source == 'crossref' else 'https://www.ebi.ac.uk/europepmc/webservices/rest/search'
    for n, query in enumerate(queries):
        params = {'query.title': query, 'rows': 12, 'filter': 'type:journal-article,until-pub-date:' + until} if source == 'crossref' else {
            'query': '('+query+') AND FIRST_PDATE:[1900-01-01 TO '+until+']', 'format': 'json', 'pageSize': 30, 'resultType': 'core'}
        url = base + '?' + urllib.parse.urlencode(params)
        log = {'provider': source, 'query': query, 'url': url, 'retrieved_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'status': 'failed'}
        try:
            filename = f'{source}-{n+1:02}.json'
            reused=use_cache and (output/filename).is_file()
            sidecar=output/(filename+'.request.json')
            if reused:
                cached_provenance= json.loads(sidecar.read_text(encoding='utf-8')) if sidecar.exists() else next((r for r in json.loads((output/'manifest.json').read_text(encoding='utf-8'))['requests'] if r.get('raw_file')==filename),{})
                if cached_provenance.get('url')!=url or cached_provenance.get('sha256')!=hashlib.sha256((output/filename).read_bytes()).hexdigest():
                    raise ValueError('Cached query or content does not match provenance; use a new output directory')
            raw = (output/filename).read_bytes() if reused else request(url)
            if not reused:(output / filename).write_bytes(raw)
            sidecar.write_text(json.dumps({'url':url,'sha256':hashlib.sha256(raw).hexdigest()}),encoding='utf-8')
            data = json.loads(raw)
            if source == 'crossref':
                if data.get('status') != 'ok' or not isinstance(data.get('message', {}).get('items'), list):
                    raise ValueError('Invalid Crossref envelope')
                items = data['message']['items']
                total = data['message']['total-results']
            else:
                if 'errCode' in data or not isinstance(data.get('resultList', {}).get('result'), list):
                    raise ValueError('Invalid Europe PMC envelope')
                items, total = data['resultList']['result'], data['hitCount']
            for r in items:
                title = plain((r.get('title') or [''])[0] if source == 'crossref' else r.get('title'))
                doi = r.get('DOI') if source == 'crossref' else r.get('doi')
                if not title:
                    continue
                record = {'key': identity(doi, title), 'title': title, 'doi': doi, 'provider': source,
                          'year': r.get('published', {}).get('date-parts', [[None]])[0][0] if source == 'crossref' else r.get('pubYear'),
                          'abstract': plain(r.get('abstract') if source == 'crossref' else r.get('abstractText')),
                          'pmcid': r.get('pmcid'), 'open_access_declared': r.get('isOpenAccess') == 'Y',
                          'journal': (r.get('container-title') or [None])[0] if source == 'crossref' else r.get('journalInfo', {}).get('journal', {}).get('title'),
                          'license_urls': [v['URL'] for v in (r.get('license') or []) if isinstance(v,dict) and isinstance(v.get('URL'),str)] if isinstance(r.get('license'),list) else [],
                          'license_text':r.get('license') if isinstance(r.get('license'),str) else None,
                          'query': query, 'raw_file': filename, 'status': 'UNREVIEWED_DISCOVERY'}
                record['in_scope_by_title_only'] = candidate(record)
                records.append(record)
            log.update(status='cached' if reused else 'retrieved', raw_file=filename, sha256=hashlib.sha256(raw).hexdigest(),
                       reported_total=total, retrieved=len(items), truncated_to_first_page=len(items) < total)
        except (ValueError, OSError, urllib.error.URLError) as exc:
            log['error'] = str(exc)
        audit.append(log)
        time.sleep(.3)
    return records, audit


def request(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'VRA-Trust-material-research/1.0 (bounded research intake)', 'Accept': 'application/json,application/xml;q=0.9'})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                body = response.read(8 * 1024 * 1024 + 1)
                if len(body) > 8 * 1024 * 1024:
                    raise ValueError('Response exceeded 8MiB; not stored as complete')
                return body
        except urllib.error.HTTPError as exc:
            if exc.code not in {429, 503} or attempt:
                raise
            time.sleep(2)


def retrieve_pmc(output, until):
    """NCBI fallback: check every article body, not only the batch envelope."""
    ids, logs, records = set(), [], []
    for n, query in enumerate(PMC):
        params = {'db': 'pmc', 'term': '(' + query + ') AND ("1900/01/01"[Publication Date] : "' + until.replace('-', '/') + '"[Publication Date])',
                  'retmode': 'json', 'retmax': 16}
        url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?' + urllib.parse.urlencode(params)
        try:
            raw = request(url)
            data = json.loads(raw)['esearchresult']
            if 'error' in data or not isinstance(data.get('idlist'), list):
                raise ValueError('Invalid NCBI search response')
            ids.update(data['idlist'])
            (output / f'pmc-search-{n+1}.json').write_bytes(raw)
            logs.append({'url': url, 'reported_count': int(data['count']), 'retrieved': len(data['idlist']), 'sha256': hashlib.sha256(raw).hexdigest()})
        except (KeyError, ValueError, OSError, urllib.error.URLError) as exc:
            logs.append({'url': url, 'error': str(exc)})
        time.sleep(.4)
    for n, start in enumerate(range(0, len(ids), 24)):
        params = {'db': 'pmc', 'id': ','.join(sorted(ids)[start:start+24]), 'retmode': 'xml'}
        url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?' + urllib.parse.urlencode(params)
        try:
            raw = request(url)
            file = f'pmc-expanded-{n+1}.xml'
            (output / file).write_bytes(raw)
            articles = ET.fromstring(raw).findall('.//article')
            if not articles:
                raise ValueError('NCBI returned no article elements')
            for a in articles:
                identifiers = {v.get('pub-id-type'): v.text for v in a.findall('.//article-id')}
                title, abstract = a.find('.//article-title'), a.find('.//abstract')
                records.append({'identifiers': identifiers, 'title': plain(''.join(title.itertext())) if title is not None else '',
                                'abstract': plain(''.join(abstract.itertext())) if abstract is not None else '',
                                'has_body': a.find('body') is not None, 'raw_file': file,
                                'licenses': [''.join(v.itertext()) for v in a.findall('.//license')],
                                'status': 'UNREVIEWED_DISCOVERY'})
            logs.append({'url': url, 'raw_file': file, 'articles': len(articles), 'sha256': hashlib.sha256(raw).hexdigest()})
        except (ValueError, OSError, urllib.error.URLError, ET.ParseError) as exc:
            logs.append({'url': url, 'error': str(exc)})
        time.sleep(.4)
    (output / 'pmc-discovery.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'pmc-retrieval-manifest.json').write_text(json.dumps(logs, ensure_ascii=False, indent=2), encoding='utf-8')
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--until', default='2026-11-01')
    parser.add_argument('--with-pmc', action='store_true', help='Also retrieve at most 64 NCBI PMC records; check body and license per article')
    parser.add_argument('--queries',type=Path,help='JSON with bounded crossref/europepmc query arrays, at most20 each; defaults unchanged')
    parser.add_argument('--resume-cache',action='store_true',help='Reuse original numbered responses for the SAME query file; old summaries are preserved')
    args = parser.parse_args()
    if args.resume_cache:
        if not args.output.is_dir():raise SystemExit('No existing cached output')
        import shutil
        for name in ['discovery.json','manifest.json']:
            if (args.output/name).exists():shutil.copy2(args.output/name,args.output/(str(time.time_ns())+'-'+name))
    else:args.output.mkdir(parents=True, exist_ok=False)
    crossref,epmc=CROSSREF,EPMC
    if args.queries:
        supplied=json.loads(args.queries.read_text(encoding='utf-8'))
        for key in ['crossref','europepmc']:
            items=supplied.get(key,[])
            if not isinstance(items,list) or len(items)>20 or any(not isinstance(q,str) or not 2<=len(q)<=300 for q in items):
                raise SystemExit('Invalid bounded query list: '+key)
        crossref,epmc=supplied.get('crossref',[]),supplied.get('europepmc',[])
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        jobs = [executor.submit(retrieve, args.output, name, queries, args.until,args.resume_cache) for name, queries in [('crossref', crossref), ('europepmc', epmc)]]
        results = [j.result() for j in jobs]
    records, logs = {}, []
    for rows, audit in results:
        logs += audit
        for row in rows:
            if row['key'] not in records:
                records[row['key']] = row
                row['alternate_records'] = []
            else:
                old = records[row['key']]
                old['alternate_records'].append({'provider': row['provider'], 'query': row['query'], 'raw_file': row['raw_file']})
                if not old['abstract'] and row['abstract']:
                    old['abstract'] = row['abstract']
                if row.get('pmcid'):
                    old['pmcid'], old['open_access_declared'] = row['pmcid'], row['open_access_declared']
    (args.output / 'discovery.json').write_text(json.dumps(list(records.values()), ensure_ascii=False, indent=2), encoding='utf-8')
    pmc_records = retrieve_pmc(args.output, args.until) if args.with_pmc else []
    summary = {'requests': logs, 'unique_records': len(records), 'title_scope_candidates': sum(r['in_scope_by_title_only'] for r in records.values()),
               'records_with_abstract': sum(bool(r['abstract']) for r in records.values()),
               'full_texts_retrieved': sum(r['has_body'] for r in pmc_records), 'pmc_records': len(pmc_records),
               'completeness': 'Bounded first-page discovery, not an exhaustive literature review. Candidates are unreviewed, not products or training labels.'}
    (args.output / 'manifest.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'requests'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
