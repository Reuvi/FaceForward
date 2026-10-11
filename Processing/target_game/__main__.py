"""Read saved results without opening the camera or changing settings."""
import argparse
import json
from .storage import analyze_folder


def main():
    parser=argparse.ArgumentParser(description='Analyze saved target-game sessions')
    parser.add_argument('folder',help='Session directory containing round-*.json')
    args=parser.parse_args()
    try:print(json.dumps(analyze_folder(args.folder),indent=2,allow_nan=False))
    except (OSError,ValueError,KeyError,TypeError) as exc:parser.exit(1,str(exc)+'\n')


if __name__=='__main__':main()
