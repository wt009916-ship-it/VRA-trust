import hashlib,json,zipfile
from pathlib import Path
from pypdf import PdfReader
out=Path('output/playwright/designload-20261107')
report=json.loads((out/'report.json').read_text(encoding='utf-8'))
files=json.loads((out/'downloads.json').read_text());pdf=Path(files[0]['file']);archive=Path(files[1]['file'])
reader=PdfReader(pdf);text='\n'.join(page.extract_text() for page in reader.pages)
assert '分区设计显热负荷' in text and 'SPACE1-1' in text
sizing=report['run']['metrics']['zone_design_loads']
assert sizing['model_sha256'] in text and sizing['sql_sha256'] in text and sizing['policy_version'] in text
with zipfile.ZipFile(archive) as z:
 result=json.loads(z.read('result.json'));manifest=json.loads(z.read('manifest.json'));current=json.loads(z.read('CURRENT_VALIDATION.json'))
 assert result['metrics']['zone_design_loads']==current['metrics']['zone_design_loads']==sizing
 checked=[]
 for name,expected in manifest['artifact_hashes'].items():
  assert hashlib.sha256(z.read(name)).hexdigest()==expected,name
  checked.append(name)
receipt={'pdf_pages':len(reader.pages),'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),
         'zip_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'verified_artifacts':len(checked),
         'rows_same_in_json_native_and_zip':len(sizing['rows']),'pdf_provenance_and_section_verified':True}
with (out/'download-verification-v1.json').open('x') as stream:json.dump(receipt,stream,indent=2)
print(json.dumps(receipt))
