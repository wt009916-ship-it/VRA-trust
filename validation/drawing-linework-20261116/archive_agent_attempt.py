from pathlib import Path
import hashlib
import json
import shutil
import subprocess

BASE = Path(__file__).parent
ROOT = BASE.parents[1]/'.codex_work/vra-resource-leveling-20261115'
archive = ROOT/'validation/agent-intent-first-20261115/history-source-attempt'
archive.mkdir(parents=True, exist_ok=False)
manifest = {}
for relative in ['backend/agent.py', 'backend/agent_history.py', 'tests/test_agent_history.py', 'tests/test_agent_semantics.py']:
    source = ROOT/relative
    target = archive/(relative.replace('/', '__')+'.txt')
    shutil.copyfile(source, target)
    assert source.read_bytes() == target.read_bytes()
    manifest[relative] = {'archived_as': target.name, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
    if relative in ['backend/agent.py', 'tests/test_agent_semantics.py']:
        source.write_bytes(subprocess.check_output(['git', 'show', 'HEAD:'+relative], cwd=ROOT))
    else:
        source.unlink()
(archive/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
(archive/'README.md').write_text('''# 历史来源元数据尝试：不进入本次产品提交

补充字段的纯契约检查通过，真实应用两轮整题回归0/2，未证明改善任务完成。
保留运行时修改源码原字节及失败输出；产品Agent与测试恢复PR85的相同字节。
不存在以本次实验关闭Agent意图缺陷或增加评分的结论。
''', encoding='utf-8')
assert not subprocess.check_output(['git', 'diff', '--', 'backend/agent.py', 'tests/test_agent_semantics.py'], cwd=ROOT)
print('Archived4 experiment source files; production Agent restored exactly to PR85.')
