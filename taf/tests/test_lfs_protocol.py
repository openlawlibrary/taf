"""Unit tests for the pkt-line framing in ``taf.lfs_protocol``."""

import io

import pytest

from taf.lfs_protocol import (
    FLUSH,
    MAX_PAYLOAD,
    encode,
    encode_stream,
    encode_text,
    read_packet,
    read_section,
    read_text_section,
)


def test_encode_prefixes_the_length_including_the_header():
    assert encode(b"hi") == b"0006hi"


def test_encode_rejects_a_payload_that_does_not_fit():
    with pytest.raises(ValueError, match="exceeds"):
        encode(b"x" * (MAX_PAYLOAD + 1))


def test_encode_text_terminates_the_line():
    assert encode_text("version=2") == b"000eversion=2\n"


def test_encode_stream_splits_at_the_packet_limit():
    packets = list(encode_stream(b"x" * (MAX_PAYLOAD + 10)))
    assert len(packets) == 2
    assert packets[0] == encode(b"x" * MAX_PAYLOAD)
    assert packets[1] == encode(b"x" * 10)


def test_encode_stream_emits_nothing_for_empty_input():
    assert list(encode_stream(b"")) == []


def test_read_packet_returns_none_at_a_flush():
    assert read_packet(io.BytesIO(FLUSH)) is None


def test_read_section_stops_at_the_flush():
    stream = io.BytesIO(encode(b"a") + encode(b"b") + FLUSH + encode(b"c") + FLUSH)
    assert read_section(stream) == [b"a", b"b"]
    assert read_section(stream) == [b"c"]


def test_read_text_section_strips_the_line_endings():
    stream = io.BytesIO(encode_text("status=success") + FLUSH)
    assert read_text_section(stream) == ["status=success"]


def test_read_packet_reports_a_stream_that_ends_mid_packet():
    """A filter process that has died looks exactly like this."""
    with pytest.raises(EOFError, match="short of"):
        read_packet(io.BytesIO(b"0010abc"))


def test_read_packet_rejects_a_malformed_header():
    with pytest.raises(EOFError, match="not a pkt-line header"):
        read_packet(io.BytesIO(b"zzzzbody"))


def test_read_packet_rejects_a_length_below_the_header():
    with pytest.raises(EOFError, match="below the header size"):
        read_packet(io.BytesIO(b"0002"))


def test_a_payload_survives_a_round_trip_through_many_packets():
    payload = bytes(range(256)) * 700
    framed = b"".join(encode_stream(payload)) + FLUSH
    assert b"".join(read_section(io.BytesIO(framed))) == payload
