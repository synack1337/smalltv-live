# Recovery and going back to stock

## Back to the stock firmware

SmallTV Live does not touch the stock file system, so the GeekMagic web pages, settings and photos are still there.

1. Download the latest Ultra firmware from [GeekMagicClock/smalltv-ultra](https://github.com/GeekMagicClock/smalltv-ultra) and compare its MD5 with the `md5sum.txt` next to it.
2. Power-cycle the TV. Uploads are accepted for 10 minutes after power-on.
3. Open `http://<tv-ip>/update`, select the `.bin` and press **Update**.

The TV restarts into the stock firmware. If it can't join your Wi-Fi, it opens its own setup access point as described in GeekMagic's manual.

## Updating SmallTV Live

Same steps with a newer `smalltv-live-firmware.bin`: power-cycle, then upload within 10 minutes. `http://<tv-ip>/` shows whether the upload window is open.

## The TV doesn't come up

- **Amber bars and 192.168.4.1 on screen:** setup mode. Join the **SmallTV-Live** network and set Wi-Fi at `http://192.168.4.1/wifi`. Firmware upload also works there. If your usual network was only down for a while (a power cut), the TV goes back to it on its own within a couple of minutes of it returning.
- **Green bars and an IP, nothing else:** the TV is fine and waiting for the host. Check the host log and, on macOS, the Local Network permission.
- **Black screen and no network:** use the serial header.

## Serial recovery

You need a 3.3 V USB-to-serial adapter (never 5 V) and [esptool](https://github.com/espressif/esptool).

1. Open the case: remove the two screws underneath and slide out the board tray.
2. Connect adapter GND to GND, adapter TX to RX, adapter RX to TX, and power from the adapter's 3.3 V to 3V3 (or power the TV over USB and leave 3V3 unconnected).
3. Hold GPIO0 to GND while powering on, then release it.
4. Write an application image at offset 0. This leaves the file system in place:

   ```sh
   esptool.py --port /dev/cu.usbserial-XXXX write_flash 0x0 smalltv-live-firmware.bin
   # or the stock image:
   esptool.py --port /dev/cu.usbserial-XXXX write_flash 0x0 FW-Smalltv-Ultra-V9.0.50.bin
   ```

Before experimenting further, you can read a full backup with `esptool.py read_flash 0x0 0x400000 smalltv-backup.bin`.
