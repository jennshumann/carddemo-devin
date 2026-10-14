# CBACT01C analysis

Source of truth: `app/cbl/CBACT01C.cbl` (line numbers below refer to it), JCL `app/jcl/READACCT.jcl`, copybooks `app/cpy/CVACT01Y.cpy` and `app/cpy/CODATECN.cpy`, date routine `app/asm/COBDATFT.asm` and `app/maclib/COCDATFT.mac`.

## Purpose

Batch extract. It reads every account record from the account master (VSAM KSDS) in key order, prints each one to SYSOUT, and writes three sequential files that each show the account in a different record format: fixed-length with a COMP-3 field, fixed-length with an `OCCURS` array, and variable-length. The program changes no data. It works mostly as a demo of record formats, and several output values are hard-coded test constants (rules R5 and R6).

## Inputs

| DD | Dataset (JCL) | COBOL file | Layout |
|---|---|---|---|
| `ACCTFILE` | `AWS.M2.CARDDEMO.ACCTDATA.VSAM.KSDS` | `ACCTFILE-FILE`: indexed, sequential access, key `FD-ACCT-ID` (29-33) | 300 bytes, `CVACT01Y` `ACCOUNT-RECORD` |

## Outputs

| DD | Dataset (JCL) | Format | Layout (lines) |
|---|---|---|---|
| `OUTFILE` | `AWS.M2.CARDDEMO.ACCTDATA.PSCOMP` | RECFM=FB, LRECL=107 | `OUT-ACCT-REC` (57-70) |
| `ARRYFILE` | `AWS.M2.CARDDEMO.ACCTDATA.ARRYPS` | RECFM=FB, LRECL=110 | `ARR-ARRAY-REC` (72-78) |
| `VBRCFILE` | `AWS.M2.CARDDEMO.ACCTDATA.VBPS` | RECFM=VB, LRECL=84 | `VBRC-REC1` 12 bytes, `VBRC-REC2` 39 bytes (123-130) |
| SYSOUT | n/a | text | `DISPLAY` output (141, 151, 158, 200-213, 283-284) |

Before the program runs, JCL step `PREDEL` deletes the three output datasets. Then `STEP05` runs `PGM=CBACT01C`.

## Business rules

- **R1. Read order (147-154, 165-166).** Accounts are read sequentially from the KSDS, so they come in ascending `ACCT-ID` order. Every record with status `00` is processed. Status `10` (end of file) ends the loop (180-181, 189-190).
- **R2. Errors abend (182-183, 191-196, and every open/write/close paragraph 242-403).** Any other file status displays `ERROR ...`, then `FILE STATUS IS: NNNNxxxx` (9910), then `ABENDING PROGRAM`, and calls `CEE3ABD` with abend code 999 (9999-ABEND-PROGRAM, ~405-409).
- **R3. Display (200-213, 151).** For each account, it displays a labeled field dump (`1100-DISPLAY-ACCT-RECORD`), the two VB records (283-284), and the raw 300-byte record (151).
- **R4. OUTFILE record (215-241).** Fields copied unchanged: ID, active status, current balance, credit limit, cash credit limit, open date, expiration date, current-cycle credit, group ID. Two fields are derived:
  - **R4a. Reissue date reformat (222-230).** `ACCT-REISSUE-DATE` (`YYYY-MM-DD`) goes through `COBDATFT` with input type `2` and output type `2`. The routine writes `YYYYMMDD` to the first 8 bytes of the 20-byte output field and leaves the rest as spaces. The output is `YYYYMMDD` followed by 2 spaces. No validation is done. (See the open question about the type 2/2 combination.)
  - **R4b. Current-cycle debit (236-238).** If `ACCT-CURR-CYC-DEBIT = 0`, `OUT-ACCT-CURR-CYC-DEBIT` (COMP-3) is set to `+2525.00`. **There is no ELSE.** A non-zero input debit is never copied, so the field keeps the value from the previous record. On the first record, that previous value is uninitialized (low-values under GnuCOBOL).
  - `ACCT-ADDR-ZIP` and the 178-byte filler are not output.
- **R5. ARRYFILE record (169, 253-261).** The record is `INITIALIZE`d. Then:
  - slot 1: current balance, debit `+1005.00`
  - slot 2: current balance, debit `+1525.00`
  - slot 3: balance `-1025.00`, debit `-2500.00` (constants)
  - slots 4-5: zero. Each balance is unsigned zoned `000000000000` and each debit is COMP-3 `+0`.
  - filler: 4 spaces
