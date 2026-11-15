"""Assess preserved live outputs; no model rerun or alteration of original evidence."""
from pathlib import Path
from fractions import Fraction
import hashlib
import json
import shutil

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1] / '.codex_work/vra-resource-leveling-20261115'
LIVE = BASE / 'history-live-v1'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


frozen = read(LIVE / 'frozen.json')
receipt = read(LIVE / 'receipt.json')
assert receipt['completed'] and receipt['processes_stopped']
assert digest(LIVE / 'frozen.json') == receipt['frozen_sha256']
current, old = frozen['ids']['current'], frozen['ids']['A']
rows = []
inputs = {'frozen.json': digest(LIVE / 'frozen.json'), 'receipt.json': digest(LIVE / 'receipt.json')}
for case in frozen['tasks']:
    name = case['id']
    task_path = LIVE / (name + '-task.json')
    obs_path = LIVE / (name + '-record-observations.json')
    task, observation = read(task_path), read(obs_path)
    inputs[task_path.name], inputs[obs_path.name] = digest(task_path), digest(obs_path)
    deliveries = task.get('professional_deliveries', [])
    numeric = [(r['record_id'], s) for r in deliveries for s in r.get('statements', [])]
    expected_keys = [(current, 'total_resistance_m2k_w')]
    got_keys = [(rid, s['fact']) for rid, s in numeric]
    current_r = [s for rid, s in numeric if rid == current and s['fact'] == 'total_resistance_m2k_w']
    checks = {
        'completed_transport': task['status'] == 'succeeded',
        'only_requested_numeric_outputs': got_keys == expected_keys,
        'current_R_independent_oracle': len(current_r) == 1 and Fraction(current_r[0]['value']) == Fraction(frozen['oracle']['current_R']),
        'listed_business_records_unchanged': observation['before'] == observation['after'],
    }
    if name == 'M01':
        checks['old_source_only_stale_limitation'] = any(r['record_id'] == old and r.get('limitation_status') == 'stale' and not r.get('statements') for r in deliveries)
    else:
        # The frozen request explicitly requires a current authorization-gap statement.
        # The original output has neither a deferral object nor a corresponding tool event.
        checks['current_authorization_gap_explicit'] = bool(task.get('question_deferral')) and any(
            event.get('tool') == 'requested_defer' and event.get('arguments', {}).get('defer_reason') == 'calculation_not_authorized'
            for event in task.get('events', []))
    rows.append({'id': name, 'passed': all(checks.values()), 'checks': checks,
                 'delivered_fact_keys': got_keys, 'question_deferral': task.get('question_deferral'),
                 'application_task_completion': task['answer'].get('task_completion'),
                 'failure': 'Extra layer R and explicitly excluded U delivered.' if name == 'M01' else 'New calculation obligation omitted; no current authorization-gap explanation.'})
assessment = {'scope': frozen['oracle']['scope'], 'passed': sum(row['passed'] for row in rows),
              'total': len(rows), 'cases': rows, 'score_delta': 0, 'source_sha256': inputs,
              'note': 'succeeded is transport/workflow status, not whole-task acceptance. Prior original receipts remain unchanged.'}
write(LIVE / 'assessment.json', assessment)

# Preserve the known-failing, never-integrated experiment outside application/test discovery.
archive = ROOT / 'validation/agent-intent-first-20261115/experimental-source'
archive.mkdir(parents=True, exist_ok=False)
archive_manifest = {}
for relative, target in [('backend/agent_task_plan.py', 'agent_task_plan.py.txt'),
                         ('tests/test_agent_task_plan.py', 'test_agent_task_plan.py.txt')]:
    source = ROOT / relative
    destination = archive / target
    shutil.copyfile(source, destination)
    assert digest(source) == digest(destination)
    archive_manifest[relative] = {'archived_as': target, 'sha256': digest(destination)}
    source.unlink()
write(archive / 'manifest.json', archive_manifest)
(archive / 'README.md').write_text('''# 停止接入的任务规划实验

此处保存从未接入应用的实验源码原字节，扩展名改为 .py.txt，避免进入应用与默认测试发现。
两版规划语义验收均为 3/8；增加思考预算也没有提高通过数量。第二版仍错误处理否定和矛盾请求。
这不是已交付能力，15项实验契约测试不计入产品验收。本轮不继续调整这些旧题。
原始完整输入、输出与评估保留于本机 outputs/agent-intent-first-20261115；下一产品提交再统一打包。
真实应用的历史来源元数据改动仍独立保留，不能由本实验成绩推断其有效性。
''', encoding='utf-8')

score_path = ROOT / 'docs/CURRENT_SCORE.json'
score = read(score_path)
score['in_progress'] = {
    'branch': 'fix/agent-grounded-planning-20261115', 'score_delta': 0,
    'assessment_status': 'Current uncommitted work is not a newly scored release.',
    'predecessor_pr': 85, 'predecessor_commit': receipt['product_head'],
    'predecessor_validation': 'Exact CI passed: 2170 backend/22 skipped/6 subtests;258 frontend/build;30 API. PR85 remains draft, unmerged, undeployed.',
    'scope': 'Original-raster line candidates, uncertain short-gap hypotheses, versioned human review and SVG export. Public first sheet selected stroke references6/8, not full drawing recognition. Local changes not committed.',
    'agent_experiment': 'Planner semantic checks3/8; no integration; archived outside application. Actual two-turn history regression0/2 whole tasks; values correct but requested scope/new-calculation obligation failed.',
    'report': 'docs/WORK_REVIEW_20261116.md',
    'browser': 'pending_user_deferred'
}
write(score_path, score)
print(json.dumps({'history_whole_tasks': f"{assessment['passed']}/{assessment['total']}",
                  'archived_experiment_files': len(archive_manifest), 'formal_score': score['published']['score'],
                  'historical_candidate_score': score['candidate']['score'], 'current_uncommitted_score': None}, ensure_ascii=False))
