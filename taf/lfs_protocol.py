"""The pkt-line framing git uses to talk to long-running filter processes.

A packet is a four-digit hexadecimal length - counting the four digits
themselves - followed by that many bytes minus four. ``0000`` is a flush,
which ends a section. ``git-lfs filter-process`` speaks this on stdin and
stdout, so one process can serve every file of a checkout instead of one
process per file.

Reference: https://git-scm.com/docs/protocol-common#_pkt_line_format
"""

from typing import IO, Iterator, List, Optional

#: A packet's payload cannot exceed the length its four hex digits can express.
MAX_PAYLOAD = 65516

FLUSH = b"0000"


def encode(payload: bytes) -> bytes:
    """Frame ``payload`` as one packet."""
    if len(payload) > MAX_PAYLOAD:
        raise ValueError(f"payload of {len(payload)} exceeds {MAX_PAYLOAD}")
    return b"%04x" % (len(payload) + 4) + payload


def encode_stream(payload: bytes) -> Iterator[bytes]:
    """Frame ``payload`` as as many packets as its length requires."""
    if not payload:
        return
    for start in range(0, len(payload), MAX_PAYLOAD):
        yield encode(payload[start : start + MAX_PAYLOAD])


def encode_text(line: str) -> bytes:
    """Frame ``line`` as one packet, newline-terminated as the protocol expects."""
    return encode(line.encode() + b"\n")


def read_packet(stream: IO[bytes]) -> Optional[bytes]:
    """The next packet's payload, or None at a flush.

    Raises ``EOFError`` if the stream ends mid-packet, which is what a filter
    process that has died looks like from here.
    """
    header = _read_exactly(stream, 4)
    if header == FLUSH:
        return None
    try:
        length = int(header, 16)
    except ValueError as error:
        raise EOFError(f"not a pkt-line header: {header!r}") from error
    if length < 4:
        raise EOFError(f"pkt-line length {length} is below the header size")
    return _read_exactly(stream, length - 4)


def read_section(stream: IO[bytes]) -> List[bytes]:
    """Every packet up to the next flush."""
    packets = []
    while (packet := read_packet(stream)) is not None:
        packets.append(packet)
    return packets


def read_text_section(stream: IO[bytes]) -> List[str]:
    """``read_section``, decoded and stripped, for the protocol's key=value lines."""
    return [packet.decode().strip() for packet in read_section(stream)]


def _read_exactly(stream: IO[bytes], count: int) -> bytes:
    chunks = []
    remaining = count
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise EOFError(f"stream ended {remaining} bytes short of {count}")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
