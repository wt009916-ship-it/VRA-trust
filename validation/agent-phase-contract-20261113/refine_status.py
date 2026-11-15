from pathlib import Path
root=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108')
p=root/'backend/agent.py';s=p.read_text(encoding='utf-8')
s=s.replace("if not read_any or not any(r.get('explanation_facts') for _,r in read_records):available.discard('professional_deliver')", "if not read_any or not any(r.get('explanation_facts') and r[ds.record_key] not in review_ids for ds,r in read_records):available.discard('professional_deliver')")
s=s.replace("[(ds,r) for ds,r in read_records if r.get('explanation_facts')]", "[(ds,r) for ds,r in read_records if r.get('explanation_facts') and r[ds.record_key] not in review_ids]")
s=s.replace("                    if record.get('read_deferrals') and not batch_failed", "                    if record.get('question_deferral') and not batch_failed:\n                        record['termination']={'reason':'question_deferred','model_declared_finished':False}\n                        break  # Explicit uncertainty stops execution without resolving selected reads.\n                    if record.get('read_deferrals') and not batch_failed")
p.write_text(s,encoding='utf-8')
p=root/'tests/test_agent_actions.py';s=p.read_text(encoding='utf-8')+'''

def test_open_question_defer_stops_after_selected_read_without_false_completion(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;r=create_record(client,pid,'thermal')
    captured=scripted(a,monkeypatch,[tool('thermal_read',{'thermal_id':r['thermal_id']}),tool('requested_defer',{})])
    t=a.start(pid,Chat(message='Inspect the record but the requested metric has no definition.',mode='provider'),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert len(captured)==2 and t['termination']['reason']=='question_deferred'
    assert t['answer']['task_completion']=='incomplete' and not t['answer'].get('checked_statements')
    assert t['unresolved_selected_reads'] and not t.get('model_finished_delivery')
''';p.write_text(s,encoding='utf-8')
print('Separated nonnumeric review from numeric selections and made uncertain open tasks actually stop incomplete.')
