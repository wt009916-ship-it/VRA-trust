"""Pass the new explicit response_mode through protocol fixtures; no assertions removed."""
import ast,json
from pathlib import Path
ROOT=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108')
changes=[]
for p in (ROOT/'tests').glob('test_*.py'):
 s=p.read_text(encoding='utf-8');tree=ast.parse(s);parents={c:n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
 lines=s.splitlines(keepends=True);starts=[];pos=0
 for line in lines:starts.append(pos);pos+=len(line)
 def offset(line,col):return starts[line-1]+len(lines[line-1].encode()[:col].decode())
 callbacks=[]
 for call in ast.walk(tree):
  if not isinstance(call,ast.Call) or not isinstance(call.func,ast.Attribute) or call.func.attr!='setattr' or len(call.args)<3:continue
  if not isinstance(call.args[1],ast.Constant) or call.args[1].value!='complete':continue
  target=call.args[2]
  if isinstance(target,ast.Lambda):callbacks.append(target)
  elif isinstance(target,ast.Name):
   enclosing=parents.get(call)
   while enclosing and not isinstance(enclosing,(ast.FunctionDef,ast.Module)):enclosing=parents.get(enclosing)
   candidates=[n for n in ast.walk(enclosing) if isinstance(n,ast.FunctionDef) and n.name==target.id and n.lineno<call.lineno]
   if candidates:callbacks.append(max(candidates,key=lambda n:n.lineno))
 edits=[]
 for cb in set(callbacks):
  if cb.args.kwarg:continue
  begin=offset(cb.lineno,cb.col_offset)
  if isinstance(cb,ast.Lambda):
   end=s.index(':',begin);prefix=s[begin:end];edits.append((end,end,', **response_options' if prefix.strip()!='lambda' else ' **response_options'))
  else:
   signature_end=s.index('\n',begin);end=s.rfind(')',begin,signature_end)
   assert end>=begin,(p,cb.lineno)
   edits.append((end,end,', **response_options' if s[end-1]!='(' else '**response_options'))
  for call in ast.walk(cb):
   if isinstance(call,ast.Call) and isinstance(call.func,ast.Name) and call.func.id in {'original','complete_original'} and not any(k.arg is None for k in call.keywords):
    end=offset(call.end_lineno,call.end_col_offset)-1
    edits.append((end,end,', **response_options' if call.args or call.keywords else '**response_options'))
 if edits:
  for start,end,new in sorted(set(edits),reverse=True):s=s[:start]+new+s[end:]
  ast.parse(s);p.write_text(s,encoding='utf-8',newline='\n');changes.append({'file':p.name,'edits':len(edits)})
print(json.dumps(changes))
