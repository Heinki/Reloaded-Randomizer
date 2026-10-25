"""Reviewed special production access, isolated from installed enemy types."""

from copy import deepcopy

from .buff_links import linked_types

FACTORIES = {'GDI': 'GAWEAP', 'Nod': 'NAWEAP',
             'ThirdSide': 'YAWEAP', 'TSGDISide': 'TSGAWEAP', 'TSNodSide': 'TSNAWEAP'}


def reviewed_rules(rules, access, *, deliveries=()):
    """Use the same portable models as campaign rewards without campaign clone identities."""
    if not access and not deliveries:
        return rules, set()
    from randomizer.rewards.reloaded_roster import randomizer_unit_template_values
    templates = randomizer_unit_template_values()
    reviewed = dict(rules)
    forms, included = set(), set()
    categories = {kind: category for category in (
        'BuildingTypes', 'InfantryTypes', 'VehicleTypes', 'AircraftTypes')
        for kind in rules[category].values()}

    def include(original, *, unlock):
        if original in included:
            return
        if original not in rules:
            raise ValueError(f'Special unit {original} is not installed.')
        included.add(original)
        if unlock:
            forms.add(original)
        row = deepcopy(templates.get(original, rules[original]))
        if not unlock:
            # Portable reward templates expose hidden Secret Lab units for
            # campaign rewards. A periodic gift must retain native production
            # gates, and must never hide an ordinary Flak Track or tank.
            row['TechLevel'] = rules[original].get('TechLevel', '-1')
        for _, target in linked_types(row, categories):
            include(target, unlock=unlock)
        reviewed[original] = row

    for original in access:
        if original not in templates:
            raise ValueError(f'Special access requires a reviewed reward model: {original}.')
        include(original, unlock=True)
    for original in deliveries:
        if original not in templates:
            raise ValueError(f'Special delivery requires a reviewed reward model: {original}.')
        include(original, unlock=False)
    return reviewed, forms


def production_access(row, friends, country, rules):
    """Replace mission/stolen-tech gates with the faction's ordinary factory."""
    for field in tuple(row):
        if field.startswith(('Prerequisite', 'FactoryOwners')):
            del row[field]
    row.update(TechLevel='1', Owner=','.join(friends), RequiredHouses=','.join(friends),
               ForbiddenHouses='', Prerequisite=FACTORIES[rules[country]['Side']],
               BuiltAt=FACTORIES[rules[country]['Side']])
