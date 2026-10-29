"""8-in-7 packing: MIDI SysEx carries 7-bit bytes, so the high bit of each of
seven data bytes is gathered into a leading byte.

Ported from `decode_payload`/`encode_8in7` in mischa85/elektron-firmware-tool
(`decompress.c`, `compress.c`), MIT, with thanks. Bit order is MSB-first: data
byte n of a group takes bit (6 - n) of the group's leading byte.
"""

GROUP = 7  # data bytes carried by one group, after its leading high-bit byte
HIGH_BIT = 0x80
MASK7 = 0x7F


def encode(data: bytes) -> bytes:
    """Pack 8-bit bytes into 8-in-7 groups. A trailing partial group is emitted
    with only the data bytes it has; its unused high-bit positions stay zero."""
    out = bytearray()
    for i in range(0, len(data), GROUP):
        group = data[i : i + GROUP]
        high = 0
        for n, b in enumerate(group):
            if b & HIGH_BIT:
                high |= 1 << (GROUP - 1 - n)
        out.append(high)
        out.extend(b & MASK7 for b in group)
    return bytes(out)


def decode(payload: bytes) -> bytes:
    """Unpack 8-in-7 groups back to 8-bit bytes.

    A group is a leading high-bit byte followed by up to GROUP data bytes; the
    final group may be short, which is how a 116-byte payload yields 101 bytes.
    """
    out = bytearray()
    i = 0
    n = len(payload)
    while i < n:
        high = payload[i]
        count = min(GROUP, n - i - 1)
        for k in range(count):
            bit = (high >> (GROUP - 1 - k)) & 1
            out.append(payload[i + 1 + k] | (HIGH_BIT if bit else 0))
        i += GROUP + 1
    return bytes(out)
