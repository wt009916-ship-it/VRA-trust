"""Reference exact repeated fact catalogs; never omit unique tool evidence."""
import copy
import json

from . import core


def share_catalogs(messages):
    result = copy.deepcopy(messages)
    ids = [m['tool_call_id'] for m in messages if m.get('role') == 'tool' and m.get('tool_call_id')]
    if len(set(ids)) != len(ids):
        return result  # A repeated ID would make the reference ambiguous.
    known = {}
    for message in result:
        if message.get('role') != 'tool' or not message.get('tool_call_id'):
            continue
        try:
            content = json.loads(message.get('content', ''))
        except (ValueError, TypeError):
            continue
        changed = False

        def visit(node, pointer=''):
            nonlocal changed
            if isinstance(node, list):
                for index, child in enumerate(node):
                    visit(child, pointer + '/' + str(index))
            elif isinstance(node, dict):
                catalog = node.get('available_fact_catalog')
                if (isinstance(catalog, list) and len(json.dumps(catalog, ensure_ascii=False)) > 2000
                        and 'available_fact_catalog_reference' not in node):
                    digest = core.hash_json(catalog)
                    # Full equality, not hash alone, controls sharing.
                    previous = known.get(digest)
                    if previous and previous['tool_call_id'] != message['tool_call_id'] and previous['catalog'] == catalog:
                        node['available_fact_catalog_reference'] = {
                            'tool_call_id': previous['tool_call_id'], 'json_pointer': previous['json_pointer'],
                            'sha256': digest, 'entry_count': len(catalog),
                            'meaning': 'Identical complete catalog already supplied; all entries, labels and units unchanged.'}
                        del node['available_fact_catalog']
                        changed = True
                    else:
                        known[digest] = {'catalog': copy.deepcopy(catalog),
                                         'tool_call_id': message['tool_call_id'],
                                         'json_pointer': pointer + '/available_fact_catalog'}
                for name, child in list(node.items()):
                    if name not in {'available_fact_catalog', 'available_fact_catalog_reference'}:
                        visit(child, pointer + '/' + name.replace('~', '~0').replace('/', '~1'))

        visit(content)
        if changed:
            message['content'] = json.dumps(content, ensure_ascii=False)
    return result
