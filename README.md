# azcachedns

Generate a dnsmasq config file that redirects game and patch CDN traffic to a
[lancache](https://lancache.net/) server. Drop the output directly into pihole
or any dnsmasq-based DNS server.

CDN domain data is sourced from
[uklans/cache-domains](https://github.com/uklans/cache-domains). The script
clones it into `cache-domains/` on first run (git-ignored) and pulls the latest
upstream data on every run after that.

---

## Requirements

- Python 3.10+
- Git
- A running [lancache monolithic](https://lancache.net/) server on your network

---

## Quickstart

**1. Clone**

```bash
git clone https://github.com/na-parse/azcachedns.git
cd azcachedns
```

**2. Create your config**

```bash
python azcachedns.py setup
```

Setup asks for your lancache server IP, an optional output path, and which CDNs
to include, then writes `.config`. Re-run it any time to change settings; your
current values are offered as defaults. You can also copy `config.sample` to
`.config` and edit it by hand.

**3. Run**

```bash
python azcachedns.py
```

This updates the CDN domain list from upstream, then writes `lancache-redirect.conf`
in the project directory.

---

## Using the Output

The generated file contains dnsmasq `address=` directives, one per domain:

```
### CDN: steam - CDN for steam platform
address=/lancache.steamcontent.com/192.168.1.100

### CDN: riot - CDN for Riot Games
address=/l3cdn.riotgames.com/192.168.1.100
...
```

**Pihole 6+**

Enable custom dnsmasq config loading at `Settings > All Settings > Miscellaneous`,
then copy the file to `/etc/dnsmasq.d/`:

```bash
cp lancache-redirect.conf /etc/dnsmasq.d/
```

Or set `DNSMASQ_FILE` in your config to write there directly (see below).

**Any dnsmasq server**

Copy the file to your dnsmasq config directory and reload the service.

> **Note:** Some CDN entries use wildcard domains (e.g. `*.example.com`).
> These require `address=` directives — CNAMEs are not supported for wildcards.

---

## Configuration Reference

Config file: `.config` or `config` (script checks for `.config` first).
Create it with `python azcachedns.py setup`, or copy `config.sample`.

| Variable | Required | Description |
|---|---|---|
| `CACHE_SERVER_IP` | Yes | IP address of your lancache server |
| `INCLUDE_CDNS` | No | List of CDN names to include. Empty or absent = all CDNs |
| `DNSMASQ_FILE` | No | Full output path for the generated file |

**`INCLUDE_CDNS` example** — include only Steam and Wargaming:

```python
INCLUDE_CDNS = ['steam', 'wargaming']
```

CDN names must match entries in `cache-domains/cache_domains.json`.
Run `python azcachedns.py list` to see the available names.
Leave the list empty (or omit the variable) to include all available CDNs.

**`DNSMASQ_FILE` example** — write directly to pihole's config directory:

```python
DNSMASQ_FILE = '/etc/dnsmasq.d/lancache-redirect.conf'
```

---

## Commands

```
python azcachedns.py [generate] [--ip CACHE_SERVER_IP] [--output OUTPUT_FILE]
python azcachedns.py list
python azcachedns.py setup
```

| Command | Description |
|---|---|
| `generate` | Write the dnsmasq config file. This is the default when no command is given |
| `list` | Print available CDN names and descriptions (no config needed) |
| `setup` | Create or update `.config` interactively |

`generate` options override config file values for one-off runs:

| Option | Description |
|---|---|
| `--ip` | Override `CACHE_SERVER_IP` |
| `--output` | Override output file path |

In `setup`, CDN names can be separated by spaces, commas, or both. Press Enter
at any prompt to keep the value shown in brackets. Type `all` at the CDN prompt
to include every CDN, or `default` at the output prompt to go back to
`lancache-redirect.conf`.

**Output path precedence:** `--output` > `DNSMASQ_FILE` (config) > default (`lancache-redirect.conf`)

---

## Keeping Up to Date

Re-run the script periodically. It fetches the latest CDN domain list from
upstream each time and regenerates the output file.

```bash
python azcachedns.py
```

If `git pull` fails (for example, when offline), the script warns you and uses
the data it already has.

### Upgrading from the submodule layout

Older versions included `cache-domains` as a git submodule pinned to a fixed
commit. After pulling this version, delete the old checkout so the script can
clone a fresh copy that it keeps up to date:

```bash
git submodule deinit -f cache-domains
rm -rf cache-domains .git/modules/cache-domains
python azcachedns.py list
```
