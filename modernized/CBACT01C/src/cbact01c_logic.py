"""Pure business logic for CBACT01C (account file extract).

Operates on raw fixed-width records exactly as laid out by the COBOL
copybooks, so output bytes match the original program. No AWS I/O here.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

ACCOUNT_RECORD_LEN = 300
OUT_RECORD_LEN = 107
ARRAY_RECORD_LEN = 110

_POS_OVERPUNCH = "{ABCDEFGHI"
_NEG_OVERPUNCH = "}JKLMNOPQR"

# Initial content of the OUT-ACCT-CURR-CYC-DEBIT bytes before any MOVE.
# GnuCOBOL leaves the FD record area as low-values.
UNSET_PACKED_DEBIT = b"\x00" * 7


def decode_zoned(field: bytes, scale: int = 2) -> Decimal:
    """Decode a signed zoned-decimal field with trailing overpunch sign."""
    text = field.decode("ascii")
    last = text[-1]
    if last in _POS_OVERPUNCH:
        digits, negative = text[:-1] + str(_POS_OVERPUNCH.index(last)), False
    elif last in _NEG_OVERPUNCH:
        digits, negative = text[:-1] + str(_NEG_OVERPUNCH.index(last)), True
    else:
        digits, negative = text, False
    value = Decimal(int(digits)).scaleb(-scale)
    return -value if negative else value


def encode_zoned(value: Decimal, digits: int = 12, scale: int = 2) -> bytes:
    """Encode as PIC S9(digits-scale)V9(scale) with trailing overpunch sign."""
    units = int(abs(value).scaleb(scale))
    text = f"{units:0{digits}d}"[-digits:]
    table = _NEG_OVERPUNCH if value < 0 else _POS_OVERPUNCH
    return (text[:-1] + table[int(text[-1])]).encode("ascii")


def encode_packed(value: Decimal, digits: int = 12, scale: int = 2) -> bytes:
    """Encode as PIC S9(digits-scale)V9(scale) COMP-3."""
    units = int(abs(value).scaleb(scale))
    nibbles = f"{units:0{digits}d}"[-digits:] + ("d" if value < 0 else "c")
    if len(nibbles) % 2:
        nibbles = "0" + nibbles
    return bytes.fromhex(nibbles)


@dataclass(frozen=True)
class Account:
    """View over a CVACT01Y ACCOUNT-RECORD (300 bytes)."""

    raw: bytes

    @property
    def acct_id(self) -> bytes: return self.raw[0:11]
    @property
    def active_status(self) -> bytes: return self.raw[11:12]
    @property
    def curr_bal(self) -> bytes: return self.raw[12:24]
    @property
    def credit_limit(self) -> bytes: return self.raw[24:36]
    @property
    def cash_credit_limit(self) -> bytes: return self.raw[36:48]
    @property
    def open_date(self) -> bytes: return self.raw[48:58]
    @property
    def expiration_date(self) -> bytes: return self.raw[58:68]
    @property
    def reissue_date(self) -> bytes: return self.raw[68:78]
    @property
    def curr_cyc_credit(self) -> bytes: return self.raw[78:90]
    @property
    def curr_cyc_debit(self) -> bytes: return self.raw[90:102]
    @property
    def group_id(self) -> bytes: return self.raw[112:122]


@dataclass
class ExtractResult:
    out_records: list[bytes]
    array_records: list[bytes]
    vb_records: list[bytes]


def cobdatft_type2_to_type2(date: bytes) -> bytes:
    """COBDATFT with input type '2' (YYYY-MM-DD) and output type '2'.

    Copies YYYY, MM, DD into the first 8 bytes of the 20-byte output
    field; the rest keeps its initial spaces. CBACT01C keeps 10 bytes.
    """
    return date[0:4] + date[5:7] + date[8:10] + b"  "


def parse_accounts(data: bytes) -> list[Account]:
    """Split a line-sequential extract into 300-byte account records."""
    accounts = []
    for line in data.splitlines():
        if not line:
            continue
        accounts.append(Account(line.ljust(ACCOUNT_RECORD_LEN)[:ACCOUNT_RECORD_LEN]))
    return accounts


def extract_accounts(accounts: list[Account]) -> ExtractResult:
    """Reproduce CBACT01C paragraphs 1000-1575 for every account."""
    result = ExtractResult([], [], [])
    # OUT-ACCT-CURR-CYC-DEBIT is only assigned when the input debit is zero,
    # so other records inherit the previous value (CBACT01C.cbl 236-238).
    packed_debit = UNSET_PACKED_DEBIT
    for acct in sorted(accounts, key=lambda a: a.acct_id):
        if decode_zoned(acct.curr_cyc_debit) == 0:
            packed_debit = encode_packed(Decimal("2525.00"))
        out = (
            acct.acct_id + acct.active_status + acct.curr_bal
            + acct.credit_limit + acct.cash_credit_limit + acct.open_date
            + acct.expiration_date + cobdatft_type2_to_type2(acct.reissue_date)
            + acct.curr_cyc_credit + packed_debit + acct.group_id
        )
        empty_slot = b"0" * 12 + encode_packed(Decimal(0))
        array = (
            acct.acct_id
            + acct.curr_bal + encode_packed(Decimal("1005.00"))
            + acct.curr_bal + encode_packed(Decimal("1525.00"))
            + encode_zoned(Decimal("-1025.00")) + encode_packed(Decimal("-2500.00"))
            + empty_slot * 2
            + b" " * 4
        )
        assert len(out) == OUT_RECORD_LEN and len(array) == ARRAY_RECORD_LEN
        result.out_records.append(out)
        result.array_records.append(array)
        result.vb_records.append(acct.acct_id + acct.active_status)
        result.vb_records.append(
            acct.acct_id + acct.curr_bal + acct.credit_limit + acct.reissue_date[0:4]
        )
    return result


def to_rdw(records: list[bytes]) -> bytes:
    """Serialize variable records with z/OS RDWs (length includes the RDW)."""
    return b"".join((len(r) + 4).to_bytes(2, "big") + b"\x00\x00" + r for r in records)


def from_gnucobol_varseq(data: bytes) -> list[bytes]:
    """Parse GnuCOBOL's default variable file format (length excludes header)."""
    records, pos = [], 0
    while pos < len(data):
        length = int.from_bytes(data[pos:pos + 2], "big")
        records.append(data[pos + 4:pos + 4 + length])
        pos += 4 + length
    return records


def from_rdw(data: bytes) -> list[bytes]:
    records, pos = [], 0
    while pos < len(data):
        length = int.from_bytes(data[pos:pos + 2], "big")
        records.append(data[pos + 4:pos + length])
        pos += length
    return records
