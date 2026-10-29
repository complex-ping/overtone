"""The container content checksum, carried in the transport preamble at [4:8].

Ported from `syx_content_checksum` in mischa85/elektron-firmware-tool
(`integrity.c`), MIT.

Not a standard checksum: a running 32-bit sum where each big-endian word is
XORed with its own one-based index before being added. Trailing bytes that do
not fill a word are not covered.
"""


def content(container: bytes) -> int:
    """Checksum of `container` -- pass exactly the declared container length."""
    acc = 0
    for k in range(len(container) // 4):
        word = int.from_bytes(container[4 * k : 4 * k + 4], "big")
        acc = (acc + (((k + 1) & 0xFFFFFFFF) ^ word)) & 0xFFFFFFFF
    return acc
