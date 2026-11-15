"""Read cached public OOXML cells only; never evaluate formulas/macros."""
import json,posixpath,zipfile
from pathlib import Path
from xml.etree import ElementTree as E
NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
def sheets(path):
    with zipfile.ZipFile(path) as z:
        assert sum(i.file_size for i in z.infolist())<128*1024**2
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            strings=[''.join(e.itertext()) for e in E.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',NS)]
        rels={x.attrib['Id']:x.attrib for x in E.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        for sheet in E.fromstring(z.read('xl/workbook.xml')).findall('m:sheets/m:sheet',NS):
            relation=rels[sheet.attrib['{'+REL+'}id']]
            if not relation['Type'].endswith('/worksheet'):
                continue  # Historical template retains chart relations without chart XML.
            target=relation['Target']
            name=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
            rows=[]
            for row in E.fromstring(z.read(name)).findall('m:sheetData/m:row',NS):
                cells={}
                for c in row.findall('m:c',NS):
                    value=c.find('m:v',NS);formula=c.find('m:f',NS);text=value.text if value is not None else None
                    if c.attrib.get('t')=='s':text=strings[int(text)] if text is not None else None
                    elif c.attrib.get('t')=='inlineStr':text=''.join(c.find('m:is',NS).itertext())
                    if text is not None or formula is not None:cells[c.attrib['r']]={'value':text,'formula':formula.text if formula is not None else None}
                if cells:rows.append(cells)
            yield sheet.attrib['name'],rows
if __name__=='__main__':
    root=Path(__file__).parent/'public-reference/ASHRAE140-Envelope'
    for p in root.glob('*.xlsx'):
        print('\nFILE',p.name)
        for name,rows in sheets(p):
            print('SHEET',name,'ROWS',len(rows))
            if 'Reference' in p.name and name in ['Cases 600','Cases 900','Free Float Cases']:
                for r in rows:
                    if int(next(iter(r)).lstrip('ABCDEFGHIJKLMNOPQRSTUVWXYZ'))>=20:print(json.dumps({k:v for k,v in r.items() if k.startswith(('A','C','G','I'))},ensure_ascii=False))
            elif 'Part 1' in p.name:
                for r in rows[:12]:print(json.dumps(r,ensure_ascii=False))
