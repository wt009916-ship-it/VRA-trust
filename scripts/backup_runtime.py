"""Offline maintenance CLI; archives stay local and are never served by the API."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.backup import create_backup, restore_backup, verify_backup


def main():
    parser = argparse.ArgumentParser(description='VRA local cold backup. Archives contain private project data and account hashes; protect them. Stop the service first.')
    commands = parser.add_subparsers(dest='command', required=True)
    backup = commands.add_parser('create')
    backup.add_argument('--source', required=True)
    backup.add_argument('--archive', required=True)
    for name in ('verify', 'restore'):
        child = commands.add_parser(name)
        child.add_argument('--archive', required=True)
        child.add_argument('--sha256', required=True, help='Previously recorded trusted checksum, not one read from an unknown archive')
        if name == 'restore':
            child.add_argument('--target', required=True, help='New directory only; never overwrite an existing runtime')
    args = parser.parse_args()
    try:
        if args.command == 'create':
            result = create_backup(args.source, args.archive)
        elif args.command == 'verify':
            result = verify_backup(args.archive, args.sha256)
        else:
            result = restore_backup(args.archive, args.target, args.sha256)
    except Exception as exc:
        # No database rows, account hashes, tokens, private paths or file content in error output.
        print(json.dumps({'status': 'rejected', 'error_type': type(exc).__name__,
                          'message': str(exc) if type(exc) is ValueError else 'Backup operation failed; original retained. Check format, permissions and available space.'}))
        return 1
    print(json.dumps({'status': 'succeeded', **result}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
