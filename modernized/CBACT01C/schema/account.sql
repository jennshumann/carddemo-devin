CREATE TABLE IF NOT EXISTS account (
    acct_id             BIGINT PRIMARY KEY CHECK (acct_id BETWEEN 0 AND 99999999999),
    active_status       CHAR(1)        NOT NULL,
    curr_bal            NUMERIC(12, 2) NOT NULL,
    credit_limit        NUMERIC(12, 2) NOT NULL,
    cash_credit_limit   NUMERIC(12, 2) NOT NULL,
    open_date           CHAR(10)       NOT NULL,
    expiration_date     CHAR(10)       NOT NULL,
    reissue_date        CHAR(10)       NOT NULL,
    curr_cyc_credit     NUMERIC(12, 2) NOT NULL,
    curr_cyc_debit      NUMERIC(12, 2) NOT NULL,
    addr_zip            VARCHAR(10)    NOT NULL,
    group_id            VARCHAR(10)    NOT NULL
)
