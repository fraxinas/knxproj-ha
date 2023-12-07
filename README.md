# KNX Project to Home Assistant config converter

Utility tool to convert a KNX project into a Home Assistant configuration. It
depends on [xknxproject] for parsing of the actual ETS project.


## Concept

Unlike the original version of [knxproj-ha], this does not rely on any arbitrary
comments for the group addresses.
Currently, it relies on some hardcoded proprietary naming / addressing schemes to glob
the multiple address GAs needed for more advanced Lights (with brightness control).

## Usage
### knxproj-ha
`./knxproj-ha.py -i /net/team/Haustechnik/KNX/Fuchsbau-2023-12.knxproj -d`
* this will output a home assistant configuration of the lights from the project
* the optional `-d` flag is for extra debug output


### knxproj-print
`./knxproj-print.py -i filename.knxproj`
* this will parse and print all the group addresses from the given knxproj file


[xknxproject]: https://github.com/XKNX/xknxproject
[knxproj-ha]: https://github.com/mueli/knxproj-ha
[ha-knx]: https://www.home-assistant.io/integrations/knx/
