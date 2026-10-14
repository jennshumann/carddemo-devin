from decimal import Decimal

import pytest

from cbact01c_logic import (
    cobdatft_type2_to_type2, decode_zoned, encode_packed, encode_zoned,
    from_rdw, to_rdw,
)


@pytest.mark.parametrize("text,value", [
    (b"00000001940{", Decimal("194.00")),
    (b"00000001234N", Decimal("-123.45")),
    (b"00000000000}", Decimal("0")),
    (b"00000077777G", Decimal("7777.77")),
])
def test_decode_zoned(text, value):
    assert decode_zoned(text) == value


def test_encode_zoned_negative():
    assert encode_zoned(Decimal("-1025.00")) == b"00000010250}"


def test_encode_packed():
    assert encode_packed(Decimal("2525.00")) == bytes.fromhex("0000000252500c")
    assert encode_packed(Decimal("-2500.00")) == bytes.fromhex("0000000250000d")


def test_cobdatft_reformats_to_yyyymmdd():
    assert cobdatft_type2_to_type2(b"2025-05-20") == b"20250520  "


def test_rdw_round_trip():
    records = [b"A" * 12, b"B" * 39]
    data = to_rdw(records)
    assert data[:4] == bytes([0, 16, 0, 0])
    assert from_rdw(data) == records
