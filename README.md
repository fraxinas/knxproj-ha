# KNX Project to Home Assistant config converter

Utility tool to convert a KNX project into a Home Assistant configuration. It
depends on [xknxproject] for parsing of the actual ETS project.


## Concept

Unlike the original version of [mueli/knxproj-ha], this does not rely on any arbitrary
comments for the group addresses.


## Usage
### knxproj-print
`./knxproj-print.py -i filename.knxproj`
This will parse and print all the group addresses from the given knxproj file


[xknxproject]: https://github.com/XKNX/xknxproject
[ha-knx]: https://www.home-assistant.io/integrations/knx/
