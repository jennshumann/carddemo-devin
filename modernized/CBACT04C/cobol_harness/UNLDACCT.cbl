      * Unloads the account KSDS in key order to a fixed-length
      * sequential file (RECFM=F, LRECL=300), like an IDCAMS REPRO.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. UNLDACCT.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT ACCT-KS ASSIGN TO ACCTFILE
                  ORGANIZATION IS INDEXED
                  ACCESS MODE IS SEQUENTIAL
                  RECORD KEY IS AK-ACCT-ID
                  FILE STATUS IS KS-STATUS.
           SELECT ACCT-OUT ASSIGN TO ACCTOUT
                  ORGANIZATION IS SEQUENTIAL
                  FILE STATUS IS OUT-STATUS.
       DATA DIVISION.
       FILE SECTION.
       FD  ACCT-KS.
       01  AK-REC.
           05 AK-ACCT-ID           PIC 9(11).
           05 AK-DATA              PIC X(289).
       FD  ACCT-OUT.
       01  OUT-REC                 PIC X(300).
       WORKING-STORAGE SECTION.
       01  KS-STATUS               PIC XX.
       01  OUT-STATUS              PIC XX.
       01  WS-EOF                  PIC X VALUE 'N'.
       PROCEDURE DIVISION.
           OPEN INPUT ACCT-KS OUTPUT ACCT-OUT
           IF KS-STATUS NOT = '00' OR OUT-STATUS NOT = '00'
              DISPLAY 'UNLDACCT OPEN FAILED ' KS-STATUS ' ' OUT-STATUS
              MOVE 8 TO RETURN-CODE
              STOP RUN
           END-IF
           PERFORM UNTIL WS-EOF = 'Y'
              READ ACCT-KS NEXT
                 AT END MOVE 'Y' TO WS-EOF
                 NOT AT END WRITE OUT-REC FROM AK-REC
              END-READ
           END-PERFORM
           CLOSE ACCT-KS ACCT-OUT
           STOP RUN.
