-- Snowflake compatibility shims for the DuckDB sandbox.
--
-- These cover scalar functions whose semantics are identical but whose names
-- differ. Parser-level Snowflake syntax (LATERAL FLATTEN, colon paths,
-- OBJECT_CONSTRUCT) cannot be shimmed and is rejected by
-- domain.sql_portability instead, in every environment.

CREATE OR REPLACE MACRO iff(condition, when_true, when_false) AS
    CASE WHEN condition THEN when_true ELSE when_false END;

CREATE OR REPLACE MACRO nvl(value, fallback) AS coalesce(value, fallback);

CREATE OR REPLACE MACRO nvl2(value, when_present, when_null) AS
    CASE WHEN value IS NOT NULL THEN when_present ELSE when_null END;

CREATE OR REPLACE MACRO zeroifnull(value) AS coalesce(value, 0);

CREATE OR REPLACE MACRO nullifzero(value) AS nullif(value, 0);

CREATE OR REPLACE MACRO charindex(needle, haystack) AS position(needle IN haystack);

CREATE OR REPLACE MACRO to_varchar(value) AS CAST(value AS VARCHAR);

CREATE OR REPLACE MACRO to_number(value) AS CAST(value AS DECIMAL(38, 0));

CREATE OR REPLACE MACRO is_null_value(value) AS value IS NULL;
