# Stream protocol

The host connects to the TV on TCP port **7777** and sends messages. Each message starts with a 9-byte header:

| Offset | Size | Field |
|---|---|---|
| 0 | 1 | type (ASCII) |
| 1 | 1 | x |
| 2 | 1 | y |
| 3 | 1 | width - 1 |
| 4 | 1 | height - 1 |
| 5 | 4 | payload length, unsigned, little endian |

The payload follows the header directly.

| Type | Meaning | Payload |
|---|---|---|
| `R` | Rectangle of pixels at (x, y), width x height | exactly `width * height * 2` bytes of RGB565, big endian (high byte first), row by row |
| `F` | End of frame | none. The TV answers with one byte, `K`, once every earlier message has reached the panel |
| `B` | Backlight level `x` (0 to 255) | none |
| `C` | Panel command `x` | parameter bytes. Only `0x20`/`0x21` (inversion off/on, no parameters) and `0x36` (memory access control, one byte) are accepted |

The panel is 240x240, so every rectangle must satisfy `x + width <= 240` and `y + height <= 240`.

Any malformed message (unknown type, wrong payload length, rectangle off screen, disallowed panel command) closes the connection. The host is expected to reconnect and send a full frame.

## Flow control

The host sends a frame's rectangles followed by `F` and waits for `K` before sending the next frame. That keeps at most one frame in flight and lets a slow Wi-Fi link set the frame rate.

## Connections

One host is served at a time. A new connection replaces the current one, so a host that reconnects after a network drop is never locked out. A connection that sends nothing for 15 seconds is closed. If no frame arrives for 2 minutes, the TV shows its status screen again.

## Example

A full first frame is a single `R` message covering (0, 0, 240, 240) with 115,200 bytes of pixels, then `F`. Later frames usually carry a few small rectangles: the seconds, the dog and anything else that moved.
