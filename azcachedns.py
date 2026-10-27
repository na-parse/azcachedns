#!/usr/bin/env python3
'''
azcachedns.py - Generate a dnsmasq config for lancache CDN redirection.

Reads CDN domain data from a local clone of uklans/cache-domains, applies an
optional CDN filter from .config (or config), and writes a dnsmasq address=
file suitable for import into pihole or any dnsmasq-based DNS server.

Commands:
    generate (default)  Write the dnsmasq config file
    list                Show available CDN names
    setup               Create or update .config interactively
'''

# =============================================================================
# Imports
# =============================================================================
import argparse
import ipaddress
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
CACHE_DOMAINS_URL = 'https://github.com/uklans/cache-domains'

# =============================================================================
# Config
# =============================================================================

def find_config(script_dir: Path) -> Path | None:
    '''Return the first config file found (.config or config), or None.'''
    for name in CONFIG_CANDIDATES:
        path = script_dir / name
        if path.exists():
            return path
    return None


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


def write_config(
    path: Path, ip: str, include_cdns: list[str], dnsmasq_file: str | None
) -> None:
    '''Write a config file in the same layout as config.sample.'''
    if dnsmasq_file:
        dnsmasq_line = f'DNSMASQ_FILE = {dnsmasq_file!r}'
    else:
        dnsmasq_line = "# DNSMASQ_FILE = '/etc/dnsmasq.d/lancache-redirect.conf'"

    content = f'''\
# IP Address for the lancache server for dnsmasq address redirection
# - cnames are not supported due to presence of '*' wildcard domains
CACHE_SERVER_IP = {ip!r}

# All CDNs will be included in configuration generation if
# INCLUDE_CDNS is not defined or an empty list.  Names must
# match CDN names shown by: azcachedns.py list
INCLUDE_CDNS = {include_cdns!r}

# Output path for the generated dnsmasq config file.
# Defaults to {DEFAULT_OUTPUT} in the script directory.
{dnsmasq_line}
'''
    path.write_text(content, encoding='utf-8')

# =============================================================================
# Data Source
# =============================================================================

