"""Preserve first runner; repair group dispatch only, reuse completed predictions."""
from pathlib import Path
ROOT=Path('C:/Users/18483/AppData/Local/Temp/vra-symbol-detector-20261108')
HERE=Path(__file__).parent
original=(HERE/'run_symbol_screen.py').read_bytes()
assert not (ROOT/'runner-original.py').exists()
(ROOT/'runner-original.py').write_bytes(original)
text=original.decode('utf-8')
text=text.replace("OUT.mkdir(exist_ok=False)","assert OUT.is_dir()")
text=text.replace("if r['group']==group","if r['group']==({'clean':'rendered_clean','degraded':'rendered_degraded'}.get(group,group))")
begin=text.index('    tick=time.perf_counter()\n    try:')
end=text.index('\ngroups={}',begin)
text=text[:begin]+'''    run=json.loads((OUT/f'{name}.json').read_text())
    assert run['image_id']==name
    if run['error'] is None:
        predictions.append({**base,'boxes':[{'category':x['category'],'box':x['box']} for x in run['result']['candidates']],
                            'wall_mask':(np.asarray(Image.open(OUT/f'{name}-wall.png'))>0).astype(int).tolist()})
    runs.append(run)
'''+text[end:]
text=text.replace("name=f'public-plan-{kind}';source=ROOT/f'{name}.jpg';tick=time.perf_counter()", "name=f'public-plan-{kind}';source=ROOT/f'{name}.jpg';tick=time.perf_counter();assert not (OUT/f'{name}.json').exists()")
text=text.replace("'total_seconds':time.perf_counter()-start,", "'resume_scoring_and_public_seconds':time.perf_counter()-start,'reference_inference_seconds':sum(r['seconds'] for r in runs),\n         'runner_repair':'Original runner completed 14 detections then failed because group clean did not match rendered_clean. Original predictions reused unchanged; only dispatch labels repaired; public inference first run.',")
dest=HERE/'run_symbol_resume.py';assert not dest.exists();dest.write_text(text,encoding='utf-8')
print('Original runner preserved; resume runner repairs group lookup only.')
