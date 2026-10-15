# Hardware

## GeekMagic SmallTV-Ultra

| Part | Detail |
|---|---|
| Module | ESP-12F (ESP8266EX), 4 MB SPI flash, DIO mode, 40 MHz |
| Display | 1.54" 240x240 IPS, ST7789, 4-wire SPI |
| Power | USB-C, 5 V |

### Pins

| Signal | GPIO | Notes |
|---|---|---|
| SPI clock | 14 | hardware SPI |
| SPI data (MOSI) | 13 | hardware SPI |
| Data/command | 0 | also a boot strap pin |
| Reset | 2 | also a boot strap pin |
| Chip select | 15 | also a boot strap pin; held low, the panel is the only SPI device |
| Backlight | 5 | PWM, active low |

The panel runs in SPI mode 3 at 40 MHz with 16-bit colour, inversion on and RGB order. If a unit shows swapped or inverted colours, change `panel.bgr` or `panel.invert` in the host config.

### Flash layout

The firmware uses the same layout as the stock Ultra firmware, the Arduino ESP8266 `4M3M` layout:

| Region | Flash offset | Size |
|---|---|---|
| Application (and update staging) | `0x000000` | 1 MB |
| LittleFS (stock web UI, settings, photos) | `0x100000` | 3,121,152 bytes |
| EEPROM, RF calibration, SDK Wi-Fi config | `0x3FA000` | 24 KB |

SmallTV Live never mounts the file system, so the stock data stays as it was. The stock updater only has room for an image of about 520 KB next to the running stock firmware; SmallTV Live is about 340 KB. From SmallTV Live, the 505 KB stock image fits back the same way.

### Serial header

The board has no USB-to-serial chip. For recovery, open the case (two screws underneath) and use the labelled pads: 3V3, GND, TX, RX and GPIO0. Hold GPIO0 to GND while powering on to enter flash mode. See [recovery.md](recovery.md).

## Sources

- [ESPHome device page: GeekMagic Ultra](https://devices.esphome.io/devices/geekmagic-ultra/)
- [smalltv-mod](https://github.com/giovi321/smalltv-mod): board notes and the Ultra's stock flash layout
- The stock firmware image header (DIO, 4 MB) and its file system size (`/space.json` reports 3,121,152 bytes total)
