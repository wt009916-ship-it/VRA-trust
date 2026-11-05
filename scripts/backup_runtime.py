"""Offline maintenance CLI; archives stay local and are never served by the API."""
import argparse
import getpass
import json
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.backup import create_backup, restore_backup, verify_backup
from backend.encrypted_backup import create_encrypted, restore_encrypted, verify_encrypted


def passphrase(args):
    if args.password_stdin:
        value=sys.stdin.buffer.readline(1026).rstrip(b'\r\n')
    else:
        # Never silently fall back to echoing passwords when no real terminal exists.
        with warnings.catch_warnings():
            warnings.simplefilter('error',getpass.GetPassWarning)
            text=getpass.getpass('Backup passphrase (not stored): ')
            if args.command=='create' and text!=getpass.getpass('Repeat backup passphrase: '):
                raise ValueError('Passphrases do not match')
            value=text.encode('utf-8')
    return value


def main():
    parser = argparse.ArgumentParser(description='VRA encrypted local cold backup. Stop the service first; keep the passphrase separately. Lost passphrases cannot be recovered.')
    commands = parser.add_subparsers(dest='command', required=True)
    backup = commands.add_parser('create')
    backup.add_argument('--source', required=True)
    backup.add_argument('--archive', required=True)
    children=[backup]
    for name in ('verify', 'restore'):
        child = commands.add_parser(name)
        children.append(child)
        child.add_argument('--archive', required=True)
        child.add_argument('--sha256', required=True, help='Previously recorded trusted checksum, not one read from an unknown archive')
        if name == 'restore':
            child.add_argument('--target', required=True, help='New directory only; never overwrite an existing runtime')
    for child in children:
        mode=child.add_mutually_exclusive_group()
        mode.add_argument('--password-stdin',action='store_true',help='Automation only: read passphrase from a private stdin pipe, never from argv or an environment variable')
        mode.add_argument('--legacy-plaintext',action='store_true',help='Explicit unencrypted v1 compatibility; contains private data')
    args = parser.parse_args()
    try:
        password=None if args.legacy_plaintext else passphrase(args)
        if not args.legacy_plaintext:
            if args.command=='create':result=create_encrypted(args.source,args.archive,password)
            elif args.command=='verify':result=verify_encrypted(args.archive,password,args.sha256)
            else:result=restore_encrypted(args.archive,args.target,password,args.sha256)
        elif args.command == 'create':
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
