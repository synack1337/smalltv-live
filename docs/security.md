# Security

SmallTV Live is a display for a trusted home network. This page lists what the firmware and the host expose and how they are protected.

## Firmware

| Surface | Access | Protection |
|---|---|---|
| Stream port, TCP 7777 | anyone on the LAN | Every message is validated (types, sizes, screen bounds) and malformed input closes the connection. Only display output is possible: pixels, backlight and two colour-related panel commands. |
| Status page `/` | anyone on the LAN | Read only. Shows the IP, network name, signal and counters. No passwords. |
| Firmware upload `/update` | anyone on the LAN, **only during the first 10 minutes after power-on** | Outside that window uploads are refused before anything is written. Inside it, the standard ESP8266 updater checks the image header and size. |
| Wi-Fi settings `/wifi` | **setup mode only** (the open SmallTV-Live access point) | Not served once the TV is on your network, so nobody can move it to another network. |
| Setup access point | open, only when the stored Wi-Fi fails | Same behaviour as the stock firmware's setup mode. |

The stock GeekMagic firmware also has no authentication on its web pages and accepts firmware uploads at any time, so this is a tighter default than stock.

What an attacker on your LAN can do: show other images on the TV, and flash firmware if they can make it restart (for example by cutting its power) and reach it in the next 10 minutes. Keep the TV on a network you trust, or on a separate IoT network.

The firmware stores no secrets of its own. Wi-Fi credentials live in the ESP8266 SDK configuration, as with the stock firmware.

## Host

- Connects to the TV and to `api.open-meteo.com` over HTTPS. Nothing else.
- Reads `~/.claude/rate_limits.json`, which holds only usage percentages and reset times. The `statusline` command writes that file with mode 0600 and keeps only those fields from the JSON Claude Code passes in. It never reads or stores credentials.
- `statusline --then` runs the given command without a shell, with a 10 second timeout.
- The config file is parsed with `tomllib`, unknown keys are rejected and every value is range-checked.

## Static analysis notes

Snyk Code reports four findings that are intended behaviour, not vulnerabilities:

| Finding | Why it stands |
|---|---|
| Command injection, `host/smalltv_live/__main__.py` (`statusline --then`) | Runs the user's own previous status line command, from their own Claude Code settings, so that it keeps working. It is split with `shlex` and run without a shell, with a timeout. |
| Path traversal, `host/smalltv_live/config.py` | The config path comes from the user's own environment (`$SMALLTV_LIVE_CONFIG`, `$XDG_CONFIG_HOME`). The program runs as that user, so no privilege boundary is crossed. |
| Path traversal, `macos/launcher.c` | The log path is built from `$HOME`, which must be absolute; the file is opened with `O_NOFOLLOW`, so a symlink at that path is refused. |

Dependencies are pinned in `host/requirements.txt` and watched by Dependabot; GitHub Actions are pinned to commit SHAs.

## Reporting

See [SECURITY.md](../SECURITY.md).
