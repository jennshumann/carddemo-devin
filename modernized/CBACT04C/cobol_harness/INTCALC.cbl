      * Stands in for JCL step STEP15 (EXEC PGM=CBACT04C,PARM=...).
      * z/OS passes PARM as a halfword length followed by the text;
      * this driver builds the same area and CALLs CBACT04C with it.
      * Usage: intcalc <parm>
       IDENTIFICATION DIVISION.
       PROGRAM-ID. INTCALC.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-CMD-LINE             PIC X(100).
       01  EXTERNAL-PARMS.
           05  PARM-LENGTH         PIC S9(04) COMP.
           05  PARM-TEXT           PIC X(100).
       PROCEDURE DIVISION.
           ACCEPT WS-CMD-LINE FROM COMMAND-LINE
           MOVE WS-CMD-LINE TO PARM-TEXT
           MOVE FUNCTION LENGTH(FUNCTION TRIM(WS-CMD-LINE TRAILING))
             TO PARM-LENGTH
           CALL 'CBACT04C' USING EXTERNAL-PARMS
           STOP RUN.
