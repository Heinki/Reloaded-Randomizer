"""Discover alternate TechnoTypes reached through native mode changes."""

TRANSFORM_REFERENCE_KEYS = frozenset({
    'deploysinto', 'undeploysinto', 'convert.deploy',
    'convert.deploy.reversedas', 'convert.land', 'convert.water', 'reversedas',
})

TYPE_CATEGORIES = {
    'InfantryTypes': 'infantry',
    'VehicleTypes': 'units',
    'AircraftTypes': 'aircraft',
    'BuildingTypes': 'defenses',
}


def techno_type_categories(sections):
    return {
        str(identifier).strip().upper(): category
        for registry, category in TYPE_CATEGORIES.items()
        for identifier in sections.get(registry, {}).values()
    }


def linked_transform_families(sections, root_ids):
    """Follow outgoing links, without adopting unrelated AI variants.

    Each approved root owns its reachable support forms. Reverse lookups use
    that same family, but incoming links from AI/story units do not grant
    those identities player access or buffs.
    """
    names = {str(name).upper(): name for name in sections}
    categories = techno_type_categories(sections)
    families = {}
    for root_id in sorted(root_ids):
        root_id = str(root_id).upper()
        pending = [root_id]
        visited = set()
        while pending:
            source_id = pending.pop()
            if source_id in visited:
                continue
            visited.add(source_id)
            for key, value in sections.get(names.get(source_id), {}).items():
                if str(key).lower() not in TRANSFORM_REFERENCE_KEYS:
                    continue
                for token in str(value).split(','):
                    target_id = token.strip().upper()
                    if target_id in categories and target_id in names:
                        pending.append(target_id)
        if len(visited) > 1:
            families[root_id] = frozenset(visited)
    return families
