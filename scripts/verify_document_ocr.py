"""Reproducible local OCR checks; supplied public files remain outside Git."""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from backend import core
from backend.document_worker import raster
from backend.intake import parse_source


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--font', type=Path, required=True, help='Local Chinese font, not redistributed')
    parser.add_argument('--public-image', type=Path, required=True)
    parser.add_argument('--construction-pdf', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.artifacts.mkdir(parents=True, exist_ok=True)
    expected = {'name':'南昌公共建筑改造（合成测试）','use':'办公楼','location':'江西省南昌市',
                'region':'CN-JX','area_m2':12345.6}
    labels = ['项目名称：'+expected['name'], '建筑用途：'+expected['use'], '项目地点：'+expected['location'],
              '地区代码：CN-JX', '总建筑面积：12345.6 m2']
    image = Image.new('RGB', (1600, 800), 'white')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(args.font), 38)
    for index, line in enumerate(labels):
        draw.text((60, 60 + index * 130), line, font=font, fill='black')
    cases = []
    for name, value in [('clean.png', image), ('skew3-blur06.png', image.rotate(3, expand=True, fillcolor='white').filter(ImageFilter.GaussianBlur(.6))),
                        ('rotation90.png', image.rotate(90, expand=True, fillcolor='white'))]:
        path = args.artifacts / name
        value.save(path)
        cases.append((path, 'synthetic', expected, []))
    scan = args.artifacts/'scan.pdf'
    image.save(scan, resolution=144)
    cases.append((scan, 'synthetic', expected, []))
    floor = args.artifacts/'public-floor-page6.png'
    with raster(args.construction_pdf, 6) as picture:
        picture.save(floor)
    # Five area labels manually read on the public ground-floor sheet. This is
    # selected-label recall, not room association, a total area, or full OCR accuracy.
    cases += [(args.public_image, 'public-general-ocr', {}, ['正品促销', '5.8', '假一赔十']),
              (floor, 'public-construction-page-raster', {}, ['7.22', '5.49', '2.34', '19.97', '15.8']),
              (args.construction_pdf, 'public-hybrid-pdf', {}, [])]
    output = {'timestamp': core.now(), 'scope':'OCR text and selected labels only; no geometry, building calibration or software-market superiority claim.',
              'sources': [{'url':'https://github.com/RapidAI/RapidOCR/releases/download/v1.1.0/ch_en_num.jpg', 'sha256':core.sha(args.public_image)},
                          {'url':'https://www.lookhere.pro/download/LookHere_Sample-Document_Construction.pdf', 'sha256':core.sha(args.construction_pdf),
                           'redistribution':'Original file not committed; no commercial reuse license inferred.'}], 'cases':[]}
    for path, kind, fields, anchors in cases:
        started = time.monotonic()
        result = parse_source(path)
        pages = result['facts']['document_pages']
        text = '\n'.join(p['text'] for p in pages)
        actual = {c['field']:c['value'] for c in result['candidates']}
        row = {'file':path.name, 'kind':kind, 'sha256':core.sha(path), 'bytes':path.stat().st_size,
               'seconds':round(time.monotonic()-started,3), 'pages':result['facts']['pages'],
               'page_methods':[p['method'] for p in pages], 'recognized_characters':len(text),
               'expected_fields':fields, 'actual_fields':actual,
               'correct_fields':sum(actual.get(k) == v for k,v in fields.items()),
               'selected_labels':[{'expected':label,'found':label in text} for label in anchors],
               'warnings':result['warnings'], 'ocr':result['facts']['ocr']}
        if kind == 'synthetic':
            assert row['correct_fields'] == 5, row
        if kind.startswith('public'):
            assert not actual, 'Public unrelated labels must not become building declarations'
        if path == args.construction_pdf:
            row['native_page6_characters'] = len(pages[5].get('native_text',''))
            row['ocr_page6_characters'] = len(pages[5]['text'])
            row['page6_selected_area_labels'] = [{'expected':s,'found':s in pages[5]['text']} for s in ['7.22','5.49','2.34','19.97','15.8']]
        output['cases'].append(row)
        print(json.dumps({k:row[k] for k in ('file','seconds','correct_fields','actual_fields')}, ensure_ascii=False), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
