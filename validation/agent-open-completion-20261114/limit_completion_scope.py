from pathlib import Path
p=Path('backend/agent_recovery.py');s=p.read_text(encoding='utf-8').replace("        if spec is None or event['status'] != 'succeeded':","        if record.get('objective') != 'open_ended' or spec is None or event['status'] != 'succeeded':")
p.write_text(s,encoding='utf-8')
p=Path('tests/test_agent_metric_reads.py');s=p.read_text(encoding='utf-8').replace("    record={'events':[{'tool':'utility_comparison_read','status':'succeeded',\n        'origin':'controller'","    record={'objective':'open_ended','events':[{'tool':'utility_comparison_read','status':'succeeded',\n        'origin':'controller'")
s += """
def test_inspection_read_is_already_its_delivery_without_open_task_obligations():
    from backend import agent_recovery
    record={'objective':'inspect_thermal','events':[
        {'tool':'thermal_read','status':'succeeded','origin':'model',
         'result':{'thermal_id':'thermal_'+'b'*32}}]}
    assert agent_recovery.unresolved(record)==[]
"""
p.write_text(s,encoding='utf-8')
