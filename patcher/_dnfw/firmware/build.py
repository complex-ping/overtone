"""Assembling a `.syx` OS file back from a `Firmware` plus replacements.

Ported in shape from `cmd_build`/`rebuild_container`/`build_preamble` in
mischa85/elektron-firmware-tool (`main.c`), MIT.

Order matters and is not negotiable: sections are laid out, then the trailer is
signed over the result, then the content checksum is taken over the whole
declared container, then the transport wraps it. Each integrity field covers
everything decided before it, so computing one early silently invalidates it.
"""

from ..container import ele3
from ..container.section import Section, compress, store_raw
from ..integrity import checksum, digest
from ..syx import transport
from .model import PREAMBLE, Firmware


class BuildError(ValueError):
    """The rebuild cannot be done safely."""


def replacement(firmware: Firmware, section_id: int, content: bytes) -> Section:
    """Wrap new content for `section_id` the way that section is stored.

    A section that depacks is recompressed; one that does not is stored raw.
    Getting this backwards would produce a file that passes every checksum and
    bricks the instrument, so the decision is taken from the original section
    rather than from an argument.
    """
    original = firmware.container.find(section_id)
    if original is None:
        raise BuildError(f"no section id={section_id} in this image")
    if original.unpack() is not None:
        return compress(section_id, original.dest, content)
    return store_raw(section_id, original.dest, content)


def build(firmware: Firmware, replacements: dict[int, Section] | None = None) -> bytes:
    """Return the complete `.syx` bytes for this firmware."""
    body = ele3.assemble(firmware.container, replacements or {})

    if firmware.key is not None:
        container = digest.append(body, firmware.key.value)
    else:
        container = digest.pad_unsigned(body)

    preamble = len(container).to_bytes(4, "big") + checksum.content(container).to_bytes(4, "big")
    if len(preamble) != PREAMBLE:
        raise BuildError("preamble is not 8 bytes")

    return transport.encode(preamble + container, firmware.envelope)
