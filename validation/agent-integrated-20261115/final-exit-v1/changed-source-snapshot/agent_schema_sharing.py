"""Share identical large choice contracts without dropping semantics or evidence."""
import copy
import json
from collections import Counter


DATA_KEYS = {'enum', 'const', 'default', 'examples'}


def compact_choices(schema):
    counts, nodes = Counter(), {}
    scoped = False

    def choice(node):
        return (isinstance(node, dict) and node.get('type') == 'array'
                and isinstance(node.get('items'), dict)
                and isinstance(node['items'].get('enum'), list)
                and all(isinstance(value, str) for value in node['items']['enum'])
                and len(json.dumps(node, ensure_ascii=False)) >= 256)

    def key(node):
        return json.dumps(node, ensure_ascii=False, sort_keys=True)

    def visit(value):
        nonlocal scoped
        if isinstance(value, dict):
            if '$id' in value or '$anchor' in value or '$dynamicAnchor' in value:
                scoped = True
            if choice(value):
                identity = key(value)
                counts[identity] += 1
                nodes[identity] = value
            for name, child in value.items():
                if name not in DATA_KEYS:
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(schema)
    # Moving a schema under a different identifier could alter reference resolution.
    # Generated VRA tool contracts have one root scope; keep other schemas unchanged.
    if scoped:
        return copy.deepcopy(schema)
    names = {}
    used = set(schema.get('$defs', {}))
    for identity, count in counts.items():
        if count < 2:
            continue
        index = len(names)
        name = 'vra_shared_choices_' + str(index)
        while name in used:
            index += 1
            name = 'vra_shared_choices_' + str(index)
        names[identity] = name
        used.add(name)

    def rewrite(value):
        if isinstance(value, dict):
            identity = key(value) if choice(value) else None
            if identity in names:
                return {'$ref': '#/$defs/' + names[identity]}
            return {name: copy.deepcopy(child) if name in DATA_KEYS else rewrite(child)
                    for name, child in value.items()}
        if isinstance(value, list):
            return [rewrite(child) for child in value]
        return value

    result = rewrite(schema)
    if names:
        result.setdefault('$defs', {}).update({name: copy.deepcopy(nodes[identity])
                                              for identity, name in names.items()})
    return result
