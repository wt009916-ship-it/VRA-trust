from pathlib import Path
out=Path(__file__).parent
text=(out/'verify_git_source_v1.py').read_text()
old="assert name in {'frontend/src/main.js','fixtures/test/native_zone_sizing_projection.json'},name"
new="assert name == 'frontend/src/main.js' or name.endswith('.json'),name"
assert old in text
text=text.replace(old,new).replace("out/'git-source-v1.json'","out/'git-source-v2.json'")
with (out/'verify_git_source_v2.py').open('x') as f:f.write(text)
