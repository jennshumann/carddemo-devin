# CBACT04C / INTCALC business specification

Source of truth: `app/cbl/CBACT04C.cbl`, JCL `app/jcl/INTCALC.jcl`, copybooks `app/cpy/CVTRA01Y.cpy`, `CVACT03Y.cpy`, `CVTRA02Y.cpy`, `CVACT01Y.cpy`, `CVTRA05Y.cpy`, VSAM definitions in `app/jcl/XREFFILE.jcl`. Paragraph names below are from CBACT04C. Every rule here is checked by the golden files in `../golden/` (see [Baseline](#baseline-methodology)).

## Purpose

Monthly interest posting. For each transaction-category balance, the program looks up the account's annual rate for that transaction type and category, computes one month of interest, and writes a system-generated interest transaction. It then adds each account's total interest to its current balance and clears the account's cycle credit and debit. Paragraph `1400-COMPUTE-FEES` is an empty stub, so no fees are charged.

## JCL (INTCALC, one step)

`STEP15 EXEC PGM=CBACT04C,PARM='2022071800'`. The PARM reaches the program as `EXTERNAL-PARMS` (halfword `PARM-LENGTH` followed by `PARM-DATE PIC X(10)`). Only `PARM-DATE` is used, as the first 10 characters of each generated `TRAN-ID`. It is not checked as a date, and its length is not checked either: the Lambda takes the first 10 bytes and space-pads a shorter (or empty) value.

## Files

| DD | Dataset | COBOL file / access | Copybook (record) | Key |
|---|---|---|---|---|
| `TCATBALF` | `TCATBALF.VSAM.KSDS` | indexed, sequential read | `CVTRA01Y` `TRAN-CAT-BAL-RECORD` (50) | `TRANCAT-ACCT-ID` 9(11) + `TRANCAT-TYPE-CD` X(2) + `TRANCAT-CD` 9(4) |
| `XREFFILE` / `XREFFIL1` | `CARDXREF.VSAM.KSDS` + `.AIX.PATH` | indexed, random read by alternate key | `CVACT03Y` `CARD-XREF-RECORD` (50) | primary `XREF-CARD-NUM`; AIX `XREF-ACCT-ID` (NONUNIQUEKEY) |
| `ACCTFILE` | `ACCTDATA.VSAM.KSDS` | indexed, random, opened I-O (READ and REWRITE) | `CVACT01Y` `ACCOUNT-RECORD` (300) | `ACCT-ID` 9(11) |
| `DISCGRP` | `DISCGRP.VSAM.KSDS` | indexed, random read | `CVTRA02Y` `DIS-GROUP-RECORD` (50) | `DIS-ACCT-GROUP-ID` X(10) + `DIS-TRAN-TYPE-CD` X(2) + `DIS-TRAN-CAT-CD` 9(4) |
| `TRANSACT` | `SYSTRAN(+1)` (new GDG generation, `DISP=(NEW,CATLG,DELETE)`) | sequential output, RECFM=F LRECL=350 | `CVTRA05Y` `TRAN-RECORD` (350) | none |

Fields used:

| Copybook | Field | Picture | Bytes (0-based) | Use |
|---|---|---|---|---|
| CVTRA01Y | `TRAN-CAT-BAL` | S9(09)V99 zoned | 17-27 | balance the interest is computed on |
| CVACT01Y | `ACCT-CURR-BAL` | S9(10)V99 zoned | 12-23 | += total interest |
| CVACT01Y | `ACCT-CURR-CYC-CREDIT` / `-DEBIT` | S9(10)V99 zoned | 78-89 / 90-101 | set to 0 |
| CVACT01Y | `ACCT-GROUP-ID` | X(10) | 112-121 | disclosure group lookup |
| CVACT03Y | `XREF-CARD-NUM` | X(16) | 0-15 | copied to `TRAN-CARD-NUM` |
| CVTRA02Y | `DIS-INT-RATE` | S9(04)V99 zoned | 16-21 | annual rate in percent |

## Processing rules

- **R1 Order.** `TCATBALF` is read in key order (account, then type, then category). One SYSOUT line per record: `DISPLAY TRAN-CAT-BAL-RECORD` (the raw 50 bytes).
- **R2 Account break.** When `TRANCAT-ACCT-ID` differs from the previous record's (`WS-LAST-ACCT-NUM`, initially spaces):
  1. If this is not the first account, rewrite the previous account (R7).
  2. Reset `WS-TOTAL-INT` to 0.
  3. Read `ACCTFILE` by `ACCT-ID` (`1100-GET-ACCT-DATA`). Not found: abend (R9).
  4. Read `XREFFILE` by alternate key `XREF-ACCT-ID` (`1110-GET-XREF-DATA`) to get the card number. Not found: abend (R9).
- **R3 Rate lookup** (`1200-GET-INTEREST-RATE`), for every category record. The key is `ACCT-GROUP-ID` + `TRANCAT-TYPE-CD` + `TRANCAT-CD`. On status `23` (not found), SYSOUT gets `DISCLOSURE GROUP RECORD MISSING` and `TRY WITH DEFAULT GROUP CODE`, and the read is retried with group `DEFAULT` and the same type and category (`1200-A-GET-DEFAULT-INT-RATE`). If that fails too: abend (R9). The fallback is per category, so a group that exists but lacks a category also falls back.
- **R4 Zero rate.** If `DIS-INT-RATE = 0`, nothing else happens for that record: no transaction and no interest.
- **R5 Interest** (`1300-COMPUTE-INTEREST`). `COMPUTE WS-MONTHLY-INT = (TRAN-CAT-BAL * DIS-INT-RATE) / 1200`, with `WS-MONTHLY-INT PIC S9(09)V99`:
  - There is no `ROUNDED`, so the result is **truncated toward zero** to 2 decimals (for example 19.5364 → 19.53 and -1.250125 → -1.25).
  - There is no `ON SIZE ERROR`, so a result over 9 integer digits **loses its high-order digits** (8,333,324,999.91 → 333,324,999.91).
  - A negative result that truncates to zero is stored as +0.
  - `ADD WS-MONTHLY-INT TO WS-TOTAL-INT` uses the same S9(09)V99 truncation.
  - A non-zero rate always produces a transaction, even when the interest is 0.00 (for example a zero balance).
- **R6 Transaction** (`1300-B-WRITE-TX`). One 350-byte `TRAN-RECORD` per non-zero rate:

  | Field | Value |
  |---|---|
  | `TRAN-ID` X(16) | `PARM-DATE` (10 bytes) + `WS-TRANID-SUFFIX` 9(6). The suffix starts at 000001 and runs across the whole run, not per account. |
  | `TRAN-TYPE-CD` X(2) | `01` |
  | `TRAN-CAT-CD` 9(4) | `0005` (`MOVE '05'` into a 9(4) field) |
  | `TRAN-SOURCE` X(10) | `System` padded with spaces |
  | `TRAN-DESC` X(100) | `Int. for a/c ` + `ACCT-ID` (24 bytes) followed by spaces. `STRING` does not pad, so the rest is the field's initial content, which is spaces. |
  | `TRAN-AMT` S9(09)V99 | `WS-MONTHLY-INT` |
  | `TRAN-MERCHANT-ID` 9(9) | 0 |
  | `TRAN-MERCHANT-NAME` / `-CITY` / `-ZIP` | spaces |
  | `TRAN-CARD-NUM` X(16) | `XREF-CARD-NUM` |
  | `TRAN-ORIG-TS`, `TRAN-PROC-TS` X(26) | Current local time as `YYYY-MM-DD-HH.MM.SS.hh0000` (hundredths, then `0000`). Both fields hold the same value, taken once per transaction. |
  | `FILLER` X(20) | never set (spaces) |
- **R7 Account rewrite** (`1050-UPDATE-ACCOUNT`):
  - `ADD WS-TOTAL-INT TO ACCT-CURR-BAL`, which drops high-order digits beyond S9(10)V99.
  - `ACCT-CURR-CYC-CREDIT = 0` and `ACCT-CURR-CYC-DEBIT = 0`.
  - `REWRITE` of the whole 300-byte record.
  - All three numeric fields are re-encoded with a standard sign, even when the total is 0. For example an unsigned `...0` becomes `...{`.
- **R8 Last account is never rewritten.** The main loop is `PERFORM UNTIL END-OF-FILE = 'Y'`, and its `ELSE PERFORM 1050-UPDATE-ACCOUNT` branch only runs when `END-OF-FILE` is not `'N'` at the top of an iteration. That can't happen, because the loop exits as soon as EOF is set. So the last account in `TCATBALF` gets its interest transactions, but its balance is not updated and its cycle fields are not cleared. The GnuCOBOL baseline confirms this (account `00000000015` in `golden/edge` keeps its old balance and cycle fields). **The Lambda reproduces it.** See [Open questions](#open-questions).
- **R9 Abends.** Each of the following ends with SYSOUT lines and then `CALL 'CEE3ABD'` with code 999:
  - account not found: `ACCOUNT NOT FOUND: <id>`, `ERROR READING ACCOUNT FILE`
  - XREF not found: `ACCOUNT NOT FOUND: <id>`, `ERROR READING XREF FILE`
  - DEFAULT disclosure group not found: `ERROR READING DEFAULT DISCLOSURE GROUP`

  Each is followed by `FILE STATUS IS: NNNN0023` and `ABENDING PROGRAM`. On z/OS the abend deletes the new `TRANSACT` generation, but any `REWRITE`s already done to `ACCTFILE` stay. Other I/O errors (open, close, write, non-23 statuses) also abend. They have no business meaning and no Lambda equivalent beyond an exception.
- **R10 Accounts not in TCATBALF** are untouched.

## Platform-dependent details (baseline = GnuCOBOL 3.1.2)

1. **Uninitialized `WORKING-STORAGE`.** `TRAN-DESC` beyond byte 24 and the `TRAN-RECORD` `FILLER` are never moved to. GnuCOBOL initializes them to spaces. On z/OS without `WSCLEAR`/`STORAGE(00)`, their content is not defined.
2. **Negative zero.** GnuCOBOL stores a zero arithmetic result with a positive sign. Not verified on z/OS.
3. **Character set.** Datasets are the ASCII extracts in `app/data/ASCII`, with EBCDIC-style overpunch signs (`{`, `A`-`I` positive; `}`, `J`-`R` negative). The harness compiles with `-fsign=EBCDIC` so these decode correctly. The EBCDIC encoding has not been compared.
4. **AIX duplicates.** CARDXREF's AIX is `NONUNIQUEKEY`, but CBACT04C's `SELECT` declares no `WITH DUPLICATES`, so GnuCOBOL cannot model duplicate account IDs. The sample data has none. On a duplicate the Lambda uses the first record in card-number order. That choice is unverified.

## Baseline methodology

`../cobol_harness/run_cobol.sh <input_dir> <golden_dir> [parm]`:

1. Compile the unmodified `app/cbl/CBACT04C.cbl` with `cobc -x -fsign=EBCDIC -I app/cpy`, together with two stand-ins:
   - `INTCALC.cbl`, a driver that builds the z/OS PARM area (halfword length + text) and `CALL`s CBACT04C, like `EXEC PGM=...,PARM=`.
   - `CEE3ABD.cbl`, a stand-in for the IBM LE abend service. It sets `RETURN-CODE` 999, which the shell sees as 231.
2. `LOADDATA.cbl` loads `tcatbal.txt`, `acctdata.txt`, `cardxref.txt`, and `discgrp.txt` into GnuCOBOL (BDB) indexed files with the same keys as CBACT04C's `SELECT`s, standing in for the KSDSs.
3. Run with the fixed PARM `2022071800` (the JCL value). Capture stdout as `SYSOUT.txt`, the exit status as `RC.txt`, and `TRANSACT` as `TRANSACT.dat` (only on RC 0, like `DISP=(NEW,CATLG,DELETE)`).
4. `UNLDACCT.cbl` unloads the updated account KSDS in key order to `ACCTFILE.dat` (RECFM=F, 300-byte records with no delimiters), like an IDCAMS REPRO.

Cases (inputs → `golden/<case>/`):

| Case | Inputs | What it covers |
|---|---|---|
| `sample` | `app/data/ASCII` | The repo's sample data: 50 accounts, one category each. All balances are 0 and every `ACCT-GROUP-ID` is blank, so every lookup falls back to DEFAULT. 50 zero-amount transactions; accounts unchanged. |
| `edge` | `tests/fixtures/edge` | Positive and negative balances and rates, truncation, a zero rate (no transaction), a 0.00 transaction, a missing group and a missing category falling back to DEFAULT, an account not in TCATBALF, overflow of `WS-MONTHLY-INT` and `ACCT-CURR-BAL`, an unsigned input balance, -0.000125 → +0, and R8 |
| `empty` | `tests/fixtures/empty` | Empty TCATBALF |
| `abend_acct` / `abend_xref` / `abend_discgrp` | `tests/fixtures/abend_*` | Each R9 path. The golden `ACCTFILE.dat` shows that the previous account was already rewritten before the abend. |

Only `TRAN-ORIG-TS` and `TRAN-PROC-TS` (bytes 278-329 of each transaction) depend on the clock. The parity tests mask exactly those 52 bytes and check that both runs match the `YYYY-MM-DD-HH.MM.SS.hh0000` format.

## Open questions

1. **R8 (last account never rewritten) contradicts the intended behavior** ("REWRITE on account break and EOF"). The migration keeps the COBOL behavior for parity. Fixing it would mean calling `update_account()` once after the loop in `run_intcalc`, plus regenerating the expected outputs from a corrected program.
2. **Blank `ACCT-GROUP-ID` in the sample data.** `A000000000` sits in `ACCT-ADDR-ZIP` (bytes 102-111), so every sample account uses the DEFAULT group. This was also noted for CBACT01C.
