"""Decoding a `.syx` OS file into a `Firmware`.

The order is transport, then preamble, then container, then key -- each layer
handing the next only what it needs.
"""

from ..container import ele3
from ..integrity import digest, keyderive
from ..syx import transport
from .model import PREAMBLE, Firmware


def load(raw: bytes) -> Firmware:
    """Parse a `.syx` file. Raises ValueError if it is not an ELE3 OS image."""
    decoded = transport.decode(raw)
    stream = decoded.stream

    magic = stream.find(ele3.MAGIC)
    if magic < PREAMBLE:
        raise ValueError("no ELE3 container in this file")
    declared_size = int.from_bytes(stream[magic - PREAMBLE : magic - 4], "big")
    stored_checksum = int.from_bytes(stream[magic - 4 : magic], "big")

    container_bytes = stream[magic:]
    container = ele3.parse(container_bytes, declared_size)

    return Firmware(
        envelope=decoded.envelope,
        container=container,
        raw_container=container_bytes,
        key=_find_key(container_bytes, declared_size, container),
        stored_checksum=stored_checksum,
        packets=decoded.packets,
        checksums_ok=decoded.checksums_ok,
        checksums_bad=decoded.checksums_bad,
    )


def _find_key(container_bytes: bytes, declared_size: int, container: ele3.Container):
    """Recover the signing key, or None when the image is unsigned.

    Two short-circuits, both of which matter in practice. An all-zero trailer
    means unsigned -- that is the Digitone 1.42A image, and scanning for a key
    that cannot exist would mean depacking every section for nothing. And
    sections are searched smallest first, because the Digitone II key material
    lives in the 16 KB bootstrap section, so the 3 MB MAIN OS never has to be
    depacked to sign a build.
    """
    if declared_size < digest.DIGEST_BYTES + 4 or declared_size > len(container_bytes):
        return None
    expected = container_bytes[declared_size - digest.DIGEST_BYTES : declared_size]
    if not any(expected):
        return None

    message = container_bytes[: declared_size - digest.DIGEST_BYTES]
    ordered = sorted(container.sections, key=lambda s: len(s.stored))

    def blobs():
        for section in ordered:
            content = section.unpack()
            if content:
                yield content

    return keyderive.find(blobs(), message, expected)
