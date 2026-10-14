"""Usage: python -m app.ops check | backup --destination PATH"""
import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit
from dotenv import load_dotenv

from app.core.maintenance import backup_database, integrity_check
from app.core.release import local_release_check, restore_drill


def run(argv=None) -> int:
    parser = argparse.ArgumentParser(description='CareerPilot local maintenance tools')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('check', help='Check local database and provider configuration (no API calls)')
    backup = sub.add_parser('backup', help='Create a consistent SQLite backup')
    backup.add_argument('--destination', required=True, type=Path, help='Existing private folder')
    restore = sub.add_parser('restore-drill', help='Restore a private SQLite backup into throwaway temporary storage and verify it')
    restore.add_argument('--backup', required=True, type=Path)
    sub.add_parser('release-check', help='Offline v1.0 localhost release checklist (never checks live providers)')
    args = parser.parse_args(argv)
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    if args.command == 'check':
        db = integrity_check()
        configured = bool(os.getenv('AI_API_KEY', '').strip())
        address = os.getenv('AI_BASE_URL', 'https://api.groq.com/openai/v1')
        # Do not print the provider URL: it can contain a userinfo or query token.
        ssl_provider = urlsplit(address).scheme == 'https' if address else False
        result = {'database':db, 'ai_key_present':configured,
                  'ai_endpoint_uses_https':ssl_provider,
                  'network_scope':'loopback only', 'multi_user_auth_enabled':False}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if db['status'] in ('invalid_path', 'integrity_failed') else 0
    if args.command == 'release-check':
        result = local_release_check()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['local_ready'] else 1
    if args.command == 'restore-drill':
        try:
            result = restore_drill(args.backup)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        except (ValueError, OSError) as exc:
            print(f'Restore drill failed: {exc}', file=sys.stderr)
            return 2
    try:
        target = backup_database(args.destination)
        print(f'Backup created: {target}')
        print('Store backup privately: it contains saved jobs, notes and search preferences.')
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(f'Backup failed: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(run())
