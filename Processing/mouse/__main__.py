import argparse
import json
from pathlib import Path

from .desktop import run


def main():
    parser = argparse.ArgumentParser(description="Open the native Python/Tk mouse processing lab")
    parser.add_argument("--config", type=Path, help="JSON settings exported by the lab")
    args = parser.parse_args()
    try:
        payload = json.loads(args.config.read_text()) if args.config else {}
        run(payload)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Could not start lab: {exc}\n")


if __name__ == "__main__":
    main()
