"""The limits Elektron's own compressed streams stay inside.

The aPLib format can express a match reaching back to the start of the output,
however far that is. Elektron's packer never does. Measured over every
compressed section of Digitone II OS 1.11 (2026-09-11):

    section        output   furthest match   longest match
    bootstrap      30,302           28,368           2,048
    MAIN OS     3,192,192        1,048,553           2,048
    blob          836,956          826,328           2,048
    8             159,948           49,144           2,048

MAIN OS is three megabytes, so material further back than 1 MiB was there to
be used, and 52,461 of its matches reach past 64 KiB -- the packer is not
timid, it is bounded. **The window is 1 MiB.** The longest match is exactly
2,048 in every section, so that is a cap too.

Why it matters: images of ours with no window boot through the normal update
path and stall in the Early Start-up Menu's recovery flash. The normal path can
decompress into RAM, where any distance works; a bootloader writing flash as
it goes has no reason to keep more history than the packer that made the image
ever needed. That is the leading explanation, not a proven one -- see
`docs/flashing.md`.

`WINDOW` is what an image is checked against. `PACK_MAX_OFFSET` is what we
emit, and sits a margin inside it on purpose: every offset we produce is then
smaller than one Elektron's own images already show the device accepting,
rather than merely inside a limit we inferred.
"""

WINDOW = 1 << 20  # every match offset in an Elektron stream is below this
MAX_MATCH = 2048  # and no match copies more bytes than this

_MARGIN = 4096
PACK_MAX_OFFSET = WINDOW - _MARGIN  # 1,044,480: under the 1,048,553 measured
