"""What a loaded firmware file is: the three layers, plus the few transport
facts a faithful rebuild needs to reproduce.

No parsing and no I/O here -- see `firmware.load` and `firmware.build`.
"""

from dataclasses import dataclass

from ..container.ele3 import Container
from ..integrity.keyderive import Key
from ..syx.transport import Envelope

PREAMBLE = 8  # [u32 container size][u32 content checksum] ahead of the container


@dataclass(frozen=True)
class Firmware:
    """A `.syx` OS file, decoded.

    `stored_checksum` and `packets` are what the file claimed, kept so
    `firmware.verify` can compare them against what we compute rather than
    silently recomputing and reporting success.
    """

    envelope: Envelope
    container: Container
    raw_container: bytes  # the container exactly as decoded, for verification
    key: Key | None
    stored_checksum: int
    packets: int
    checksums_ok: int
    checksums_bad: int

    @property
    def signed(self) -> bool:
        return self.key is not None
