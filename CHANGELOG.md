# Changelog

All notable changes to this project are listed here. Versions follow [Semantic Versioning](https://semver.org).

## [1.0.0] - 2026-10-15

### Added
- Firmware for the GeekMagic SmallTV-Ultra: streams RGB565 rectangles from a host over TCP 7777 straight to the panel, with frame acknowledgement for flow control.
- Same flash layout as the stock firmware; the stock file system is never mounted, so the stock firmware can be flashed back from `/update`.
- Wi-Fi from the stored SDK configuration, with an open setup access point and Wi-Fi form as a fallback.
- Status page, `smalltv.local` via mDNS, and a status screen with the IP address when no host is connected.
- Firmware upload and Wi-Fi changes only in setup mode or the first 10 minutes after power-on.
- Wi-Fi page lists nearby networks. In setup mode the saved network is retried every two minutes, so the TV recovers by itself when it started before the router.
- Host package (`smalltv-live`): clock with seconds, weather from Open-Meteo, Claude usage rings, an animated Boston terrier that follows the weather, night brightness, English and Romanian labels.
- `smalltv-live statusline` to cache Claude Code usage limits for the screen.
- macOS installer with an app launcher and login agent; Linux systemd example.