def update_cache_domains(script_dir: Path) -> None:
    '''
    Clone uklans/cache-domains on first run, or pull the latest data.

    A failed pull falls back to the existing local data with a warning.
    '''
    target = script_dir / CACHE_DOMAINS_DIR

    if not target.exists():
        print(f'Cloning {CACHE_DOMAINS_URL}...')
        command = ['git', 'clone', '--depth', '1', CACHE_DOMAINS_URL, CACHE_DOMAINS_DIR]
        cwd = script_dir
    elif (target / '.git').is_dir():
        print('Updating cache-domains...')
        command = ['git', 'pull', '--ff-only', '--quiet']
        cwd = target
    else:
        print(
            f'Error: {target} exists but is not a git clone; '
            'remove it and re-run to clone fresh data',
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        if command[1] == 'clone':
            print(f'Error: clone failed:\n{exc.stderr}', file=sys.stderr)
            sys.exit(1)
        print(
            f'Warning: update failed, using existing data:\n{exc.stderr}',
            file=sys.stderr,
        )

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


def print_cdn_list(cdns: list[dict]) -> None:
    '''Print available CDN names and descriptions as an aligned table.'''
    width = max(len(cdn['name']) for cdn in cdns)
    for cdn in sorted(cdns, key=lambda cdn: cdn['name']):
        print(f"{cdn['name']:<{width}}  {cdn['description']}")

# =============================================================================
# Setup
# =============================================================================

def prompt_ip(current: str | None) -> str:
    '''Prompt for the cache server IP, re-asking until a valid address is given.'''
    suffix = f' [{current}]' if current else ''
    while True:
        answer = input(f'Cache server IP{suffix}: ').strip() or current
        if not answer:
            print('  A cache server IP is required.')
            continue
        try:
            ipaddress.ip_address(answer)
        except ValueError:
            print(f'  {answer!r} is not a valid IP address.')
            continue
        return answer


def prompt_output(current: str | None) -> str | None:
    '''
    Prompt for the output path.

    Blank keeps the current value (built-in default when there is none);
    "default" clears it back to the built-in default.
    '''
    if current:
        hint = f"[{current}] ('default' for {DEFAULT_OUTPUT})"
    else:
        hint = f'[{DEFAULT_OUTPUT}]'

    answer = input(f'Output path {hint}: ').strip()
    if answer == 'default':
        return None
    return answer or current


def prompt_cdns(cdns: list[dict], current: list[str]) -> list[str]:
    '''
    Prompt for CDN names separated by whitespace and/or commas.

    Blank keeps the current selection (all CDNs when there is none);
    "all" clears the selection.
    '''
    known = {cdn['name'] for cdn in cdns}
    if current:
        hint = f"[{' '.join(current)}] ('all' for all)"
    else:
        hint = '[all]'

    while True:
        answer = input(f'CDNs to include {hint}: ').replace(',', ' ').split()
        if not answer:
            return current
        if answer == ['all']:
            return []

        names = list(dict.fromkeys(name.lower() for name in answer))
        unknown = [name for name in names if name not in known]
        if unknown:
            print(f"  Unknown CDN(s): {' '.join(unknown)}")
            continue
        return names


def run_setup(script_dir: Path) -> None:
    '''Interactively create or update the config file.'''
    config_path = find_config(script_dir)
    if config_path:
        print(f'Updating {config_path} (press Enter to keep current values)')
        namespace = load_config(config_path)
    else:
        config_path = script_dir / CONFIG_CANDIDATES[0]
        print(f'Creating {config_path}')
        namespace = {}

    current_ip = namespace.get('CACHE_SERVER_IP')
    current_output = namespace.get('DNSMASQ_FILE')
    current_cdns = namespace.get('INCLUDE_CDNS') or []

    try:
        ip = prompt_ip(current_ip if isinstance(current_ip, str) else None)
        dnsmasq_file = prompt_output(
            current_output if isinstance(current_output, str) else None
        )

        update_cache_domains(script_dir)
        cdns = load_cdn_data(script_dir / CACHE_DOMAINS_DIR)
        print()
        print_cdn_list(cdns)
        print()
        include_cdns = prompt_cdns(
            cdns, current_cdns if isinstance(current_cdns, list) else []
        )
    except (KeyboardInterrupt, EOFError):
        print('\nSetup cancelled, config not changed.')
        sys.exit(1)

    write_config(config_path, ip, include_cdns, dnsmasq_file)
    print(f'Written: {config_path}')
    print('Run ./azcachedns.py to generate the dnsmasq config.')

# =============================================================================
# Main
# =============================================================================

def run_generate(script_dir: Path, ip_override: str | None, output: str | None) -> None:
    '''Load config and write the dnsmasq config file.'''
    config_path = find_config(script_dir)
    if not config_path:
        candidates = ' or '.join(CONFIG_CANDIDATES)
        print(
            f'Error: no config file found (looked for {candidates}); '
            'run: azcachedns.py setup',
            file=sys.stderr,
        )
        sys.exit(1)

    namespace = load_config(config_path)
    ip, include_cdns, dnsmasq_file = validate_config(namespace)

    if ip_override:
        ip = ip_override

    if output:
        output_path = Path(output)
    elif dnsmasq_file:
        output_path = Path(dnsmasq_file)
    else:
        output_path = script_dir / DEFAULT_OUTPUT

    update_cache_domains(script_dir)

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


def add_generate_args(parser: argparse.ArgumentParser, default) -> None:
    '''Add the generate options to parser with the given default.'''
    parser.add_argument(
        '--ip',
        metavar='CACHE_SERVER_IP',
        default=default,
        help='Override CACHE_SERVER_IP from config',
    )
    parser.add_argument(
        '--output',
        metavar='OUTPUT_FILE',
        default=default,
        help=f'Output file path (default: ./{DEFAULT_OUTPUT})',
    )


def main() -> None:
    '''Entry point: parse args and dispatch to the selected command.'''
    parser = argparse.ArgumentParser(
        description='Generate a dnsmasq config for lancache CDN redirection.',
        epilog='With no command, runs generate.',
    )
    add_generate_args(parser, None)

    subparsers = parser.add_subparsers(dest='command', metavar='command')
    generate_parser = subparsers.add_parser(
        'generate', help='Write the dnsmasq config file (default)'
    )
    # SUPPRESS keeps top-level --ip/--output values from being reset to None
    add_generate_args(generate_parser, argparse.SUPPRESS)
    subparsers.add_parser('list', help='Show available CDN names for INCLUDE_CDNS')
    subparsers.add_parser('setup', help='Create or update .config interactively')

    args = parser.parse_args()
    script_dir = Path(__file__).parent.resolve()

    if args.command in ('list', 'setup') and (args.ip or args.output):
        parser.error(f'--ip and --output do not apply to {args.command}')

    if args.command == 'list':
        update_cache_domains(script_dir)
        print_cdn_list(load_cdn_data(script_dir / CACHE_DOMAINS_DIR))
    elif args.command == 'setup':
        run_setup(script_dir)
    else:
        run_generate(script_dir, args.ip, args.output)


if __name__ == '__main__':
    main()
