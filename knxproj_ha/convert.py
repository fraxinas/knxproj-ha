import sys
import logging
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from xknxproject import XKNXProj
from .models import *
import yaml

class OrderedDumper(yaml.SafeDumper):
    """A custom YAML dumper that respects the order of keys in OrderedDict."""

def _dict_representer(dumper, data):
    return dumper.represent_mapping(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, data.items())

OrderedDumper.add_representer(dict, _dict_representer)

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
    TARGET_TEMPERATURE_STATE_GROUPNAME = None #"Basis-Solltemperaturen"
    OPERATION_MODE_GROUPNAME = "Betriebsmodi"
    ON_OFF_STATE_GROUPNAME = None #"Meldung Heizen"
    CURRENT_TEMPERATURE_GROUPNAME = "Ist-Temperaturen"
    LIGHTS_GROUPNAME = "Beleuchtung"
    LIGHTS_STATUS_GROUPNAME = "Status"

    SENSOR_SUB_DPTS = (2, 4, 5, 6, 11, 12, 13, 14, 18)

    def __init__(self, project_file_path, language='de-DE'):
        self.project_file_path = project_file_path
        self.language = language
        self.processed_addresses = set()
        self.logger = logging.getLogger("knxproj_ha")
        self.project = None
        self.group_range_cache = {}
        self.ga_listener_keys = {}


    def _find_group_range_by_name(self, name):
        # Check cache first
        if name in self.group_range_cache:
            return self.group_range_cache[name]

        group_ranges = self.project["group_ranges"]
        all_group_addresses = []

        for main_range, main_range_data in group_ranges.items():
            if main_range_data.get('name') == name:
                # Found in main range, get addresses from all sub-ranges
                for sub_range, sub_range_data in main_range_data.get('group_ranges', {}).items():
                    all_group_addresses.extend(sub_range_data.get('group_addresses', []))

                # Cache and return the concatenated list
                self.group_range_cache[name] = all_group_addresses
                return all_group_addresses

            # Check in sub-ranges
            for sub_range, sub_range_data in main_range_data.get('group_ranges', {}).items():
                if sub_range_data.get('name') == name:
                    # Found in sub-range, return addresses
                    self.group_range_cache[name] = sub_range_data.get('group_addresses', [])
                    return sub_range_data.get('group_addresses', [])

        self.logger.warning(f"No group addresses found for group name '{name}'")
        # Cache the empty result
        self.group_range_cache[name] = []
        return []


    def find_group_range_path(self, ga):
        if isinstance(ga, dict):
            name = ga["name"]
            address = ga["address"]
        else:
            address = ga
            name = self.project["group_addresses"][address]["name"]

        group_ranges = self.project["group_ranges"]

        for main_range, main_range_data in group_ranges.items():
            main_range_name = main_range_data.get('name')

            # Check in the main range's direct group addresses
            if address in main_range_data.get('group_addresses', []):
                return main_range_name

            # Check in sub-ranges
            for sub_range, sub_range_data in main_range_data.get('group_ranges', {}).items():
                if address in sub_range_data.get('group_addresses', []):
                    sub_range_name = sub_range_data.get('name')
                    return f"{main_range_name}/{sub_range_name}/{name}"

        self.logger.warning(f"No path found for group address {address}")
        return "Unknown"  # Return a default value if not found


    def _map_dpt_to_ha_sensor(self, dpt):
        """
        Map a KNX DPT (Data Point Type) to its corresponding Home Assistant sensor type and device class.

        Args:
            dpt_main (dict): DPT with main and sub.

        Returns:
            tuple: (value_type, device_class, entity_class) or None if no match is found.
        """

        # Mapping of DPT main and sub to sensor types and device classes
        sensor_mappings = {
            # Format: (DPT main, DPT sub): ('value_type', 'device_class'),
            (5, 1): ('percent', 'humidity'),
            (5, 3): ('angle', None),
            (5, 4): ('percentU8', 'humidity'),
            (5, 5): ('decimal_factor', None),
            (6, 1): ('percentV8', None),
            (6, 10): ('counter_pulses', None),
            (7, 1): ('pulse_2byte', None),
            (7, 2): ('time_period_msec', 'duration'),
            (7, 3): ('time_period_10msec', 'duration'),
            (7, 4): ('time_period_100msec', 'duration'),
            (7, 5): ('time_period_sec', 'duration'),
            (7, 6): ('time_period_min', 'duration'),
            (7, 7): ('time_period_hrs', 'duration'),
            (7, 11): ('length_mm', 'distance'),
            (7, 12): ('current', 'current'),
            (7, 13): ('brightness', 'illuminance'),
            (7, 600): ('color_temperature', None),
            (8, 1): ('pulse_2byte_signed', None),
            (8, 2): ('delta_time_ms', 'duration'),
            (8, 3): ('delta_time_10ms', 'duration'),
            (8, 4): ('delta_time_100ms', 'duration'),
            (8, 5): ('delta_time_sec', 'duration'),
            (8, 6): ('delta_time_min', 'duration'),
            (8, 7): ('delta_time_hrs', 'duration'),
            (8, 10): ('percentV16', None),
            (8, 11): ('rotation_angle', 'angle'),
            (9, 1): ('temperature', 'temperature'),
            (9, 2): ('temperature_difference_2byte', 'temperature'),
            (9, 3): ('temperature_a', 'temperature'),
            (9, 4): ('illuminance', 'illuminance'),
            (9, 5): ('wind_speed_ms', 'speed'),
            (9, 6): ('pressure_2byte', 'pressure'),
            (9, 7): ('humidity', 'humidity'),
            (9, 8): ('ppm', None),
            (9, 9): ('air_flow', 'speed'),
            (9, 10): ('time_1', 'duration'),
            (9, 11): ('time_2', 'duration'),
            (9, 20): ('voltage', 'voltage'),
            (9, 21): ('current', 'current'),
            (9, 22): ('power_density', 'power'),
            (9, 23): ('kelvin_per_percent', 'temperature'),
            (9, 24): ('power_2byte', 'power'),
            (9, 25): ('volume_flow', 'volume'),
            (9, 26): ('rain_amount', 'precipitation'),
            (9, 27): ('temperature_f', 'temperature'),
            (9, 28): ('wind_speed_kmh', 'speed'),
            (9, 29): ('absolute_humidity', 'humidity'),
            (9, 30): ('concentration_ugm3', None),
            (12, 1): ('pulse_4_ucount', None),
            (12, 100): ('long_time_period_sec', 'duration'),
            (12, 101): ('long_time_period_min', 'duration'),
            (12, 102): ('long_time_period_hrs', 'duration'),
            (12, 1200): ('volume_liquid_litre', 'volume'),
            (12, 1201): ('volume_m3', 'volume'),
            (13, 1): ('pulse_4byte', None),
            (13, 2): ('flow_rate_m3h', None),
            (13, 10): ('active_energy', 'energy'),
            (13, 11): ('apparant_energy', 'energy'),
            (13, 12): ('reactive_energy', 'energy'),
            (13, 13): ('active_energy_kwh', 'energy'),
            (13, 14): ('apparant_energy_kvah', 'energy'),
            (13, 15): ('reactive_energy_kvarh', 'energy'),
            (13, 16): ('active_energy_mwh', 'energy'),
            (13, 100): ('long_delta_timesec', 'duration'),
            (14, 0): ('acceleration', None),
            (14, 1): ('acceleration_angular', None),
            (14, 2): ('activation_energy', None),
            (14, 3): ('activity', None),
            (14, 4): ('mol', None),
            (14, 5): ('amplitude', None),
            (14, 6): ('angle_rad', None),
            (14, 7): ('angle_deg', None),
            (14, 8): ('angular_momentum', None),
            (14, 9): ('angular_velocity', None),
            (14, 10): ('area', None),
            (14, 11): ('capacitance', None),
            (14, 12): ('charge_density_surface', None),
            (14, 13): ('charge_density_volume', None),
            (14, 14): ('compressibility', None),
            (14, 15): ('conductance', None),
            (14, 16): ('electrical_conductivity', None),
            (14, 17): ('density', None),
            (14, 18): ('electric_charge', None),
            (14, 19): ('electric_current', 'current'),
            (14, 20): ('electric_current_density', None),
            (14, 21): ('electric_dipole_moment', None),
            (14, 22): ('electric_displacement', None),
            (14, 23): ('electric_field_strength', None),
            (14, 24): ('electric_flux', None),
            (14, 25): ('electric_flux_density', None),
            (14, 26): ('electric_polarization', None),
            (14, 27): ('electric_potential', 'voltage'),
            (14, 28): ('electric_potential_difference', 'voltage'),
            (14, 29): ('electromagnetic_moment', None),
            (14, 30): ('electromotive_force', None),
            (14, 31): ('energy', 'energy'),
            (14, 32): ('force', None),
            (14, 33): ('frequency', 'frequency'),
            (14, 34): ('angular_frequency', 'frequency'),
            (14, 35): ('heatcapacity', None),
            (14, 36): ('heatflowrate', None),
            (14, 37): ('heat_quantity', None),
            (14, 38): ('impedance', None),
            (14, 39): ('length', None),
            (14, 40): ('light_quantity', None),
            (14, 41): ('luminance', None),
            (14, 42): ('luminous_flux', None),
            (14, 43): ('luminous_intensity', None),
            (14, 44): ('magnetic_field_strength', None),
            (14, 45): ('magnetic_flux', None),
            (14, 46): ('magnetic_flux_density', None),
            (14, 47): ('magnetic_moment', None),
            (14, 48): ('magnetic_polarization', None),
            (14, 49): ('magnetization', None),
            (14, 50): ('magnetomotive_force', None),
            (14, 51): ('mass', 'weight'),
            (14, 52): ('mass_flux', None),
            (14, 53): ('momentum', None),
            (14, 54): ('phaseanglerad', None),
            (14, 55): ('phaseangledeg', None),
            (14, 56): ('power', 'power'),
            (14, 57): ('powerfactor', 'power_factor'),
            (14, 58): ('pressure', 'pressure'),
            (14, 59): ('reactance', None),
            (14, 60): ('resistance', None),
            (14, 61): ('resistivity', None),
            (14, 62): ('self_inductance', None),
            (14, 63): ('solid_angle', None),
            (14, 63): ('solid_angle', None),
            (14, 64): ('sound_intensity', None),
            (14, 65): ('speed', 'speed'),
            (14, 66): ('stress', 'pressure'),
            (14, 67): ('surface_tension', None),
            (14, 68): ('common_temperature', 'temperature'),
            (14, 69): ('absolute_temperature', 'temperature'),
            (14, 70): ('temperature_difference', 'temperature'),
            (14, 71): ('thermal_capacity', None),
            (14, 72): ('thermal_conductivity', None),
            (14, 73): ('thermoelectric_power', None),
            (14, 74): ('time_seconds', 'duration'),
            (14, 75): ('torque', None),
            (14, 76): ('volume', 'volume'),
            (14, 77): ('volume_flux', None),
            (14, 78): ('weight', None),
            (14, 79): ('work', None),
            (14, 80): ('apparent_power', 'apparent_power'),
            (16, 0): ('string', None),
            (16, 1): ('latin_1', None),
            (17, 1): ('scene_number', None, Number),
        }

        if not (dpt["main"], dpt["sub"]) in sensor_mappings:
            return None

        sensor_mapping = sensor_mappings[dpt["main"], dpt["sub"]]

        if len(sensor_mapping) == 2:
            sensor_mapping = sensor_mapping + (Sensor, )

        return sensor_mapping


    def _find_listener_ga(self):
        for co in self.project['communication_objects'].values():
            ga_links = co.get("group_address_links")
            if ga_links and len(ga_links) > 1:
                self.ga_listener_keys[ga_links[0]] = ga_links[1:]
                self.logger.debug(f"Linked listener GAs found: {ga_links[0]}: {self.ga_listener_keys[ga_links[0]]}")


    def _get_ga_list(self, ga):
            ga_list = [ga]
            if ga in self.ga_listener_keys:
                ga_list = [ga] + self.ga_listener_keys[ga]
            return ga_list


    def _get_lights_ga(self, group_addresses):
        temp_lights = {}
        final_lights = {}

        # First pass: Collect all potential Light objects
        for ga, values in group_addresses.items():
            base_name = values['name']

            if ga in self._find_group_range_by_name(self.LIGHTS_GROUPNAME):
                ga_list = self._get_ga_list(ga)

                if _check_dpt(values, 1, 1):
                    temp_lights.setdefault(base_name, {}).setdefault('address', []).extend(ga_list)
                    self.processed_addresses.add(ga)
                elif _check_dpt(values, 1, 11):
                    temp_lights.setdefault(base_name, {}).setdefault('state_address', []).extend(ga_list)
                    self.processed_addresses.add(ga)
                elif _check_dpt(values, 5, 1):
                    if self.LIGHTS_STATUS_GROUPNAME in self.find_group_range_path(ga):
                        temp_lights.setdefault(base_name, {}).setdefault('brightness_state_address', []).extend(ga_list)
                    else:
                        temp_lights.setdefault(base_name, {}).setdefault('brightness_address', []).extend(ga_list)
                    self.processed_addresses.add(ga)
                elif _check_dpt(values, 7, 600):
                    if self.LIGHTS_STATUS_GROUPNAME in self.find_group_range_path(ga):
                        temp_lights.setdefault(base_name, {}).setdefault('color_temperature_state_address', []).extend(ga_list)
                    else:
                        temp_lights.setdefault(base_name, {}).setdefault('color_temperature_address', []).extend(ga_list)
                    self.processed_addresses.add(ga)
                elif _check_dpt(values, 251, 600):
                    if self.LIGHTS_STATUS_GROUPNAME in self.find_group_range_path(ga):
                        temp_lights.setdefault(base_name, {}).setdefault('rgbw_address', []).extend(ga_list)
                    else:
                        temp_lights.setdefault(base_name, {}).setdefault('rgbw_state_address', []).extend(ga_list)
                    self.processed_addresses.add(ga)

        # Second pass: Create Light objects only if they have a main address
        for name, attrs in temp_lights.items():
            if 'address' in attrs:
                final_lights[name] = Light(name=name, **attrs)
            else:
                self.logger.warning(f"Lights entity '{name}' with attributes {attrs} is missing a main address, not adding to config!")

        return list(final_lights.values())


    def _get_climate_ga(self, all_group_addresses):
        temp_climates = {}
        final_climates = {}

        def process_climate_group(name, dpt_main, dpt_sub, field_name, warning_msg):
            sub_group_addresses = self._find_group_range_by_name(name)

            for address in sub_group_addresses:
                values = all_group_addresses.get(address)
                if values and _check_dpt(values, dpt_main, dpt_sub):
                    base_name = values['name']
                    temp_climates.setdefault(base_name, {}).setdefault(field_name, []).append(address)
                    self.processed_addresses.add(address)
                else:
                    self.logger.warning(warning_msg.format(values))

        # Process different climate-related group addresses
        process_climate_group(self.TARGET_TEMPERATURE_GROUPNAME, 9, 1, 'target_temperature_address', "Unexpected DPT for target temperature in GA: {}")
        process_climate_group(self.OPERATION_MODE_GROUPNAME, 20, 102, 'operation_mode_address', "Unexpected DPT for operation mode in GA: {}")
        if self.ON_OFF_STATE_GROUPNAME:
            process_climate_group(self.ON_OFF_STATE_GROUPNAME, 1, 2, 'on_off_state_address', "Unexpected DPT for on/off state in GA: {}")
        process_climate_group(self.CURRENT_TEMPERATURE_GROUPNAME, 9, 1, 'temperature_address', "Unexpected DPT for current temperature in GA: {}")
        if self.TARGET_TEMPERATURE_STATE_GROUPNAME:
            process_climate_group(self.TARGET_TEMPERATURE_STATE_GROUPNAME, 9, 1, 'target_temperature_state_address', "Unexpected DPT for target temperature state in GA: {}")

        print("temp_climates", temp_climates)
        # Second pass: Make sure Climate entities have required fields (temperature_address,  target_temperature_state_address)
        for name, attrs in temp_climates.items():

            if not 'temperature_address' in attrs:
                self.logger.warning(f"Climate entity '{name}' with attributes {attrs} is missing a temperature_address, not adding to config!")
                continue

            if not "target_temperature_state_address" in attrs:
                if "target_temperature_address" in attrs:
                    self.logger.warning(f"Climate entity '{name}' with attributes {attrs} is missing a target_temperature_state_address, assuming same as target_temperature_address!")
                    attrs['target_temperature_state_address'] = attrs['target_temperature_address']
                else:
                    self.logger.warning(f"Climate entity '{name}' with attributes {attrs} is missing a target_temperature_state_address (and has no target_temperature_address as fallback), not adding to config!")
                    continue  # Skip this climate entity

            final_climates[name] = Climate(name=name, **attrs)

        return list(final_climates.values())


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
            ga_list = self._get_ga_list(ga)
            base_name = values['name'].split(' (')[0]
            if _check_dpt(values, 1, 8):
                covers[base_name] = Cover(name=base_name, move_long_address=ga_list)
                self.processed_addresses.add(ga)

        # Next, find group addresses with DPT 1.007 or 5.001 with the same base name
        for ga, values in group_addresses.items():
            base_name = values['name'].split(' (')[0]
            if base_name in covers:
                ga_list = self._get_ga_list(ga)
                if _check_dpt(values, 1, 7):
                    covers[base_name].stop_address = ga_list
                    self.processed_addresses.add(ga)
                elif _check_dpt(values, 5, 1):
                    covers[base_name].position_address = ga_list
                    self.processed_addresses.add(ga)

        return list(covers.values())


    def _get_switches_ga(self, group_addresses):
        switches = []

        check_dpt_subs = lambda dpt_sub: dpt_sub not in self.SENSOR_SUB_DPTS

        for ga, values in group_addresses.items():
            if ga not in self.processed_addresses and _check_dpt(values, 1, check_dpt_subs):
                switches.append(Switch(name=values["name"], state_address=[ga]))
                self.processed_addresses.add(ga)
        return switches


    def _get_binary_sensors_ga(self, group_addresses):
        binary_sensors = []

        check_dpt_subs = lambda dpt_sub: dpt_sub in self.SENSOR_SUB_DPTS

        for ga, values in group_addresses.items():
            if ga not in self.processed_addresses and _check_dpt(values, 1, check_dpt_subs):
                binary_sensors.append(BinarySensor(name=values["name"], state_address=[ga]))
                self.processed_addresses.add(ga)
        return binary_sensors


    def _get_sensors_ga(self, group_addresses):
        sensors = []

        for ga, values in group_addresses.items():
            if ga not in self.processed_addresses and values['dpt']:
                mapping = self._map_dpt_to_ha_sensor(values['dpt'])
                if mapping:
                    (value_type, device_class, entity_class) = mapping
                    if entity_class == Sensor:
                        sensors.append(Sensor(name=values["name"], state_address=[ga], type=value_type, device_class=device_class))
                    elif entity_class == Number and value_type == "scene_number":
                        self.numbers.append(Number(name=values["name"], state_address=[ga], type=value_type, min=0., max=64., step=1))

                    self.processed_addresses.add(ga)
        return sensors


    def convert(self):
        knxproj: XKNXProj = XKNXProj(
            path=self.project_file_path,
            language="de-DE",  # optional
        )
        self.logger.debug("Start parsing KNX project file ...")
        self.project = knxproj.parse()
        self.logger.debug("... parsing finished")

        self.logger.debug(self.project["group_addresses"])

        self._find_listener_ga()

        self.numbers = []

        covers = self._get_cover_ga(self.project["group_addresses"])
        lights = self._get_lights_ga(self.project["group_addresses"])
        climate = self._get_climate_ga(self.project["group_addresses"])
        switches = self._get_switches_ga(self.project["group_addresses"])
        binary_sensors = self._get_binary_sensors_ga(self.project["group_addresses"])
        sensors = self._get_sensors_ga(self.project["group_addresses"])

        return HAConfig(light=lights, switch=switches, binary_sensor=binary_sensors, sensor=sensors, climate=climate, cover=covers, number=self.numbers)


    def _serialize_groups(self, entity, comments=False):
        serialized_entity = CommentedMap()
        serialized_entity['name'] = entity.pop('name')

        for key, value in entity.items():
            if value:
                if isinstance(value, list):
                    serialized_list = CommentedSeq()

                    for addr in value:
                        serialized_list.append(addr)
                        if comments:
                            serialized_list.yaml_add_eol_comment(f" {self.find_group_range_path(addr)}", len(serialized_list) - 1, column=20)

                    serialized_entity[key] = serialized_list
                else:
                    serialized_entity[key] = value

        return serialized_entity



    def print(self, ha_config, comments):
        ha_config_dict = ha_config.dict() if isinstance(ha_config, BaseModel) else ha_config
        filtered_config = CommentedMap({'knx': {}})

        yaml_obj = YAML()
        yaml_obj.indent(mapping=2, sequence=4, offset=2)

        for entity_type, entities in ha_config_dict.items():
            filtered_config['knx'][entity_type] = []
            for entity in entities:
                serialized_entity = self._serialize_groups(entity, comments)
                filtered_config['knx'][entity_type].append(serialized_entity)

        yaml_obj.dump(filtered_config, sys.stdout)


