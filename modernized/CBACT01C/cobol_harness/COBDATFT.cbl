      * Stand-in for app/asm/COBDATFT.asm (HLASM) so CBACT01C can run
      * under GnuCOBOL. Mirrors the assembler logic byte for byte.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. COBDATFT.
       DATA DIVISION.
       LINKAGE SECTION.
       COPY CODATECN.
       PROCEDURE DIVISION USING CODATECN-REC.
           EVALUATE CODATECN-TYPE
             WHEN '1'
               IF CODATECN-INP-DATE(5:1) = '-'
                  OR CODATECN-OUTTYPE = '2'
                  MOVE 'INVALID INPUT' TO CODATECN-ERROR-MSG
               ELSE
                  MOVE CODATECN-INP-DATE(1:4) TO CODATECN-0UT-DATE(1:4)
                  MOVE '-'                    TO CODATECN-0UT-DATE(5:1)
                  MOVE CODATECN-INP-DATE(5:2) TO CODATECN-0UT-DATE(6:2)
                  MOVE '-'                    TO CODATECN-0UT-DATE(8:1)
                  MOVE CODATECN-INP-DATE(7:2) TO CODATECN-0UT-DATE(9:2)
               END-IF
             WHEN '2'
               IF CODATECN-OUTTYPE = '1'
                  MOVE 'INVALID INPUT' TO CODATECN-ERROR-MSG
               ELSE
                  MOVE CODATECN-INP-DATE(1:4) TO CODATECN-0UT-DATE(1:4)
                  MOVE CODATECN-INP-DATE(6:2) TO CODATECN-0UT-DATE(5:2)
                  MOVE CODATECN-INP-DATE(9:2) TO CODATECN-0UT-DATE(7:2)
               END-IF
             WHEN OTHER
               MOVE 'INVALID INPUT' TO CODATECN-ERROR-MSG
           END-EVALUATE
           GOBACK.
