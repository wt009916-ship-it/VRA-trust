"""Explicit integration repair rerun; never replace failed candidate evidence."""
from pathlib import Path
import hashlib,json
base=Path(__file__).parent
source=base/'run_intent_review_comparison.py'
text=source.read_text(encoding='utf-8')
old="out=Path('C:/Users/18483/AppData/Local/Temp/vra-intent-review-model-20261108')/args.variant"
new="out=Path('C:/Users/18483/AppData/Local/Temp/vra-intent-review-model-20261108')/'candidate-schema-repair'"
assert text.count(old)==1
text=text.replace(old,new)
assert "if args.variant=='candidate':payload['review_intent']=True" in text
decision={
  'type':'integration-repair-rerun, not an untouched holdout',
  'original_runner_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
  'failed_arm':'candidate: 0/20, 27 model calls; all retained',
  'reason':'Unsupported properties + oneOf/anyOf schema combination documented by llama.cpp',
  'source':'https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md#json-schemas--gbnf',
  'change':'Complete disjoint schema branches; no model, prompt, question, gold, budget or scoring changes',
  'adoption':'Original gate remains necessary; a pass still needs a new untouched holdout before adoption',
  'stop_rule':'If repaired comparison fails gate, stop this second-pass approach; do not tune prompts on these cases'
}
target=base/'intent-review-schema-repair-decision.json'
assert not target.exists()
target.write_text(json.dumps(decision,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
exec(compile(text,str(source),'exec'))
