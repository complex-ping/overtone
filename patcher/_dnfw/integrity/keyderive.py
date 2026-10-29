"""Recovering the device HMAC key from the firmware's own key material.

Ported from `elektron_extract_key`/`derive_key` in
mischa85/elektron-firmware-tool (`integrity.c`), MIT.

No key is stored in this repository and none needs to be. The material sits in
a decompressed section: an anchor, a printable string, a NUL, then a 32-byte
constant. The key is

    SHA256(s) XOR SHA256(reverse(s)) XOR constant

and a candidate is accepted only when it reproduces the image's own trailer, so
a wrong guess cannot be mistaken for the right one.

Measured on the two images we hold (2026-09-07): Digitone II 1.10E derives from
the string "Multiplier" in its bootstrap section and verifies. Digitone 1.42A has a
32-zero-byte trailer -- it is unsigned, and `find` correctly returns None.
"""

import hashlib
import hmac
from dataclasses import dataclass
from typing import Iterable

# The last two SHA-256 round constants, which sit immediately before the key
# material. Not itself a secret -- it is a published constant of the hash.
ANCHOR = bytes.fromhex("bef9a3f7c67178f2")
MAX_STRING = 64
KEY_BYTES = 32


@dataclass(frozen=True)
class Key:
    value: bytes
    derivation_string: str


def derive(string: bytes, constant: bytes) -> bytes:
    forward = hashlib.sha256(string).digest()
    backward = hashlib.sha256(string[::-1]).digest()
    return bytes(a ^ b ^ c for a, b, c in zip(forward, backward, constant))


def find(sections: Iterable[bytes], message: bytes, expected: bytes) -> Key | None:
    """Search decompressed sections for the key that signs `message` as
    `expected`. Returns None when no candidate verifies -- including when the
    firmware is simply unsigned."""
    for blob in sections:
        for candidate in _candidates(blob):
            key = derive(*candidate)
            if hmac.compare_digest(hmac.new(key, message, hashlib.sha256).digest(), expected):
                return Key(value=key, derivation_string=candidate[0].decode("ascii"))
    return None


def _candidates(blob: bytes):
    """Yield (string, constant) pairs at every anchor in `blob`."""
    start = blob.find(ANCHOR)
    while start >= 0:
        text = start + len(ANCHOR)
        end = text
        while end < len(blob) and 0x20 <= blob[end] < 0x7F and end - text < MAX_STRING:
            end += 1
        if end > text and end < len(blob) and blob[end] == 0 and end + 1 + KEY_BYTES <= len(blob):
            yield blob[text:end], blob[end + 1 : end + 1 + KEY_BYTES]
        start = blob.find(ANCHOR, start + 1)
