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


class BinarySensor(Entity):
    """Sensor configuration for Home Assistant KNX integration."""
    _type_id: str = "binary_sensor"

    state_address: str

    device_class: str | None = None


class Sensor(Entity):
    """Sensor configuration for Home Assistant KNX integration."""
    _type_id: str = "sensor"

    state_address: str
    type: str

    device_class: str | None = None


class HAConfig(BaseModel):
    """Extracted Home Assistant configuration"""

    light: list[Light] = list()
    binary_sensors: list[BinarySensor] = list()

