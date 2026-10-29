"""One ELE3 section: the 8-byte header in front of a compressed stream, and
the question of whether a section is compressed at all.

    [u32 stream length BE][u32 sum of the stream bytes BE][stream ...]

Not every section has this. On both Digitones `meta`, `updater` and `boot` --
and DN1's `blob` -- are stored raw, and the only reliable test is whether the
bytes depack. So a section is modelled as its **stored** bytes, exactly as they
sit in the container, and compression is something we discover rather than
assume. `dnfw build` must never recompress a section it could not depack.

**A compressed section is zero-padded to a multiple of four bytes.** The header
still gives the exact stream length and the sum of the stream alone; the
padding sits after the stream and is counted only in the section table's
length. Every compressed section of Digitone II OS 1.10D, 1.10E and 1.11 --
eleven of them -- follows this, with 0 to 3 bytes of padding each. Images
built without it boot through the normal update path and stall in recovery,
so it is written here rather than left to chance. See `docs/flashing.md`.
"""

from dataclasses import dataclass

from ..codec import aplib, aplibpack

HEADER = 8
STORED_ALIGN = 4  # compressed sections are zero-padded to this


@dataclass(frozen=True)
class Section:
    """A section as the container holds it."""

    id: int
    dest: int
    stored: bytes

    @property
    def declared_length(self) -> int:
        """Stream length from the header. Meaningless on a raw section."""
        return int.from_bytes(self.stored[0:4], "big")

    @property
    def declared_sum(self) -> int:
        return int.from_bytes(self.stored[4:8], "big")

    @property
    def computed_sum(self) -> int:
        """Sum of the declared stream bytes, which is what the header claims."""
        end = min(HEADER + self.declared_length, len(self.stored))
        return sum(self.stored[HEADER:end]) & 0xFFFFFFFF

    @property
    def stream(self) -> bytes:
        """The compressed stream the header describes, header excluded.
        Meaningless on a raw section."""
        return self.stored[HEADER : HEADER + self.declared_length]

    @property
    def sum_ok(self) -> bool:
        return self.declared_sum == self.computed_sum

    @property
    def raw_payload(self) -> bytes:
        """What a *raw* section actually loads at `dest`, header excluded.

        Not every raw section carries a header, and the difference is eight
        bytes of silent misalignment for anyone who loads the result:

            id 4  updater  **header present**, declared sum 0, payload raw
            id 5  meta     15 ASCII bytes of build stamp, no header at all

        The test is the declared sum. A real header whose stream is stored
        rather than packed has **sum 0** — there is no stream to sum — while a
        section that is nothing but payload has arbitrary bytes there, which for
        `meta` are ASCII and so never zero.

        Deciding this from the section *id* would be a guess; this is a check.

        **Measured, not reasoned.** Until 2026-09-13 `dnfw extract` wrote raw
        sections whole, so section 4 came out 32,776 bytes against
        `m-dwyer/digikit`'s 32,768, with `ours[8:] == theirs` exactly. digikit's
        layout is confirmed by execution — it runs the updater's own aPLib
        depacker at `0x80000432` from that base and reproduces every compressed
        section byte-for-byte — so the eight bytes are a header and ours were
        payload by mistake. See `docs/emulator.md`.
        """
        if len(self.stored) > HEADER and self.declared_sum == 0:
            return self.stored[HEADER:]
        return self.stored

    def unpack(self) -> bytes | None:
        """The section content, or None if these bytes are not an aPLib stream.

        Truncation is tolerated: a raw section can decode a few plausible bytes
        before running out, so the caller distinguishes raw from compressed by
        None rather than by trusting a length field it has no reason to.
        """
        if len(self.stored) <= HEADER:
            return None
        try:
            out = aplib.depack(self.stored[HEADER:], allow_truncated=True)
        except aplib.DepackError:
            return None
        return out or None


def compress(section_id: int, dest: int, content: bytes) -> Section:
    """Build a compressed section from raw content: header, stream, padding."""
    stream = aplibpack.pack(content)
    header = len(stream).to_bytes(4, "big") + (sum(stream) & 0xFFFFFFFF).to_bytes(4, "big")
    padding = bytes(-(HEADER + len(stream)) % STORED_ALIGN)
    return Section(id=section_id, dest=dest, stored=header + stream + padding)


def store_raw(section_id: int, dest: int, content: bytes) -> Section:
    """Build a section that is stored verbatim, for the sections that are."""
    return Section(id=section_id, dest=dest, stored=content)
