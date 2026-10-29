"""The Elektron block-streaming SysEx transport: data packets and markers on
one side, a flat decoded byte stream on the other.

Ported from `syx_transport_decode`/`syx_encode` in
mischa85/elektron-firmware-tool (`decompress.c`, `compress.c`), MIT.

Scope: the 126-byte-packet transport used by every ELE3-era instrument, which
covers both Digitones. The legacy Machinedrum/Monomachine (2+7+7) and Octatrack
(ELEK) transports are deliberately not implemented here — no Digitone uses
them, and an untested implementation of a format we cannot check against a real
file would be a liability rather than a feature.

Layout of one message body (between F0 and F7):

    data packet, 126 B : 00 20 3C <dev> 00 7E <block:2> <seq> <116B payload> <cksum>
    marker,       14 B : 00 20 3C <dev> 00 7F <kind> <7B info>

Each data packet's 116-byte payload is 8-in-7, carrying exactly 101 decoded
bytes; the final packet is zero-padded to that length.
"""

from dataclasses import dataclass

from . import checksum, encode87, frame

MANUFACTURER = bytes((0x00, 0x20, 0x3C))

PACKET_BODY = 126  # data-packet body size
HEADER = 9  # bytes before the payload
PAYLOAD = 116  # 8-in-7 encoded payload bytes
DECODED_PER_PACKET = 101  # decoded bytes carried by one packet
MARKER_BODY = 14
MARKER_INFO = 7

CMD_DATA = 0x7E
CMD_MARKER = 0x7F
MARKER_START = 0x01
MARKER_END = 0x02

OFF_DEVICE = 3
OFF_COMMAND = 5
OFF_BLOCK = 6
OFF_SEQ = 8
OFF_PAYLOAD = 9
OFF_MARKER_KIND = 6
OFF_MARKER_INFO = 7

MASK7 = 0x7F


@dataclass(frozen=True)
class Envelope:
    """Everything about a file's transport that is not its payload.

    Kept so a rebuild can reproduce the original framing exactly: the device
    id, the checksum seed, and the marker info template that carries the
    starting block/sequence counter.
    """

    device: int
    base: int
    marker_info: bytes


@dataclass(frozen=True)
class Decoded:
    stream: bytes
    envelope: Envelope
    packets: int
    checksums_ok: int
    checksums_bad: int


def decode(raw: bytes) -> Decoded:
    """Decode a `.syx` file into its flat byte stream.

    Raises ValueError if the file carries no start marker, because without one
    there is no checksum seed and nothing can be verified.
    """
    bodies = frame.split(raw)
    envelope = _read_envelope(bodies)

    stream = bytearray()
    packets = ok = bad = 0
    for body in bodies:
        if len(body) != PACKET_BODY or body[OFF_COMMAND] != CMD_DATA:
            continue
        packets += 1
        stream += encode87.decode(body[OFF_PAYLOAD : OFF_PAYLOAD + PAYLOAD])
        if checksum.packet(body, envelope.base) == body[checksum.CHECKSUM_OFFSET]:
            ok += 1
        else:
            bad += 1

    return Decoded(bytes(stream), envelope, packets, ok, bad)


def encode(stream: bytes, envelope: Envelope) -> bytes:
    """Encode a flat byte stream back into a `.syx` file.

    The stream is zero-padded to a whole number of packets, which is what the
    original files do — a stream that is an exact multiple still gets one more
    packet, matching `syx_encode`'s `total // 101 + 1`.
    """
    count = len(stream) // DECODED_PER_PACKET + 1
    padded = stream + bytes(count * DECODED_PER_PACKET - len(stream))

    out = bytearray()
    out += frame.wrap(_marker(MARKER_START, count, envelope))
    for k in range(count):
        chunk = padded[k * DECODED_PER_PACKET : (k + 1) * DECODED_PER_PACKET]
        out += frame.wrap(_packet(k, chunk, envelope))
    out += frame.wrap(_marker(MARKER_END, count, envelope))
    return bytes(out)


def _read_envelope(bodies: list[bytes]) -> Envelope:
    device = bodies[0][OFF_DEVICE] if bodies and len(bodies[0]) > OFF_DEVICE else 0
    for body in bodies:
        if len(body) >= OFF_MARKER_INFO + MARKER_INFO and body[OFF_COMMAND] == CMD_MARKER:
            info = body[OFF_MARKER_INFO : OFF_MARKER_INFO + MARKER_INFO]
            return Envelope(device=device, base=info[0], marker_info=bytes(info))
    raise ValueError("no SysEx start marker: not an Elektron OS file")


def _marker(kind: int, packets: int, envelope: Envelope) -> bytes:
    info = bytearray(envelope.marker_info)
    info[0] = envelope.base
    info[4] = (packets >> 14) & MASK7
    info[5] = (packets >> 7) & MASK7
    info[6] = packets & MASK7
    body = bytearray(MANUFACTURER)
    body += bytes((envelope.device, 0x00, CMD_MARKER, kind))
    body += info
    return bytes(body)


def _packet(index: int, chunk: bytes, envelope: Envelope) -> bytes:
    """One data packet. Block and sequence are a single 7-bit-wrapping counter
    starting at the marker's info[1..3], so a rebuild continues the original
    file's numbering rather than restarting it."""
    start_block = (envelope.marker_info[1] << 7) | envelope.marker_info[2]
    cumulative = envelope.marker_info[3] + index
    block = start_block + (cumulative >> 7)

    body = bytearray(MANUFACTURER)
    body += bytes((envelope.device, 0x00, CMD_DATA))
    body += bytes(((block >> 7) & MASK7, block & MASK7, cumulative & MASK7))
    body += encode87.encode(chunk)
    body.append(checksum.packet(body, envelope.base))
    return bytes(body)
