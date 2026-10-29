"""The container's HMAC-SHA256 trailer: where it sits, and how to write it.

Ported from `append_trailer` and `syx_content_digest` in
mischa85/elektron-firmware-tool (`main.c`, `integrity.c`), MIT.

The trailer is the last 32 bytes of the declared container. It is placed on the
first 16-byte boundary at least four bytes past the end of the sections, the
gap is zeroed, and the digest covers everything before it -- so the digest is
over the container including that padding, not only the sections.
"""

import hashlib
import hmac

DIGEST_BYTES = 32
_ALIGN = 16
_MIN_GAP = 4


def offset(sections_end: int) -> int:
    """Where the digest goes, given the offset just past the last section."""
    return (sections_end + _MIN_GAP + _ALIGN - 1) & ~(_ALIGN - 1)


def compute(key: bytes, container: bytes, upto: int) -> bytes:
    """HMAC-SHA256 over `container[:upto]`."""
    return hmac.new(key, container[:upto], hashlib.sha256).digest()


def append(body: bytes, key: bytes) -> bytes:
    """Return `body` padded and signed: the complete declared container."""
    at = offset(len(body))
    padded = body + bytes(at - len(body))
    return padded + compute(key, padded, at)


def pad_unsigned(body: bytes) -> bytes:
    """Length an unsigned container takes: sections rounded up to 16 bytes.

    The Digitone 1.42A image is unsigned, and this is the shape its container
    takes -- no digest, just alignment padding.
    """
    return body + bytes(((len(body) + _ALIGN - 1) & ~(_ALIGN - 1)) - len(body))


def verify(key: bytes, container: bytes) -> bool:
    """Check a complete declared container against its own trailer."""
    if len(container) < DIGEST_BYTES:
        return False
    upto = len(container) - DIGEST_BYTES
    return hmac.compare_digest(compute(key, container, upto), container[upto:])
