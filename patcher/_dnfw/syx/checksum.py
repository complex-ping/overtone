"""The per-packet transport checksum carried in the last byte of a data-packet
body.

Ported from `syx_block_checksum` in mischa85/elektron-firmware-tool
(`integrity.c`), MIT.

The sum covers body[BLOCK_OFFSET .. CHECKSUM_OFFSET), each byte XORed with a
running `base + index`, and `base` added once more at the end. `base` is not a
constant: it is the start marker's first info byte, so it comes from the file
being read (or from the file being reproduced) — see `syx.transport`.
"""

BLOCK_OFFSET = 6  # first body byte the checksum covers
CHECKSUM_OFFSET = 125  # body offset of the checksum byte itself
SPAN = CHECKSUM_OFFSET - BLOCK_OFFSET  # 119 covered bytes
MASK7 = 0x7F


def packet(body: bytes, base: int) -> int:
    """Checksum byte for one 126-byte data-packet body, seeded with `base`."""
    acc = 0
    for i in range(SPAN):
        acc += body[BLOCK_OFFSET + i] ^ ((base + i) & 0xFF)
    return (base + acc) & MASK7
