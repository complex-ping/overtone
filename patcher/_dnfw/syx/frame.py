"""SysEx message framing: splitting a byte stream into F0..F7 message bodies,
and wrapping a body back up.

A "body" throughout this package is the bytes *between* F0 and F7, exclusive.
Nothing here knows what a body means — see `syx.transport` for that.
"""

START = 0xF0
END = 0xF7


def split(stream: bytes) -> list[bytes]:
    """Return every complete F0..F7 body in `stream`, in order.

    Bytes outside a message are skipped, and a trailing F0 with no F7 is
    dropped rather than guessed at.
    """
    bodies: list[bytes] = []
    i = 0
    n = len(stream)
    while i < n:
        if stream[i] != START:
            i += 1
            continue
        end = stream.find(END, i + 1)
        if end < 0:
            break
        bodies.append(stream[i + 1 : end])
        i = end + 1
    return bodies


def wrap(body: bytes) -> bytes:
    """Wrap one body in F0..F7."""
    return bytes((START,)) + body + bytes((END,))
