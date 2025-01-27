#!/usr/bin/env python3
import logging
import argparse
from knxproj_ha.convert import KNXHAConverter

logger = logging.getLogger("convert")


def main():
    parser = argparse.ArgumentParser(prog="knx-project-converter")
    parser.add_argument("-d", "--debug", action="store_true")
    parser.add_argument("-c", "--comments", action="store_true")
    parser.add_argument("-i", "--input")
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    converter = KNXHAConverter(project_file_path=args.input)
    ha_config = converter.convert()
    converter.print(ha_config, comments=args.comments)

    if args.debug:
        unprocessed_gas = []
        for ga, values in converter.project["group_addresses"].items():
            if ga not in converter.processed_addresses:
                dpt = "DTP Unspecified"
                if values["dpt"]:
                    dpt = (f'DPT: {values["dpt"]["main"]}.{values["dpt"]["sub"]}')
                unprocessed_gas.append(f'\t{ga}: {converter.find_group_range_path(ga)} {dpt}')

        logger.info("Unprocessed Group Addresses:\n" + '\n'.join(unprocessed_gas))



if __name__ == "__main__":
    main()
