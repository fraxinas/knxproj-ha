import logging
from pathlib import Path
from xknxproject.models import KNXProject
from xknxproject import XKNXProj
from .models import HAConfig, BinarySensor, Sensor, Light, Climate, Cover, BaseModel
import yaml

class OrderedDumper(yaml.SafeDumper):
    """A custom YAML dumper that respects the order of keys in OrderedDict."""

def _dict_representer(dumper, data):
    return dumper.represent_mapping(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, data.items())

OrderedDumper.add_representer(dict, _dict_representer)

def _ordered_dump(data, stream=None, Dumper=OrderedDumper, **kwds):
    """Dump YAML with OrderedDict."""
    return yaml.dump(data, stream, OrderedDumper, **kwds)

def _check_dpt(values, dpt_main, dpt_sub = None):
    if not (values and values['dpt']):
        return False

    # Check if dpt_main matches
    if not values['dpt']['main'] == dpt_main:
        return False

    # If dpt_sub is None, no further check is required
    if dpt_sub is None:
        return True

    # If dpt_sub is a lambda function, call it
    if callable(dpt_sub):
        return dpt_sub(values['dpt']['sub'])

    # Otherwise, check if dpt_sub matches
    return values['dpt']['sub'] == dpt_sub


class KNXHAConverter:
    TARGET_TEMPERATURE_GROUPNAME = "Soll-Temperaturen"
    OPERATION_MODE_GROUPNAME = "Betriebsmodi"
    ON_OFF_STATE_GROUPNAME = "Meldung Heizen"
    CURRENT_TEMPERATURE_GROUPNAME = "Ist-Temperaturen"

    def __init__(self, project_file_path, language='de-DE'):
        self.project_file_path = project_file_path
        self.language = language
        self.processed_addresses = set()
        self.logger = logging.getLogger("knxproj_ha")


    def _find_group_range_by_name(self, group_ranges, name):
        for main_range, main_range_data in group_ranges.items():
            for sub_range, sub_range_data in main_range_data.get('group_ranges', {}).items():
                if sub_range_data.get('name') == name:
                    return sub_range_data.get('group_addresses', [])
        self.logger.warning(f"No group addresses found for group name '{name}'")
        return []


    def _get_lights_ga(self, group_addresses):
        lights = {}
        for ga, values in group_addresses.items():
            base_name = values['name'].replace(' Helligkeit', '')

            if ga.startswith(('5/0/', '5/1/', '5/2/')) and _check_dpt(values, 1, 1):
                lights.setdefault(base_name, Light(name=base_name)).address = ga
                self.processed_addresses.add(ga)
            elif '5/3/' in ga and values['dpt'] and _check_dpt(values, 5, 1):
                lights.setdefault(base_name, Light(name=base_name)).brightness_address = ga
            elif '5/5/' in ga and values['name'].endswith('Helligkeit') and _check_dpt(values, 5, 1):
                lights.setdefault(base_name, Light(name=base_name)).brightness_state_address = ga
            elif '5/5/' in ga and _check_dpt(values, 5, 11):
                lights.setdefault(base_name, Light(name=base_name)).state_address = ga
                self.processed_addresses.add(ga)

        return list(lights.values())


    def _get_climate_ga(self, project):
        climates = {}

        def process_climate_group(name, dpt_main, dpt_sub, field_name, warning_msg):
            sub_group_addresses = self._find_group_range_by_name(project["group_ranges"], name)
            all_group_addresses = project["group_addresses"]
            for address in sub_group_addresses:
                values = all_group_addresses.get(address)
                if values and values['dpt'] == {'main': dpt_main, 'sub': dpt_sub}:
                    base_name = values['name']
                    climates.setdefault(base_name, Climate(
                        name=base_name,
                        temperature_address='',
                        target_temperature_address='',
                        operation_mode_address='',
                        on_off_state_address='')
                    ).__setattr__(field_name, values['address'])
                    self.processed_addresses.add(address)
                else:
                    self.logger.warning(warning_msg.format(values))

        # Process different climate-related group addresses
        process_climate_group(self.TARGET_TEMPERATURE_GROUPNAME, 9, 1, 'target_temperature_address', "Unexpected DPT for target temperature in GA: {}")
        process_climate_group(self.OPERATION_MODE_GROUPNAME, 20, 102, 'operation_mode_address', "Unexpected DPT for operation mode in GA: {}")
        process_climate_group(self.ON_OFF_STATE_GROUPNAME, 1, 2, 'on_off_state_address', "Unexpected DPT for on/off state in GA: {}")
        process_climate_group(self.CURRENT_TEMPERATURE_GROUPNAME, 9, 1, 'temperature_address', "Unexpected DPT for current temperature in GA: {}")

        return list(climates.values())


    def _remove_bracketed_substring(self, string):
        start = string.find('(')
        if start != -1:
            end = string.find(')', start)
            if end != -1:
                return string[:start].strip() + string[end+1:].strip()
        return string


    def _get_cover_ga(self, group_addresses):
        covers = {}
        # First, find group addresses with DPT 1.008
        for ga, values in group_addresses.items():
            base_name = values['name'].split(' (')[0]
            if _check_dpt(values, 1, 8):
                covers[base_name] = Cover(name=base_name, move_long_address=ga)
                self.processed_addresses.add(ga)

        # Next, find group addresses with DPT 1.007 or 5.001 with the same base name
        for ga, values in group_addresses.items():
            base_name = values['name'].split(' (')[0]
            if base_name in covers:
                if _check_dpt(values, 1, 7):
                    covers[base_name].stop_address = ga
                    self.processed_addresses.add(ga)
                elif _check_dpt(values, 5, 1):
                    covers[base_name].position_address = ga
                    self.processed_addresses.add(ga)

        return list(covers.values())


    def _get_binary_sensors_ga(self, group_addresses):
        binary_sensors = []

        check_dpt_subs = lambda dpt_sub: dpt_sub in (2, 3, 4, 5, 6, 11, 12, 13, 14, 18)

        for ga, values in group_addresses.items():
            if ga not in self.processed_addresses and _check_dpt(values, 1, check_dpt_subs):
                binary_sensors.append(BinarySensor(name=values["name"], state_address=ga))
        return binary_sensors



    def convert(self):
        knxproj: XKNXProj = XKNXProj(
            path=self.project_file_path,
            language="de-DE",  # optional
        )
        self.logger.debug("Start parsing KNX project file ...")
        project = knxproj.parse()
        self.logger.debug("... parsing finished")

        covers = self._get_cover_ga(project["group_addresses"])
        lights = self._get_lights_ga(project["group_addresses"])
        climate = self._get_climate_ga(project)
        binary_sensors = self._get_binary_sensors_ga(project["group_addresses"])

        return HAConfig(light=lights, binary_sensor=binary_sensors, climate=climate, cover=covers)


    def print(self, ha_config):
        # Convert ha_config to a dictionary
        ha_config_dict = ha_config.dict() if isinstance(ha_config, BaseModel) else ha_config

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
