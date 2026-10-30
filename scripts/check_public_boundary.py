"""Fail publication if private console source or unresolved local imports enter Git."""
import ast
import re
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
tracked = set(subprocess.check_output(['git', 'ls-files'], cwd=root, text=True).splitlines())
for name in tracked:
    path = root/name
    if name.startswith('backend/') and path.suffix == '.py':
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and decorator.args and isinstance(decorator.args[0], ast.Constant):
                        value = decorator.args[0].value
                        assert not isinstance(value, str) or not value.startswith(('/api/admin/', '/api/developer/')), name
    if name.startswith('frontend/src/') and path.suffix == '.js':
        text = path.read_text(encoding='utf-8')
        assert 'export function mountIdentityAdmin' not in text and 'function developerSettings(' not in text, name
        for relative in re.findall(r"from\s+['\"](\.[^'\"]+)['\"]", text):
            target = (path.parent/relative).resolve().relative_to(root).as_posix()
            assert target in tracked, f'{name} imports untracked/private module: {target}'
print('Public source boundary verified')
