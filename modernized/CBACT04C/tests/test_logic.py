from datetime import datetime

import pytest

from cbact04c_logic import (
    CobolAbend, db2_timestamp, decode_zoned, encode_zoned, fit, monthly_interest,
    normalize_parm, parse_records, run_intcalc,
)

NOW = datetime(2022, 7, 18, 13, 5, 9, 876543)


def acct(acct_id, bal="00000010000{", group="GOLD"):
    return (f"{acct_id:011d}Y{bal}" + "00000050000{" * 2 + "2014-11-20" * 3
            + "00000000500{00000000250{" + "A000000000" + f"{group:<10}").ljust(300).encode()


def tcat(acct_id, type_cd, cat, bal):
    return f"{acct_id:011d}{type_cd}{cat:04d}{bal}".ljust(50, "0").encode()


def disc(group, type_cd, cat, rate):
    return f"{group:<10}{type_cd}{cat:04d}{rate}".ljust(50, "0").encode()


def xref(card, acct_id):
    return f"{card:<16}{acct_id:09d}{acct_id:011d}".ljust(50).encode()


@pytest.mark.parametrize("raw,units", [
    (b"0000000000{", 0), (b"0000012345F", 123456), (b"0000003333L", -33333),
    (b"000000100000", 100000), (b"00150{", 1500),
])
def test_decode_zoned(raw, units):
    assert decode_zoned(raw) == units


@pytest.mark.parametrize("units,digits,raw", [
    (1953, 11, b"0000000195C"), (-125, 11, b"0000000012N"), (0, 11, b"0000000000{"),
    (1023332499991, 12, b"02333249999A"),  # high-order truncation
])
def test_encode_zoned(units, digits, raw):
    assert encode_zoned(units, digits) == raw


def test_negative_value_that_truncates_to_zero_is_stored_positive():
    assert encode_zoned(-10 ** 11, 11) == b"0000000000{"


@pytest.mark.parametrize("bal,rate,expected", [
    (123456, 1899, 1953),           # 19.536... truncated, not rounded
    (-10001, 1500, -125),           # truncation toward zero for negatives
    (-33333, -500, 138),
    (7, 2500, 0),
    (-1, 1500, 0),
    (99999999999, 999999, 33332499991),  # overflow keeps low-order 9 integer digits
])
def test_monthly_interest(bal, rate, expected):
    assert monthly_interest(bal, rate) == expected


def test_fit():
    assert fit(-1234567, 4) == -4567


def test_db2_timestamp():
    assert db2_timestamp(NOW) == b"2022-07-18-13.05.09.870000"


def test_parse_records_line_sequential_crlf_and_padding():
    assert parse_records(b"AB\r\nC\n", 4) == [b"AB  ", b"C   "]
    assert parse_records(b"AB", 4, "line") == [b"AB  "]  # no trailing LF


def test_parse_records_fixed_length():
    assert parse_records(b"AAAABBBB", 4, "fixed") == [b"AAAA", b"BBBB"]
    assert parse_records(b"A\nAABBBB", 4, "fixed") == [b"A\nAA", b"BBBB"]  # LF is data
    assert parse_records(b"", 4, "fixed") == []
    with pytest.raises(ValueError):
        parse_records(b"AAAAB", 4, "fixed")
    with pytest.raises(ValueError):
        parse_records(b"AAAA", 4, "vb")


def test_parm_is_first_ten_bytes_space_padded():
    assert normalize_parm("2022071800") == b"2022071800"
    assert normalize_parm("20220718") == b"20220718  "
    assert normalize_parm("2022071800EXTRA") == b"2022071800"
    assert normalize_parm("") == b" " * 10


def test_duplicate_primary_key_rejected():
    with pytest.raises(ValueError, match="TCATBALF"):
        run_intcalc([tcat(1, "01", 1, "0000010000{")] * 2, [acct(1)], [xref("C1", 1)],
                    [disc("GOLD", "01", 1, "00150{")], "2022071800", lambda: NOW)


def test_tranid_sequence_spans_accounts_and_skips_zero_rates():
    result = run_intcalc(
        [tcat(1, "01", 1, "0000010000{"), tcat(1, "01", 2, "0000010000{"), tcat(2, "01", 1, "0000010000{")],
        [acct(1), acct(2)], [xref("C1", 1), xref("C2", 2)],
        [disc("GOLD", "01", 1, "00150{"), disc("GOLD", "01", 2, "00000{")],
        "2022071800", lambda: NOW,
    )
    assert [t[:16] for t in result.transactions] == [b"2022071800000001", b"2022071800000002"]
    assert [t[262:278] for t in result.transactions] == [b"C1              ", b"C2              "]
    assert result.transactions[0][278:330] == b"2022-07-18-13.05.09.870000" * 2


def test_last_account_is_not_rewritten():
    """Reproduces CBACT04C: 1050-UPDATE-ACCOUNT is unreachable at EOF."""
    accounts = [acct(1), acct(2)]
    result = run_intcalc(
        [tcat(1, "01", 1, "0000120000{"), tcat(2, "01", 1, "0000120000{")],
        accounts, [xref("C1", 1), xref("C2", 2)], [disc("GOLD", "01", 1, "00100{")],
        "2022071800", lambda: NOW,
    )
    assert result.accounts[0][12:24] == b"00000011000{"     # 1000.00 + 100.00
    assert result.accounts[0][78:102] == b"00000000000{" * 2
    assert result.accounts[1] == accounts[1]


def test_abend_carries_sysout():
    with pytest.raises(CobolAbend) as exc:
        run_intcalc([tcat(9, "01", 1, "0000010000{")], [acct(1)], [], [], "2022071800", lambda: NOW)
    assert exc.value.code == 999
    assert exc.value.sysout[-4:] == [
        "ACCOUNT NOT FOUND: 00000000009", "ERROR READING ACCOUNT FILE",
        "FILE STATUS IS: NNNN0023", "ABENDING PROGRAM",
    ]
