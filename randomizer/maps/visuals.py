"""Map-local presentation repairs that do not change combat effects."""

from randomizer.maps.ini import all_section_value_maps


def iron_curtain_visual_rules(lines, installed_sections):
    """Give the installed invisible Iron Curtain tint a visible red color.

    Reloaded selects ColorAdd index 0 (None=0,0,0). Its SHP rendering path
    therefore receives no color, including Titans. Reuse StrongRed without
    changing the shared None entry, duration, targeting or protection values.
    An explicit mission tint always takes precedence.
    """
    sections = {
        name.casefold(): values
        for name, values in all_section_value_maps(lines).items()
    }
    general = sections.get('audiovisual', {})
    if 'ironcurtaincolor' in general:
        return {}
    installed = {
        str(name).casefold(): values
        for name, values in installed_sections.items()
    }
    audio = {
        str(key).casefold(): value
        for key, value in installed.get('audiovisual', {}).items()
    }
    colors = {
        str(key).casefold(): value
        for key, value in installed.get('coloradd', {}).items()
    }
    colors.update(sections.get('coloradd', {}))
    names = list(colors)
    try:
        index = int(audio.get('ironcurtaincolor', '0'))
        current = colors[names[index]] if index >= 0 else ''
        if any(int(part.strip()) for part in str(current).split(',')):
            return {}
        if not any(int(part.strip()) for part in str(colors['strongred']).split(',')):
            return {}
    except (ValueError, IndexError, KeyError):
        return {}
    return {'AudioVisual': {'IronCurtainColor': str(names.index('strongred'))}}