- **R6. VBRCFILE records (175, 276-315).** Two records per account:
  - REC1 (length 12): ID + active status
  - REC2 (length 39): ID + current balance + credit limit + reissue year (first 4 bytes of `ACCT-REISSUE-DATE`)
- **R7. Close (156, 388-403).** Only `ACCTFILE` is closed explicitly. The three output files are never `CLOSE`d. The runtime (or LE at step end) closes them implicitly, and GnuCOBOL warns `implicit CLOSE of ...`.

## Running the original (playbook step 2)

**Result: succeeded. The golden files are real COBOL output, not hand-derived.**

How it was run (`cobol_harness/run_cobol.sh`, which writes only to a temp dir and `modernized/`):

1. `LOADACCT.cbl` loads `app/data/ASCII/acctdata.txt` (50 × 300 bytes, line sequential) into a GnuCOBOL indexed file (BDB), standing in for the VSAM KSDS.
2. `CBACT01C.cbl` is compiled unmodified from `app/cbl` with `cobc -x -fsign=EBCDIC -I app/cpy`. `-fsign=EBCDIC` makes the trailing overpunch characters in the ASCII extract (`{`, `A`-`I`, `}`, `J`-`R`) decode as signed zoned decimal, the same way they do on z/OS.
3. Two stand-ins replace routines that are not COBOL:
   - `COBDATFT.cbl` copies the HLASM logic of `app/asm/COBDATFT.asm` byte for byte.
   - `CEE3ABD.cbl` replaces the IBM LE abend service. GnuCOBOL has no `CEE3ABD`; without the stub, an abend becomes `module 'CEE3ABD' not found`.
4. `DD_ACCTFILE`, `DD_OUTFILE`, `DD_ARRYFILE`, and `DD_VBRCFILE` map the DDs to files.

Golden sets:
- `golden/`: the `app/data` sample (50 accounts). Every account in it has a zero cycle debit, a positive balance, status `Y`, and a blank group ID, so it covers only part of the rules.
- `golden/edge/`: `tests/fixtures/edge_accounts.txt`, 4 synthetic accounts run through the same original COBOL. They cover the gaps: a non-zero debit on the first record (R4b uninitialized), a non-zero debit after a zero one (R4b carry-forward), negative and negative-zero balances, status `N`, maximum-magnitude values, a populated group ID, and a leap-day reissue date.

## Discrepancies and limitations

1. **VB record framing.** GnuCOBOL writes each variable record with a 4-byte header holding the length *without* the header. z/OS RDWs include the 4 bytes. The Lambda writes z/OS-style RDWs. The parity test compares the logical records (length and content), not the header bytes.
2. **SYSOUT.** GnuCOBOL shows signed numerics as `+0000000194.00`; z/OS shows the zoned overpunch. SYSOUT is diagnostic, so the Lambda logs only start, count, and end lines. SYSOUT is checked only for record count.
3. **R4b first-record value.** Under GnuCOBOL the inherited debit is `X'00000000000000'`. On z/OS the FD buffer's initial content is not defined, so it may differ. The Lambda reproduces the GnuCOBOL bytes.
4. **Character set.** The golden files are ASCII (zoned digits `0x30`-`0x39`, overpunch letters). The EBCDIC encoding of these datasets on the mainframe has not been compared.

## Open questions

1. **R4b looks like a bug** (a missing `ELSE MOVE ACCT-CURR-CYC-DEBIT`). The migration keeps it for parity. Should a later change fix it?
2. **COBDATFT type 2 → type 2.** In the HLASM, type 2 input only rejects output type `1`, so 2/2 is allowed and produces `YYYYMMDD`, which is what the program uses. The copybook's 88-levels pair type 2 input with `YYYY-MM-DD-OP` = `1`, so the call doesn't match the copybook's intent. The behavior is kept as is.
3. **Group ID in the sample data.** In `acctdata.txt`, `A000000000` sits in the `ACCT-ADDR-ZIP` position (bytes 103-112) and `ACCT-GROUP-ID` (113-122) is blank, so every output group ID is blank. This could be a data-layout problem in the extract.
4. **Input source.** The Lambda reads the extract from `in/CBACT01C/` in S3, matching the COBOL file input. The `account` table is created in Aurora for other programs. Should a later step have CBACT01C read from Aurora instead?
