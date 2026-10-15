"""Pure business logic for CBACT04C (INTCALC interest calculator).

Works on raw fixed-width records laid out exactly as the COBOL copybooks
(CVTRA01Y, CVACT01Y, CVACT03Y, CVTRA02Y, CVTRA05Y) so output bytes match
the original program. No AWS I/O here. Paragraph names refer to
app/cbl/CBACT04C.cbl.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

PROGRAM = "CBACT04C"
ABEND_CODE = 999

TCATBAL_RECORD_LEN = 50   # CVTRA01Y
ACCOUNT_RECORD_LEN = 300  # CVACT01Y
XREF_RECORD_LEN = 50      # CVACT03Y
DISCGRP_RECORD_LEN = 50   # CVTRA02Y
TRAN_RECORD_LEN = 350     # CVTRA05Y

# CVACT01Y offsets
ACCT_ID = slice(0, 11)
ACCT_CURR_BAL = slice(12, 24)
ACCT_CURR_CYC_CREDIT = slice(78, 90)
ACCT_CURR_CYC_DEBIT = slice(90, 102)
ACCT_GROUP_ID = slice(112, 122)
# CVTRA01Y offsets
TRANCAT_KEY = slice(0, 17)
TRANCAT_ACCT_ID = slice(0, 11)
TRANCAT_TYPE_CD = slice(11, 13)
TRANCAT_CD = slice(13, 17)
TRAN_CAT_BAL = slice(17, 28)
# CVACT03Y offsets
XREF_CARD_NUM = slice(0, 16)
XREF_ACCT_ID = slice(25, 36)
# CVTRA02Y offsets
DIS_GROUP_KEY = slice(0, 16)
DIS_INT_RATE = slice(16, 22)
# CVTRA05Y offsets of the wall-clock fields (TRAN-ORIG-TS, TRAN-PROC-TS)
TRAN_ORIG_TS = slice(278, 304)
TRAN_PROC_TS = slice(304, 330)

DEFAULT_GROUP = b"DEFAULT   "

_POS_OVERPUNCH = "{ABCDEFGHI"
_NEG_OVERPUNCH = "}JKLMNOPQR"


class CobolAbend(Exception):
    """The COBOL program would CALL 'CEE3ABD' (9999-ABEND-PROGRAM)."""

    def __init__(self, sysout: list[str], code: int = ABEND_CODE):
        super().__init__(f"{PROGRAM} abend {code}: {sysout[-4:]}")
        self.sysout = sysout
        self.code = code


def decode_zoned(data: bytes) -> int:
    """Signed zoned decimal (trailing overpunch sign) to integer units."""
    text = data.decode("ascii")
    last = text[-1]
    if last in _POS_OVERPUNCH:
        return int(text[:-1] + str(_POS_OVERPUNCH.index(last)))
    if last in _NEG_OVERPUNCH:
        return -int(text[:-1] + str(_NEG_OVERPUNCH.index(last)))
    return int(text)


def encode_zoned(units: int, digits: int) -> bytes:
    """Integer units to PIC S9(n) zoned decimal with overpunch sign.

    Keeps only the low-order `digits` digits, which is what a COBOL
    receiving field does on overflow without ON SIZE ERROR. A zero
    result is always stored with a positive sign (GnuCOBOL baseline).
    """
    text = f"{abs(units) % 10 ** digits:0{digits}d}"
    table = _NEG_OVERPUNCH if units < 0 and int(text) != 0 else _POS_OVERPUNCH
    return (text[:-1] + table[int(text[-1])]).encode("ascii")


def fit(units: int, digits: int) -> int:
    """Store into PIC S9(n): drop high-order digits, keep the sign."""
    kept = abs(units) % 10 ** digits
    return -kept if units < 0 else kept


def monthly_interest(tran_cat_bal: int, dis_int_rate: int) -> int:
    """1300-COMPUTE-INTEREST: (TRAN-CAT-BAL * DIS-INT-RATE) / 1200.

    Inputs and result are in hundredths (V99). COMPUTE has no ROUNDED,
    so the quotient is truncated toward zero, then fitted to S9(09)V99.
    """
    product = tran_cat_bal * dis_int_rate          # scale 4
    quotient = abs(product) // 120000              # /1200, back to scale 2
    return fit(-quotient if product < 0 else quotient, 11)


def db2_timestamp(now: datetime) -> bytes:
    """Z-GET-DB2-FORMAT-TIMESTAMP: YYYY-MM-DD-HH.MM.SS.hh0000."""
    return (now.strftime("%Y-%m-%d-%H.%M.%S") + f".{now.microsecond // 10000:02d}0000").encode("ascii")


def parse_records(data: bytes, length: int, fmt: str = "line") -> list[bytes]:
    """Split a dataset into fixed-length records.

    fmt="line": line-sequential text (LF or CRLF, last LF optional). Short lines
    are space-padded, as a GnuCOBOL LINE SEQUENTIAL read does.
    fmt="fixed": RECFM=F, e.g. this program's output. Split strictly by size,
    so LF bytes inside a record are just data.
    """
    if fmt == "fixed":
        if len(data) % length:
            raise ValueError(f"fixed-length file size {len(data)} is not a multiple of {length}")
        return [data[i:i + length] for i in range(0, len(data), length)]
    if fmt != "line":
        raise ValueError(f"unknown record format {fmt!r} (expected 'line' or 'fixed')")
    records = []
    for line in data.split(b"\n"):
        line = line.removesuffix(b"\r")
        if line:
            records.append(line.ljust(length)[:length])
    return records


def _index(records: list[bytes], key: slice, name: str) -> dict[bytes, bytes]:
    """Model a VSAM KSDS: unique primary key."""
    index: dict[bytes, bytes] = {}
    for rec in records:
        k = rec[key]
        if k in index:
            raise ValueError(f"duplicate key {k!r} in {name}")
        index[k] = rec
    return index


def normalize_parm(parm: str) -> bytes:
    """EXEC PARM text as PARM-DATE PIC X(10): first 10 bytes, space-padded.

    CBACT04C never checks the PARM length, so empty or longer values are accepted.
    """
    return parm.encode("ascii")[:10].ljust(10)


@dataclass
class IntcalcResult:
    transactions: list[bytes] = field(default_factory=list)
    accounts: list[bytes] = field(default_factory=list)
    sysout: list[str] = field(default_factory=list)
    records_read: int = 0


def run_intcalc(
    tcatbal: list[bytes],
    accounts: list[bytes],
    xrefs: list[bytes],
    discgrps: list[bytes],
    parm: str,
    now: Callable[[], datetime] = datetime.now,
) -> IntcalcResult:
    """Run CBACT04C over in-memory datasets.

    Returns the TRANSACT records and the full ACCTFILE in key order after
    all REWRITEs. Raises CobolAbend where the COBOL would abend.
    """
    parm_date = normalize_parm(parm)
    tcat_ksds = _index(tcatbal, TRANCAT_KEY, "TCATBALF")
    acct_ksds = {k: bytearray(v) for k, v in _index(accounts, ACCT_ID, "ACCTFILE").items()}
    xref_ksds = _index(xrefs, XREF_CARD_NUM, "XREFFILE")
    disc_ksds = _index(discgrps, DIS_GROUP_KEY, "DISCGRP")
    # CARDXREF AIX path (NONUNIQUEKEY): first record in primary-key order.
    xref_by_acct: dict[bytes, bytes] = {}
    for card in sorted(xref_ksds):
        xref_by_acct.setdefault(xref_ksds[card][XREF_ACCT_ID], xref_ksds[card])

    result = IntcalcResult()
    sysout = result.sysout
    sysout.append(f"START OF EXECUTION OF PROGRAM {PROGRAM}")

    def abend(message: str) -> None:
        sysout.extend([message, "FILE STATUS IS: NNNN0023", "ABENDING PROGRAM"])
        raise CobolAbend(sysout)

    account: bytearray | None = None
    card_num = b""
    last_acct_num = b" " * 11
    first_time = True
    total_int = 0
    tranid_suffix = 0

    def update_account() -> None:  # 1050-UPDATE-ACCOUNT
        bal = fit(decode_zoned(account[ACCT_CURR_BAL]) + total_int, 12)
        account[ACCT_CURR_BAL] = encode_zoned(bal, 12)
        account[ACCT_CURR_CYC_CREDIT] = encode_zoned(0, 12)
        account[ACCT_CURR_CYC_DEBIT] = encode_zoned(0, 12)
        acct_ksds[bytes(account[ACCT_ID])] = bytearray(account)

    for key in sorted(tcat_ksds):  # 1000-TCATBALF-GET-NEXT (key order)
        rec = tcat_ksds[key]
        result.records_read += 1
        sysout.append(rec.decode("latin-1"))
        acct_id = rec[TRANCAT_ACCT_ID]
        if acct_id != last_acct_num:
            if not first_time:
                update_account()
            else:
                first_time = False
            total_int = 0
            last_acct_num = acct_id
            if acct_id not in acct_ksds:  # 1100-GET-ACCT-DATA
                sysout.append(f"ACCOUNT NOT FOUND: {acct_id.decode('ascii')}")
                abend("ERROR READING ACCOUNT FILE")
            account = bytearray(acct_ksds[acct_id])
            if acct_id not in xref_by_acct:  # 1110-GET-XREF-DATA
                sysout.append(f"ACCOUNT NOT FOUND: {acct_id.decode('ascii')}")
                abend("ERROR READING XREF FILE")
            card_num = xref_by_acct[acct_id][XREF_CARD_NUM]

        type_cat = rec[TRANCAT_TYPE_CD] + rec[TRANCAT_CD]
        disc = disc_ksds.get(bytes(account[ACCT_GROUP_ID]) + type_cat)  # 1200-GET-INTEREST-RATE
        if disc is None:
            sysout.extend(["DISCLOSURE GROUP RECORD MISSING", "TRY WITH DEFAULT GROUP CODE"])
            disc = disc_ksds.get(DEFAULT_GROUP + type_cat)  # 1200-A-GET-DEFAULT-INT-RATE
            if disc is None:
                abend("ERROR READING DEFAULT DISCLOSURE GROUP")
        rate = decode_zoned(disc[DIS_INT_RATE])
        if rate != 0:
            interest = monthly_interest(decode_zoned(rec[TRAN_CAT_BAL]), rate)
            total_int = fit(total_int + interest, 11)
            tranid_suffix = (tranid_suffix + 1) % 10 ** 6
            result.transactions.append(
                _interest_transaction(parm_date, tranid_suffix, acct_id, interest, card_num, now())
            )
    # At EOF the loop exits before its ELSE branch can PERFORM
    # 1050-UPDATE-ACCOUNT, so the last account is never rewritten.
    sysout.append(f"END OF EXECUTION OF PROGRAM {PROGRAM}")
    result.accounts = [bytes(acct_ksds[k]) for k in sorted(acct_ksds)]
    return result


def _interest_transaction(
    parm_date: bytes, suffix: int, acct_id: bytes, amount: int, card_num: bytes, now: datetime
) -> bytes:
    """1300-B-WRITE-TX: one CVTRA05Y TRAN-RECORD."""
    ts = db2_timestamp(now)
    rec = (
        parm_date + f"{suffix:06d}".encode("ascii")   # TRAN-ID
        + b"01"                                        # TRAN-TYPE-CD
        + b"0005"                                      # TRAN-CAT-CD
        + b"System".ljust(10)                          # TRAN-SOURCE
        + (b"Int. for a/c " + acct_id).ljust(100)      # TRAN-DESC
        + encode_zoned(amount, 11)                     # TRAN-AMT
        + b"0" * 9                                     # TRAN-MERCHANT-ID
        + b" " * 50 + b" " * 50 + b" " * 10            # MERCHANT NAME/CITY/ZIP
        + card_num                                     # TRAN-CARD-NUM
        + ts + ts                                      # TRAN-ORIG-TS, TRAN-PROC-TS
        + b" " * 20                                    # FILLER
    )
    assert len(rec) == TRAN_RECORD_LEN
    return rec

