from pathlib import Path
p=Path('backend/agent_energy.py')
with p.open('a',encoding='utf-8') as f:
 f.write('''

def relationship(facts):
    """Explain comparable source dimensions using current verified field receipts."""
    if len(facts) < 2 or any(not fact.get('energy_context') for fact in facts):
        return None
    sources = []
    for fact in facts:
        context = fact['energy_context']
        sources.append({
            'fact': fact['fact'], 'unit': fact['unit'],
            'carrier': context['carrier'], 'boundary': context['boundary'],
            'native_start': context['native_start'], 'native_end': context['native_end'],
            'bill_start': context['bill_start'], 'bill_end': context['bill_end'],
            'basis': context['basis'], 'data_nature': context['data_nature'],
            'run_id': context['run_id'],
        })
    units = {source['unit'] for source in sources}
    carriers = {source['carrier'] for source in sources}
    periods = {(source['native_start'], source['native_end'],
                source['bill_start'], source['bill_end']) for source in sources}
    text = '这些字段的单位为' + '、'.join(sorted(units)) + '。'
    if len(units) == 1 and units == {'kWh'}:
        text += 'kWh表示能量大小，能源载体由各字段的carrier确定。'
    text += '当前字段对应的能源载体为' + '、'.join(sorted(carriers)) + '。'
    if len(carriers) > 1:
        text += '不同能源载体的量须分别归属。天然气量不能作为耗电量，跨载体换算需另有转换效率与系统边界依据。'
    text += ('这些字段的来源期间一致。' if len(periods) == 1 else
             '这些字段的来源期间有差异，比较前需对齐覆盖期间。')
    text += '各字段保留原始统计口径与数据性质。'
    return {'topic': 'energy_relationship', 'text': text, 'sources': sources,
            'origin': 'application_from_current_verified_sources'}
''')
p=Path('backend/agent_outputs.py');s=p.read_text(encoding='utf-8')
s=s.replace("'scope', 'status', 'history']","'scope', 'status', 'history', 'energy_relationship']",1)
s=s.replace("else ['period'] if r['kind'] in agent_energy.KINDS", "else ['period', 'energy_relationship'] if r['kind'] in agent_energy.KINDS")
s=s.replace("Requested explanation topics: meaning, area, period, scope, status, history.", "Requested topics: meaning, area, period, scope, status, history, energy_relationship (compare two or more requested energy facts by unit/carrier/period).")
s=s.replace("        normalized.append(saved)", """        if 'energy_relationship' in item.explanation_topics and len(item.fact_keys) < 2:
            raise core.ValidationError('Energy relationships require at least two selected energy facts')
        normalized.append(saved)""")
s=s.replace("    if topic == 'history':\n", """    if topic == 'energy_relationship':
        relation = agent_energy.relationship(facts)
        return relation['text'] if relation else '等待至少两个已核验的能耗字段及来源上下文。'
    if topic == 'history':
""",1)
s=s.replace("        ready = state in", """        relationship_missing = ('energy_relationship' in needed['explanation_topics']
                                and agent_energy.relationship(facts) is None)
        ready = state in""")
s=s.replace(" and not missing\n", " and not missing and not relationship_missing\n")
p.write_text(s,encoding='utf-8')
p=Path('backend/agent_semantics.py');s=p.read_text(encoding='utf-8')
s=s.replace("statements.append({'record_id': request.record_id, 'name': record_name(record), 'facts': checked['statements']})", """statements.append({'record_id': request.record_id, 'name': record_name(record),
                                   'facts': checked['statements'],
                                   'energy_relationship': agent_energy.relationship(checked['statements'])})""")
p.write_text(s,encoding='utf-8')
p=Path('frontend/src/agent-artifacts.js');s=p.read_text(encoding='utf-8')
s=s.replace("</dl><small class=\"mono\">${esc(s.record_id)}", "</dl>${s.energy_relationship?'<p>'+esc(s.energy_relationship.text)+'</p>':''}<small class=\"mono\">${esc(s.record_id)}")
p.write_text(s,encoding='utf-8')
