from pathlib import Path
root=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108');p=root/'tests/test_agent_actions.py';s=p.read_text(encoding='utf-8')
s=s.replace("    captured=scripted(a,monkeypatch,[tool('thermal_read',{'thermal_id':r['thermal_id']}),tool('requested_defer',{})])\n    t=a.start(pid,Chat(message='Inspect the record but the requested metric has no definition.',mode='provider'),background=False)", "    missing='cost_'+'9'*32\n    captured=scripted(a,monkeypatch,[tool('professional_read_many',{'record_ids':[r['thermal_id'],missing]}),tool('requested_defer',{})])\n    t=a.start(pid,Chat(message='Inspect '+r['thermal_id']+' and '+missing+' but the metric has no definition.',mode='provider'),background=False)")
p.write_text(s,encoding='utf-8')
