from pathlib import Path

ROOT=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108')
def edit(name, old, new):
    p=ROOT/name;s=p.read_text(encoding='utf-8')
    assert old in s, (name,old[:100])
    p.write_text(s.replace(old,new,1),encoding='utf-8',newline='\n')

edit('backend/agent_outputs.py', 'class OutputItem(Contract):', '''class ExplicitOutput(Contract):
    """User-selected obligations; never synthesized from model or source text."""
    fact_keys: list[str] = Field(default_factory=list, max_length=12)
    explanation_topics: list[Topic] = Field(default_factory=list, max_length=6)

    @model_validator(mode='after')
    def distinct(self):
        if not (self.fact_keys or self.explanation_topics):
            raise ValueError('Select an explicit metric or explanation')
        if len(set(self.fact_keys)) != len(self.fact_keys) or len(set(self.explanation_topics)) != len(self.explanation_topics):
            raise ValueError('Explicit outputs must be distinct')
        return self


class OutputItem(Contract):''')
edit('backend/agent_requests.py', "    @model_validator(mode='after')\n    def scope(self):", "    output_contract: agent_outputs.ExplicitOutput | None = None\n\n    @model_validator(mode='after')\n    def scope(self):")
edit('backend/agent_requests.py', "        return self\n", '''        if self.output_contract:
            entry = agent_outputs.catalog([self.model_dump(mode='json')])[0]
            if not set(self.output_contract.fact_keys) <= set(entry['available_fact_keys']):
                raise ValueError('Explicit metrics must belong to the selected kind and purpose')
            if not set(self.output_contract.explanation_topics) <= set(entry['available_explanation_topics']):
                raise ValueError('Explicit explanation is unsupported for this scope')
        return self
''')
edit('backend/agent.py', "        if self.read_requests:\n", "        if any(r.output_contract for r in self.read_requests) and not self.infer_outputs:\n            raise ValueError('Explicit output contracts require output planning; cannot bypass their verification')\n        if self.read_requests:\n")
edit('backend/agent_outputs.py', "             'available_fact_keys':", "             'user_output_contract': r.get('output_contract'),\n             'available_fact_keys':")
edit('backend/agent_outputs.py', "        '当前计划只表达模型的理解，不证明意图已验证或用户任务已完成。'", "        'user_output_contract非空时，指标和解释是用户逐项选定的硬约束，必须原样覆盖，不增删、不以相近字段替代。原文有其他要求或冲突仍未获核验，不宣称整个问题完成。'\n        '当前计划只表达模型的理解，不证明意图已验证或用户任务已完成。'")
edit('backend/agent_outputs.py', "        variants.append(item)", """        explicit = entry.get('user_output_contract')
        if explicit:
            for field in ('fact_keys', 'explanation_topics'):
                props[field] = {'type':'array', 'const':explicit[field]}
            props['clarification_reason'] = {'type':'null'}
            props['clarification_question'] = {'type':'null'}
        variants.append(item)""")
edit('backend/agent_outputs.py', "        saved = item.model_dump(mode='json', exclude_none=True)", """        explicit = requests[item.request_key].get('output_contract')
        if explicit and (item.clarification_question or any(
                set(getattr(item, field)) != set(explicit[field])
                for field in ('fact_keys', 'explanation_topics'))):
            raise core.ValidationError('Model plan cannot replace, omit or expand user-selected outputs')
        saved = item.model_dump(mode='json', exclude_none=True)
        saved['requirement_origin'] = 'user_selected' if explicit else 'model_inferred'
        saved['user_contract_hash'] = core.hash_json(explicit) if explicit else None""")
edit('backend/agent_outputs.py', "    if plan['version'] != version() or plan['question_hash'] != core.hash_json(record['question']):", """    contracts_current = all(
        item.get('user_contract_hash') == (core.hash_json(r['output_contract']) if r.get('output_contract') else None)
        for r in record['read_requests']
        for item in plan['items'] if item['request_key'] == r['request_key'])
    if not contracts_current or plan['version'] != version() or plan['question_hash'] != core.hash_json(record['question']):""")
