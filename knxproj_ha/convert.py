import logging
from pathlib import Path
import io
from xknxproject.models import KNXProject
from xknxproject import XKNXProj
from .models import HAConfig, Light
import yaml

logger = logging.getLogger("knxproj_ha")

def _get_lights_ga(group_addresses):
    lights = {}
    for ga, values in group_addresses.items():
        base_name = values['name'].replace(' Helligkeit', '')

        if ga.startswith(('5/0/', '5/1/', '5/2/')) and values['dpt'] and values['dpt']['main'] == 1:
            lights.setdefault(base_name, Light(name=base_name)).address = ga
        elif '5/3/' in ga and values['dpt'] is None:
            lights.setdefault(base_name, Light(name=base_name)).brightness_address = ga
        elif '5/5/' in ga and values['name'].endswith('Helligkeit'):
            lights.setdefault(base_name, Light(name=base_name)).brightness_state_address = ga
        elif '5/5/' in ga and values['dpt']['main'] == 1:
            lights.setdefault(base_name, Light(name=base_name)).state_address = ga

    return list(lights.values())


def convert(fp: Path, language: str = "de-DE") -> HAConfig:
    knxproj: XKNXProj = XKNXProj(
        path=fp,
        language="de-DE",  # optional
    )
    logger.debug("Start parsing KNX project file ...")
    project: KNXProject = knxproj.parse()
    logger.debug("  ... parsing finished")

    for o in project:
        logger.debug(o)
        logger.debug(project[o])
        logger.debug('\n\n\n')

    for ga in project["group_addresses"]:
        logger.debug(project["group_addresses"][ga])

    lights = _get_lights_ga(project["group_addresses"])
    ha_config = HAConfig(light=lights)
    return ha_config

class OrderedDumper(yaml.SafeDumper):
    """A custom YAML dumper that respects the order of keys in OrderedDict."""

def _ordered_dump(data, stream=None, Dumper=OrderedDumper, **kwds):
    """Dump YAML with OrderedDict."""
    class OrderedDumper(Dumper):
        pass

    def _dict_representer(dumper, data):
        return dumper.represent_mapping(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, data.items())

    OrderedDumper.add_representer(dict, _dict_representer)
    return yaml.dump(data, stream, OrderedDumper, **kwds)

def write(ha_config: HAConfig, dp: Path) -> None:
    """Serialize the given Home Assistant config into YAML format."""
    filtered_config = {'knx': {'light': []}}
    for light in ha_config.light:
        light_dict = light.dict()
        # Reorder dict to have 'name' first and exclude empty addresses
        ordered_light = {'name': light_dict.pop('name')}
        for key, value in light_dict.items():
            if value:
                ordered_light[key] = value
        filtered_config['knx']['light'].append(ordered_light)

    yaml_str = _ordered_dump(filtered_config, indent=2, allow_unicode=True)
    print(yaml_str)
