# azcachedns

Generate a dnsmasq config file that redirects game and patch CDN traffic to a
[lancache](https://lancache.net/) server. Drop the output directly into pihole
or any dnsmasq-based DNS server.

CDN domain data is sourced from
[uklans/cache-domains](https://github.com/uklans/cache-domains), included as a
git submodule. Running the script pulls the latest upstream data automatically.

---

## Requirements

- Python 3.10+
- Git
- A running [lancache monolithic](https://lancache.net/) server on your network

---

## Quickstart

**1. Clone with submodules**

```bash
git clone --recurse-submodules https://github.com/na-parse/azcachedns.git
cd azcachedns
```

If you already cloned without `--recurse-submodules`:

```bash
git submodule update --init
```

**2. Create your config**

```bash
cp config.sample .config
```

Edit `.config` and set your lancache server IP:

```python
CACHE_SERVER_IP = "192.168.1.100"
```

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
Copy `config.sample` to get started.

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
Leave the list empty (or omit the variable) to include all available CDNs.

**`DNSMASQ_FILE` example** — write directly to pihole's config directory:

```python
DNSMASQ_FILE = '/etc/dnsmasq.d/lancache-redirect.conf'
```

---

## CLI Options

CLI flags override config file values for one-off runs.

```
python azcachedns.py [--ip CACHE_SERVER_IP] [--output OUTPUT_FILE]
```

| Flag | Description |
|---|---|
| `--ip` | Override `CACHE_SERVER_IP` |
| `--output` | Override output file path |

**Output path precedence:** `--output` > `DNSMASQ_FILE` (config) > default (`lancache-redirect.conf`)

---

## Keeping Up to Date

Re-run the script periodically. It fetches the latest CDN domain list from
upstream each time and regenerates the output file.

```bash
python azcachedns.py
```
