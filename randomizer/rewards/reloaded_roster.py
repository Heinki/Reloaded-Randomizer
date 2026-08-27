"""Installed-rules clone templates for approved C&C Reloaded content."""

from functools import lru_cache

from randomizer.config.game_profile import GENERATED_TYPE_PREFIX
from randomizer.config.static import load_static_config
from randomizer.content.inventory import read_rules_sections


_CONTENT = load_static_config('rewards/reloaded_content_catalogue.json')[
    'content'
]


def _approved_source_ids():
    result = set()
    for records in _CONTENT['units'].values():
        for record in records:
            if str(record['id']).upper().endswith('_AI'):
                continue
            if any(
                review['status'] == 'approved'
                for review in record['reviews'].values()
            ):
                result.add(record['id'].upper())
    for record in _CONTENT['defenses']:
        if str(record['id']).upper().endswith('_AI'):
            continue
        if any(
            review['status'] == 'approved'
            for review in record['reviews'].values()
        ):
            result.add(record['id'].upper())
    return frozenset(result)


APPROVED_CLONE_SOURCE_IDS = _approved_source_ids()


def randomizer_unit_id(source_id):
    clone_id = GENERATED_TYPE_PREFIX + str(source_id or '').strip().upper()
    if len(clone_id) > 24:
        raise ValueError(f'Generated TechnoType ID exceeds 24 bytes: {clone_id}')
    return clone_id


@lru_cache(maxsize=1)
def randomizer_unit_template_values():
    """Copy native installed values without changing authored map identities."""
    sections, _source = read_rules_sections()
    names = {str(name).upper(): name for name in sections}
    templates = {}
    missing = []
    for source_id in sorted(APPROVED_CLONE_SOURCE_IDS):
        actual = names.get(source_id)
        values = dict(sections.get(actual, {})) if actual else {}
        if not values:
            missing.append(source_id)
            continue
        values.setdefault('Image', source_id)
        templates[source_id] = values
    if missing:
        raise ValueError(
            'Installed rules lack approved clone source sections: '
            + ', '.join(missing)
        )
    return templates


@lru_cache(maxsize=None)
def randomizer_unit_ids_with_behavior(key, expected_value='yes'):
    wanted_key = str(key).strip().lower()
    wanted_value = str(expected_value).strip().lower()
    return frozenset(
        source_id
        for source_id, values in randomizer_unit_template_values().items()
        if any(
            str(name).strip().lower() == wanted_key
            and str(value).strip().lower() == wanted_value
            for name, value in values.items()
        )
    )


@lru_cache(maxsize=1)
def randomizer_unit_roster():
    templates = randomizer_unit_template_values()
    clone_ids = {
        source_id: randomizer_unit_id(source_id)
        for source_id in templates
    }
    return (), clone_ids, templates
