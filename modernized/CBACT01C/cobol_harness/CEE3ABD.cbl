      * Stand-in for the IBM Language Environment abend service.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CEE3ABD.
       DATA DIVISION.
       LINKAGE SECTION.
       01  ABCODE                  PIC S9(9) BINARY.
       01  TIMING                  PIC S9(9) BINARY.
       PROCEDURE DIVISION USING ABCODE TIMING.
           DISPLAY 'CEE3ABD ABEND CODE ' ABCODE UPON SYSERR
           MOVE ABCODE TO RETURN-CODE
           STOP RUN.
