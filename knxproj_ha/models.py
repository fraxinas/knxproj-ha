from pydantic import BaseModel


class Entity(BaseModel):
    _type_id: str
    name: str

class Light(Entity):
    """Light configuration"""
    _type_id: str = "light"
    address: str = ""
    state_address: str = ""
    brightness_address: str = ""
    brightness_state_address: str = ""
    color_temperature_address: str = ""
    color_temperature_state_address: str = ""


class BinarySensor(Entity):
    """BinarySensor configuration"""
    _type_id: str = "binary_sensor"

    state_address: str

    device_class: str | None = None


class Sensor(Entity):
    """Sensor configuration"""
    _type_id: str = "sensor"

    state_address: str
    type: str

    device_class: str | None = None


class Climate(Entity):
    """Climate configuration"""
    _type_id: str = "climate"
    temperature_address: str
    target_temperature_address: str
    operation_mode_address: str
    on_off_state_address: str


class Cover(Entity):
    """Cover configuration, this is for window blinds/shutters/jalousies"""
    _type_id: str = "cover"
    move_long_address: str = ""
    stop_address: str = ""
    position_address: str = ""
    on_off_state_address: str = ""
    position_address: str = ""
    position_state_address: str = ""


class HAConfig(BaseModel):
    """Extracted Home Assistant configuration"""

    light: list[Light] = list()
    binary_sensor: list[BinarySensor] = list()
    sensor: list[Sensor] = list()
    climate: list[Climate] = list()
    cover: list[Cover] = list()
