"""Import an official, unchanged ÖKOBAUDAT point-decimal CSV into a local library."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.epd import EpdLibrary
from backend.store import Store


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', type=Path, required=True)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--encoding', choices=['cp1252', 'utf-8-sig'], default='cp1252')
    args = parser.parse_args()
    print(json.dumps(EpdLibrary(Store(args.data_dir)).import_csv(args.csv, encoding=args.encoding), ensure_ascii=True, indent=2))
