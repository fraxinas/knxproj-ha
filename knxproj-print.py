#!/usr/bin/env python3
import logging
import argparse
import pprint
from xknxproject.models import KNXProject
from xknxproject import XKNXProj

logger = logging.getLogger("convert")

def main():
    parser = argparse.ArgumentParser(prog="knx-project-converter")
    parser.add_argument("-d", "--debug", action="store_true")
    parser.add_argument("-i", "--input")
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    knxproj = XKNXProj(
        path=args.input,
        password="password",  # optional
        language="de-DE",  # optional
    )
    project = knxproj.parse()
    pp = pprint.PrettyPrinter(indent=1)
    pp.pprint(project)

if __name__ == "__main__":
    main()
