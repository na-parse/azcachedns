#!/usr/bin/env python3
'''
azcachedns.py - Generate a dnsmasq config for lancache CDN redirection.

Reads CDN domain data from the uklans/cache-domains submodule, applies an
optional CDN filter from .config (or config), and writes a dnsmasq address=
file suitable for import into pihole or any dnsmasq-based DNS server.
'''

# =============================================================================
# Imports
# =============================================================================
import argparse
import json
import subprocess
import sys
from pathlib import Path

# =============================================================================
# Constants
# =============================================================================
CONFIG_CANDIDATES = ('.config', 'config')
DEFAULT_OUTPUT = 'lancache-redirect.conf'
CACHE_DOMAINS_DIR = 'cache-domains'
CACHE_DOMAINS_JSON = 'cache_domains.json'

# =============================================================================
# Config
# =============================================================================

def find_config(script_dir: Path) -> Path:
    '''Return the first config file found (.config or config), or exit.'''
    for name in CONFIG_CANDIDATES:
        path = script_dir / name
        if path.exists():
            return path
    candidates = ' or '.join(CONFIG_CANDIDATES)
    print(f'Error: no config file found (looked for {candidates})', file=sys.stderr)
    sys.exit(1)


def load_config(path: Path) -> dict:
    '''Load and exec the config file, returning the resulting namespace.'''
    try:
        source = path.read_text(encoding='utf-8')
    except FileNotFoundError:
        print(f'Error: config file not found: {path}', file=sys.stderr)
        sys.exit(1)

    namespace: dict = {}
    try:
        exec(source, namespace)  # noqa: S102
    except Exception as exc:
        print(f'Error: failed to parse config file: {exc}', file=sys.stderr)
        sys.exit(1)

    return namespace


def validate_config(namespace: dict) -> tuple[str, list[str], str | None]:
    '''
    Validate required and optional config values.

    Returns (cache_server_ip, include_cdns, dnsmasq_file).
    '''
    ip = namespace.get('CACHE_SERVER_IP')
    if not ip or not isinstance(ip, str) or not ip.strip():
        print(
            'Error: CACHE_SERVER_IP must be a non-empty string in config',
            file=sys.stderr,
        )
        sys.exit(1)

    include_cdns: list[str] = namespace.get('INCLUDE_CDNS', [])
    if not isinstance(include_cdns, list):
        print('Error: INCLUDE_CDNS must be a list', file=sys.stderr)
        sys.exit(1)

    for entry in include_cdns:
        if not isinstance(entry, str) or entry != entry.strip() or ' ' in entry:
            print(
                f'Error: INCLUDE_CDNS entry {entry!r} must be a string with no whitespace',
                file=sys.stderr,
            )
            sys.exit(1)

    dnsmasq_file: str | None = namespace.get('DNSMASQ_FILE')
    if dnsmasq_file is not None:
        if not isinstance(dnsmasq_file, str) or not dnsmasq_file.strip():
            print('Error: DNSMASQ_FILE must be a non-empty string', file=sys.stderr)
            sys.exit(1)

    return ip, include_cdns, dnsmasq_file

# =============================================================================
# Submodule
# =============================================================================

def update_submodule(script_dir: Path) -> None:
    '''Pull the latest commit for the cache-domains submodule.'''
    print('Updating cache-domains submodule...')
    try:
        subprocess.run(
            ['git', 'submodule', 'update', '--remote', CACHE_DOMAINS_DIR],
            cwd=script_dir,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        print(
            f'Error: submodule update failed:\n{exc.stderr}',
            file=sys.stderr,
        )
        sys.exit(1)

# =============================================================================
# Generation
# =============================================================================

def load_cdn_data(cache_domains_dir: Path) -> list[dict]:
    '''Load and return the list of CDN entries from cache_domains.json.'''
    json_path = cache_domains_dir / CACHE_DOMAINS_JSON
    try:
        data = json.loads(json_path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        print(f'Error: {json_path} not found', file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f'Error: failed to parse {json_path}: {exc}', file=sys.stderr)
        sys.exit(1)

    return data['cache_domains']


def filter_cdns(cdns: list[dict], include: list[str]) -> list[dict]:
    '''
    Filter CDN list to only those named in include.

    Returns all CDNs when include is empty.
    '''
    if not include:
        return cdns

    lookup = {cdn['name']: cdn for cdn in cdns}
    result = []
    for name in include:
        if name not in lookup:
            print(f'Error: unknown CDN {name!r} in INCLUDE_CDNS', file=sys.stderr)
            sys.exit(1)
        result.append(lookup[name])

    return result


def generate_dnsmasq(cdns: list[dict], domains_dir: Path, ip: str) -> list[str]:
    '''Build dnsmasq address= lines for all CDN domain files.'''
    lines: list[str] = []

    for cdn in cdns:
        lines.append(f"### CDN: {cdn['name']} - {cdn['description']}")

        for domain_file in cdn['domain_files']:
            file_path = domains_dir / domain_file
            try:
                content = file_path.read_text(encoding='utf-8')
            except FileNotFoundError:
                print(
                    f'Error: domain file not found: {file_path}',
                    file=sys.stderr,
                )
                sys.exit(1)

            for raw_line in content.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith('#'):
                    lines.append(line)
                else:
                    lines.append(f'address=/{line}/{ip}')

        lines.append('')

    return lines

# =============================================================================
# Main
# =============================================================================

def main() -> None:
    '''Entry point: parse args, load config, generate dnsmasq config file.'''
    parser = argparse.ArgumentParser(
        description='Generate a dnsmasq config for lancache CDN redirection.'
    )
    parser.add_argument('--ip', metavar='CACHE_SERVER_IP', help='Override CACHE_SERVER_IP from config')
    parser.add_argument(
        '--output',
        metavar='OUTPUT_FILE',
        default=None,
        help=f'Output file path (default: ./{DEFAULT_OUTPUT})',
    )
    args = parser.parse_args()

    script_dir = Path(__file__).parent.resolve()
    config_path = find_config(script_dir)

    namespace = load_config(config_path)
    ip, include_cdns, dnsmasq_file = validate_config(namespace)

    if args.ip:
        ip = args.ip

    if args.output:
        output_path = Path(args.output)
    elif dnsmasq_file:
        output_path = Path(dnsmasq_file)
    else:
        output_path = script_dir / DEFAULT_OUTPUT

    update_submodule(script_dir)

    cache_domains_dir = script_dir / CACHE_DOMAINS_DIR
    all_cdns = load_cdn_data(cache_domains_dir)
    cdns = filter_cdns(all_cdns, include_cdns)

    total = len(all_cdns)
    filtered = len(cdns)
    if include_cdns:
        print(f'Loaded {filtered} CDNs (filtered from {total})')
    else:
        print(f'Loaded {filtered} CDNs')

    dnsmasq_lines = generate_dnsmasq(cdns, cache_domains_dir, ip)

    output_path.write_text('\n'.join(dnsmasq_lines) + '\n', encoding='utf-8')
    print(f'Written: {output_path}')


if __name__ == '__main__':
    main()
