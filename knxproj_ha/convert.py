import logging
from pathlib import Path
import io
from xknxproject.models import KNXProject
from xknxproject import XKNXProj
from .models import HAConfig, BinarySensor, Sensor, Light
import yaml

logger = logging.getLogger("knxproj_ha")

def _get_lights_ga(group_addresses):
    lights = {}
    for ga, values in group_addresses.items():
        base_name = values['name'].replace(' Helligkeit', '')

        if ga.startswith(('5/0/', '5/1/', '5/2/')) and values['dpt'] and values['dpt']['main'] >= 2:
            lights.setdefault(base_name, Light(name=base_name)).address = ga
        elif '5/3/' in ga and values['dpt'] is None:
            lights.setdefault(base_name, Light(name=base_name)).brightness_address = ga
        elif '5/5/' in ga and values['name'].endswith('Helligkeit'):
            lights.setdefault(base_name, Light(name=base_name)).brightness_state_address = ga
        elif '5/5/' in ga and values['dpt']['main'] == 1:
            lights.setdefault(base_name, Light(name=base_name)).state_address = ga

    return list(lights.values())

def _get_binary_sensors_ga(group_addresses, existing_lights = []):
    binary_sensors = []
    used_addresses = {light.state_address for light in existing_lights}

    for ga, values in group_addresses.items():
        if (values['dpt'] and values['dpt']['main'] == 1 and values['dpt']['sub'] in (2,3,4,5,6,11,12,13,14,18)
                and ga not in used_addresses):
            binary_sensors.append(BinarySensor(name=values["name"], state_address=ga))
    return binary_sensors

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
    binary_sensors = _get_binary_sensors_ga(project["group_addresses"], lights)
    print(binary_sensors)
    ha_config = HAConfig(light=lights, binary_sensors=binary_sensors)
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
    ha_config_dict = ha_config.dict()
    filtered_config = {'knx': {}}

    for entity_type, entities in ha_config_dict.items():
        filtered_config['knx'][entity_type] = []
        for entity in entities:
            # Check if 'name' exists in the entity dictionary and reorder
            if 'name' in entity:
                ordered_entity = {'name': entity.pop('name')}
                for key, value in entity.items():
                    if value:
                        ordered_entity[key] = value
                filtered_config['knx'][entity_type].append(ordered_entity)

    yaml_str = _ordered_dump(filtered_config, indent=2, allow_unicode=True)
    print(yaml_str)