edit('backend/agent_outputs.py', "    answer['output_contract_notice'] =", "    answer['user_selected_output_keys'] = [r['request_key'] for r in record['read_requests'] if r.get('output_contract')]\n    answer['free_question_coverage'] = 'not_verified'\n    answer['output_contract_notice'] =")
edit('backend/agent.py', "                        if wanted and (wanted.get('clarification_question') or not wanted['fact_keys']):", """                        explicit = request.get('output_contract')
                        if explicit and any(s.fact not in explicit['fact_keys'] for s in delivery.statements):
                            raise ToolRefusal('Numeric delivery is outside the user-selected metric contract')
                        if wanted and (wanted.get('clarification_question') or not wanted['fact_keys']):""")
edit('backend/agent_semantics.py', "class Delivery(Contract):", """def statement_instruction():
    return 'Copy every source fact field: ' + ', '.join(Statement.model_fields) + '. Preserve nulls; energy_context is mandatory for energy facts. Source hash must match the read record.'


class Delivery(Contract):""")
edit('backend/agent_semantics.py', "'开放问答需用professional_deliver提交所需事实的value/unit/period/study_years/area_m2及当前hash。'", "statement_instruction()")
edit('backend/agent.py', 'from .agent_semantics import NumericDelivery,', 'from .agent_semantics import statement_instruction, NumericDelivery,')
edit('backend/agent.py', "                    'read返回explanation_facts，按该事实项的value、unit、period、study_years、area_m2提交，record_hash来自hash。'", "                    + statement_instruction() +")
edit('backend/agent.py', "                    parameters['$defs'][definition]['required'].append('finish')", """                    if not limited and candidates and all(ds.kind in agent_energy.KINDS for ds, _ in candidates):
                        statement = parameters['$defs']['Statement']
                        statement['required'] = list(dict.fromkeys(statement['required'] + ['energy_context']))
                        statement['properties']['energy_context'] = {'$ref':'#/$defs/EnergyContext'}
                    parameters['$defs'][definition]['required'].append('finish')""")
edit('backend/extensions.py', "                'tool_catalog_scope':'default_read_only',", "                'output_catalog': __import__('backend.agent_outputs', fromlist=['public_catalog']).public_catalog(),\n                'tool_catalog_scope':'default_read_only',")
edit('backend/agent_outputs.py', 'def constrain_tool(tool, requests, question):', '''def public_catalog():
    return {kind: {'facts': [{'key': key, 'label': intent_catalog.MEANINGS[kind][key]} for key in keys],
                   'topics': catalog([{'request_key':'catalog', 'kind':kind, 'purpose':'results'}])[0]['available_explanation_topics']}
            for kind, keys in FACTS.items()}


def constrain_tool(tool, requests, question):''')
edit('backend/agent_energy.py', "    if topic=='period':return '原生及账单期间、时间映射均保留在energy_context；开始包含、结束不包含，原生年度不一定等于账单年份或覆盖期间。'+str(c)", """    if topic=='period':
        text = '原生年度：' + str(c.get('native_year', '未知')) + '。'
        if c.get('original_bill_start'):
            text += '原始账期：' + c['original_bill_start'] + ' 至 ' + c['original_bill_end'] + '；映射模拟期间：' + c['mapped_native_start'] + ' 至 ' + c['mapped_native_end'] + '；映射方式：' + c['alignment'] + '。'
        elif c.get('native_start'):
            text += '模拟期间：' + c['native_start'] + ' 至 ' + c['native_end'] + '。'
        return text + '开始包含、结束不包含；原生年度、账单年份和实际覆盖期间分别核验，参考数据不是实楼校准。'""")
print('backend edits complete')
