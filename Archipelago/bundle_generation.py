"""Package shared generation code under the APWorld's private namespace."""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_NAME = "cnc_reloaded"

STATIC_READER = '''"""Read immutable generation configuration from the APWorld archive."""
from copy import deepcopy
from functools import lru_cache
from importlib.resources import files
import json
from .schema import validate_sections, StaticConfigError

@lru_cache(maxsize=None)
def _read(relative_path):
    if relative_path.startswith('/') or '..' in relative_path.split('/'):
        raise StaticConfigError('Invalid static config path')
    resource = files(__package__.rsplit('.randomizer', 1)[0]).joinpath('configs', relative_path)
    document = json.loads(resource.read_text(encoding='utf-8-sig'))
    if document.get('schema_version') != 1:
        raise StaticConfigError('Unsupported static config schema')
    sections = document['sections']
    validate_sections(relative_path, sections, str(resource))
    return sections

def load_static_config(relative_path):
    return deepcopy(_read(relative_path))

load_static_config.cache_clear = _read.cache_clear

def static_config_section(relative_path, section, expected_type):
    result = load_static_config(relative_path)[section]
    if not isinstance(result, expected_type):
        raise StaticConfigError('Invalid static config section')
    return result
'''


def generation_files():
    """Yield deterministic archive entries for the source dependency closure."""
    pending = ['randomizer.generation.service', 'Archipelago.run_manifest']
    seen = set()
    output = {f'{MODULE_NAME}/_vendor/__init__.py': b''}
    from randomizer.content.inventory import read_rules_sections
    rules, _source = read_rules_sections()
    rules_json = json.dumps(rules, ensure_ascii=False, separators=(',', ':'))
    output[f'{MODULE_NAME}/_vendor/randomizer/content/_generation_rules.py'] = (
        'import json\nRULES = json.loads(' + repr(rules_json) + ')\n'
    ).encode('utf-8')
    while pending:
        module = pending.pop()
        if module in seen:
            continue
        seen.add(module)
        path = ROOT.joinpath(*module.split('.')).with_suffix('.py')
        is_package = not path.is_file()
        if is_package:
            path = ROOT.joinpath(*module.split('.'), '__init__.py')
        if not path.is_file():
            continue
        parts = module.split('.')
        pending.extend('.'.join(parts[:index]) for index in range(1, len(parts)))
        source = STATIC_READER if module == 'randomizer.config.static' else path.read_text(encoding='utf-8-sig')
        tree = ast.parse(source)
        if module == 'randomizer.content.inventory':
            node = next(
                node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == 'read_rules_sections'
            )
            node.body = ast.parse(
                "from ._generation_rules import RULES\nreturn RULES, 'bundled-generation-rules'"
            ).body
        package = parts if is_package else parts[:-1]
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level:
                    target_parts = package[:len(package) - node.level + 1]
                    if node.module:
                        target_parts += node.module.split('.')
                    target = '.'.join(target_parts)
                else:
                    target = node.module or ''
                if target.split('.')[0] in {'randomizer', 'Archipelago'}:
                    pending.append(target)
                    pending.extend(target + '.' + alias.name for alias in node.names if alias.name != '*')
                    if not node.level:
                        node.level = len(package) + 1
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split('.')[0] in {'randomizer', 'Archipelago'}:
                        raise ValueError(f'Use from-imports for bundled local module: {module}: {alias.name}')
        relative = path.relative_to(ROOT).as_posix()
        output[f'{MODULE_NAME}/_vendor/{relative}'] = (ast.unparse(tree) + '\n').encode('utf-8')
    for path in sorted((ROOT / 'configs').rglob('*.json')):
        parts = path.relative_to(ROOT / 'configs').parts
        if 'player' not in parts and path.name not in {'.bundle_manifest.json', 'bundle_manifest.json'}:
            output[f'{MODULE_NAME}/_vendor/{path.relative_to(ROOT).as_posix()}'] = path.read_bytes()
    return sorted(output.items())
