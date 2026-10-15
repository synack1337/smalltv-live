# Running the host on Linux

```sh
python3 -m venv ~/.local/share/smalltv-live
~/.local/share/smalltv-live/bin/pip install -r host/requirements.txt ./host
mkdir -p ~/.config/smalltv-live
cp config.example.toml ~/.config/smalltv-live/config.toml   # then edit it
```

The San Francisco fonts are only available on macOS; on Linux the host falls back to Pillow's built-in font.

## systemd user service

`~/.config/systemd/user/smalltv-live.service`:

```ini
[Unit]
Description=SmallTV Live host
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=%h/.local/share/smalltv-live/bin/smalltv-live run
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
```

```sh
systemctl --user daemon-reload
systemctl --user enable --now smalltv-live
journalctl --user -u smalltv-live -f
```
