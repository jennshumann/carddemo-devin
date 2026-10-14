      * Loads the 300-byte ASCII account extract into a GnuCOBOL
      * indexed file, standing in for the ACCTDATA VSAM KSDS.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. LOADACCT.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT ACCT-IN ASSIGN TO ACCTIN
                  ORGANIZATION IS LINE SEQUENTIAL
                  FILE STATUS IS IN-STATUS.
           SELECT ACCT-KSDS ASSIGN TO ACCTFILE
                  ORGANIZATION IS INDEXED
                  ACCESS MODE IS RANDOM
                  RECORD KEY IS KS-ACCT-ID
                  FILE STATUS IS KS-STATUS.
       DATA DIVISION.
       FILE SECTION.
       FD  ACCT-IN.
       01  IN-REC                  PIC X(300).
       FD  ACCT-KSDS.
       01  KS-REC.
           05 KS-ACCT-ID           PIC 9(11).
           05 KS-ACCT-DATA         PIC X(289).
       WORKING-STORAGE SECTION.
       01  IN-STATUS               PIC XX.
       01  KS-STATUS               PIC XX.
       01  WS-EOF                  PIC X VALUE 'N'.
       01  WS-COUNT                PIC 9(7) VALUE 0.
       PROCEDURE DIVISION.
           OPEN INPUT ACCT-IN
           OPEN OUTPUT ACCT-KSDS
           IF IN-STATUS NOT = '00' OR KS-STATUS NOT = '00'
              DISPLAY 'LOADACCT OPEN FAILED ' IN-STATUS ' ' KS-STATUS
              MOVE 8 TO RETURN-CODE
              STOP RUN
           END-IF
           PERFORM UNTIL WS-EOF = 'Y'
              READ ACCT-IN
                 AT END MOVE 'Y' TO WS-EOF
                 NOT AT END
                    MOVE IN-REC TO KS-REC
                    WRITE KS-REC
                       INVALID KEY
                          DISPLAY 'LOADACCT WRITE FAILED ' KS-STATUS
                          MOVE 8 TO RETURN-CODE
                          STOP RUN
                    END-WRITE
                    ADD 1 TO WS-COUNT
              END-READ
           END-PERFORM
           CLOSE ACCT-IN ACCT-KSDS
           DISPLAY 'LOADACCT RECORDS LOADED: ' WS-COUNT
           STOP RUN.
