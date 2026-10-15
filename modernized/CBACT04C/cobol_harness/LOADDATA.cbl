      * Loads the four ASCII line-sequential extracts used by INTCALC
      * into GnuCOBOL indexed files, standing in for the VSAM KSDSs
      * (and the CARDXREF AIX path). Key definitions match CBACT04C.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. LOADDATA.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT TCAT-IN ASSIGN TO TCATIN
                  ORGANIZATION IS LINE SEQUENTIAL
                  FILE STATUS IS IN-STATUS.
           SELECT ACCT-IN ASSIGN TO ACCTIN
                  ORGANIZATION IS LINE SEQUENTIAL
                  FILE STATUS IS IN-STATUS.
           SELECT XREF-IN ASSIGN TO XREFIN
                  ORGANIZATION IS LINE SEQUENTIAL
                  FILE STATUS IS IN-STATUS.
           SELECT DISC-IN ASSIGN TO DISCIN
                  ORGANIZATION IS LINE SEQUENTIAL
                  FILE STATUS IS IN-STATUS.
           SELECT TCAT-KS ASSIGN TO TCATBALF
                  ORGANIZATION IS INDEXED
                  ACCESS MODE IS RANDOM
                  RECORD KEY IS TK-KEY
                  FILE STATUS IS KS-STATUS.
           SELECT ACCT-KS ASSIGN TO ACCTFILE
                  ORGANIZATION IS INDEXED
                  ACCESS MODE IS RANDOM
                  RECORD KEY IS AK-ACCT-ID
                  FILE STATUS IS KS-STATUS.
           SELECT XREF-KS ASSIGN TO XREFFILE
                  ORGANIZATION IS INDEXED
                  ACCESS MODE IS RANDOM
                  RECORD KEY IS XK-CARD-NUM
                  ALTERNATE RECORD KEY IS XK-ACCT-ID
                  FILE STATUS IS KS-STATUS.
           SELECT DISC-KS ASSIGN TO DISCGRP
                  ORGANIZATION IS INDEXED
                  ACCESS MODE IS RANDOM
                  RECORD KEY IS DK-KEY
                  FILE STATUS IS KS-STATUS.
       DATA DIVISION.
       FILE SECTION.
       FD  TCAT-IN.
       01  TCAT-IN-REC             PIC X(50).
       FD  ACCT-IN.
       01  ACCT-IN-REC             PIC X(300).
       FD  XREF-IN.
       01  XREF-IN-REC             PIC X(50).
       FD  DISC-IN.
       01  DISC-IN-REC             PIC X(50).
       FD  TCAT-KS.
       01  TK-REC.
           05 TK-KEY               PIC X(17).
           05 TK-DATA              PIC X(33).
       FD  ACCT-KS.
       01  AK-REC.
           05 AK-ACCT-ID           PIC 9(11).
           05 AK-DATA              PIC X(289).
       FD  XREF-KS.
       01  XK-REC.
           05 XK-CARD-NUM          PIC X(16).
           05 XK-CUST-NUM          PIC 9(09).
           05 XK-ACCT-ID           PIC 9(11).
           05 XK-FILLER            PIC X(14).
       FD  DISC-KS.
       01  DK-REC.
           05 DK-KEY               PIC X(16).
           05 DK-DATA              PIC X(34).
       WORKING-STORAGE SECTION.
       01  IN-STATUS               PIC XX.
       01  KS-STATUS               PIC XX.
       01  WS-EOF                  PIC X.
       01  WS-COUNT                PIC 9(7).
       PROCEDURE DIVISION.
           MOVE 'N' TO WS-EOF  MOVE 0 TO WS-COUNT
           OPEN INPUT TCAT-IN  OPEN OUTPUT TCAT-KS
           PERFORM CHECK-OPEN
           PERFORM UNTIL WS-EOF = 'Y'
              READ TCAT-IN AT END MOVE 'Y' TO WS-EOF
              NOT AT END
                 MOVE TCAT-IN-REC TO TK-REC
                 WRITE TK-REC INVALID KEY PERFORM WRITE-FAILED
                 END-WRITE
                 ADD 1 TO WS-COUNT
              END-READ
           END-PERFORM
           CLOSE TCAT-IN TCAT-KS
           DISPLAY 'LOADDATA TCATBALF RECORDS: ' WS-COUNT

           MOVE 'N' TO WS-EOF  MOVE 0 TO WS-COUNT
           OPEN INPUT ACCT-IN  OPEN OUTPUT ACCT-KS
           PERFORM CHECK-OPEN
           PERFORM UNTIL WS-EOF = 'Y'
              READ ACCT-IN AT END MOVE 'Y' TO WS-EOF
              NOT AT END
                 MOVE ACCT-IN-REC TO AK-REC
                 WRITE AK-REC INVALID KEY PERFORM WRITE-FAILED
                 END-WRITE
                 ADD 1 TO WS-COUNT
              END-READ
           END-PERFORM
           CLOSE ACCT-IN ACCT-KS
           DISPLAY 'LOADDATA ACCTFILE RECORDS: ' WS-COUNT

           MOVE 'N' TO WS-EOF  MOVE 0 TO WS-COUNT
           OPEN INPUT XREF-IN  OPEN OUTPUT XREF-KS
           PERFORM CHECK-OPEN
           PERFORM UNTIL WS-EOF = 'Y'
              READ XREF-IN AT END MOVE 'Y' TO WS-EOF
              NOT AT END
                 MOVE XREF-IN-REC TO XK-REC
                 WRITE XK-REC INVALID KEY PERFORM WRITE-FAILED
                 END-WRITE
                 ADD 1 TO WS-COUNT
              END-READ
           END-PERFORM
           CLOSE XREF-IN XREF-KS
           DISPLAY 'LOADDATA XREFFILE RECORDS: ' WS-COUNT

           MOVE 'N' TO WS-EOF  MOVE 0 TO WS-COUNT
           OPEN INPUT DISC-IN  OPEN OUTPUT DISC-KS
           PERFORM CHECK-OPEN
           PERFORM UNTIL WS-EOF = 'Y'
              READ DISC-IN AT END MOVE 'Y' TO WS-EOF
              NOT AT END
                 MOVE DISC-IN-REC TO DK-REC
                 WRITE DK-REC INVALID KEY PERFORM WRITE-FAILED
                 END-WRITE
                 ADD 1 TO WS-COUNT
              END-READ
           END-PERFORM
           CLOSE DISC-IN DISC-KS
           DISPLAY 'LOADDATA DISCGRP RECORDS: ' WS-COUNT
           STOP RUN.

       CHECK-OPEN.
           IF IN-STATUS NOT = '00' OR KS-STATUS NOT = '00'
              DISPLAY 'LOADDATA OPEN FAILED ' IN-STATUS ' ' KS-STATUS
              MOVE 8 TO RETURN-CODE
              STOP RUN
           END-IF.

       WRITE-FAILED.
           DISPLAY 'LOADDATA WRITE FAILED ' KS-STATUS
           MOVE 8 TO RETURN-CODE
           STOP RUN.
