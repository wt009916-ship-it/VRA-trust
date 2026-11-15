from pathlib import Path
p=Path('backend/agent_recovery.py')
s=p.read_text(encoding='utf-8').replace("    read_specs = {spec.read_tool: spec for spec in INSPECTIONS.values()}", """    # Frozen calculation plans already track execution and delivery stages.
    read_specs = {} if record.get('calculation_plan_snapshot') else {
        spec.read_tool: spec for spec in INSPECTIONS.values()
    }""")
p.write_text(s,encoding='utf-8')
