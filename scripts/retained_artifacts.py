#!/usr/bin/env python3
"""Verify retained originals or extract one to a file that does not yet exist."""
import argparse
from pathlib import Path
from maintenance.retention import manifest, original_bytes, verify_entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--verify',action='store_true',help='check every original size and SHA256')
    action.add_argument('--extract',metavar='ORIGINAL_PATH',help='original path from the retention manifest')
    parser.add_argument('--out',type=Path,help='new output file; existing files are never overwritten')
    args = parser.parse_args()
    if args.verify:
        if args.out: parser.error('--out is only valid with --extract')
        entries = manifest()['entries']
        for rel in entries: verify_entry(rel)
        print(f'PASS retained originals: {len(entries)} exact size/SHA256 checks')
    else:
        if not args.out: parser.error('--extract requires --out')
        if args.extract not in manifest()['entries']: parser.error('path is not in the retention manifest')
        data = original_bytes(args.extract)
        args.out.parent.mkdir(parents=True,exist_ok=True)
        with args.out.open('xb') as output: output.write(data)
        print(f'Extracted {args.extract}: {len(data)} bytes to {args.out}')


if __name__ == '__main__': main()
