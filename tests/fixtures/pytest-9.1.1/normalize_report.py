"""Remove variable runner metadata from this synthetic pytest report."""

import argparse
from pathlib import Path
import xml.etree.ElementTree as ET


def normalize_report(source: Path, destination: Path) -> None:
    """Keep exporter outcomes and diagnostics while removing machine/timing fields."""
    tree = ET.parse(source)
    for element in tree.iter():
        for attribute in ("hostname", "timestamp", "time"):
            element.attrib.pop(attribute, None)
    ET.indent(tree, space="  ")
    tree.write(destination, encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    normalize_report(args.source, args.destination)
