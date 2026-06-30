from agent.sql_guard import (
    format_sql_literal,
    prepare_readonly_sqls,
    replace_sql_variables,
)


def assert_raises(sql: str):
    try:
        prepare_readonly_sqls(sql)
    except Exception:
        return
    raise AssertionError(f"Expected SQL to be blocked: {sql}")


def test_prepare_readonly_sqls_allows_single_select():
    assert prepare_readonly_sqls("SELECT * FROM orders WHERE amount > 10;") == [
        "SELECT * FROM orders WHERE amount > 10"
    ]


def test_prepare_readonly_sqls_allows_with_query():
    assert prepare_readonly_sqls("WITH x AS (SELECT 1 AS a) SELECT * FROM x")


def test_prepare_readonly_sqls_blocks_write_statements():
    for sql in ["UPDATE t SET a=1", "DROP TABLE t", "INSERT INTO t VALUES (1)"]:
        assert_raises(sql)


def test_prepare_readonly_sqls_blocks_multiple_statements():
    assert_raises("SELECT * FROM t; DELETE FROM t")


def test_prepare_readonly_sqls_ignores_keywords_inside_literals():
    assert prepare_readonly_sqls("SELECT * FROM t WHERE note = 'delete'")


def test_prepare_readonly_sqls_blocks_expensive_sleep_functions():
    for sql in ["SELECT SLEEP(10)", "SELECT pg_sleep(10)", "SELECT BENCHMARK(1000000, MD5('x'))"]:
        assert_raises(sql)


def test_prepare_readonly_sqls_blocks_file_read_or_select_into_risks():
    for sql in ["SELECT * INTO new_table FROM t", "SELECT LOAD_FILE('/etc/passwd')"]:
        assert_raises(sql)


def test_prepare_readonly_sqls_blocks_file_write_tokens():
    for sql in ["SELECT * FROM t INTO OUTFILE '/tmp/x'", "SELECT 'abc' INTO DUMPFILE '/tmp/x'"]:
        assert_raises(sql)


def test_prepare_readonly_sqls_strips_comments_before_checking():
    assert prepare_readonly_sqls("/* harmless ; */ SELECT * FROM t -- trailing ; delete\n") == [
        "SELECT * FROM t"
    ]


def test_format_sql_literal_quotes_and_escapes_strings():
    assert format_sql_literal("O'Reilly") == "'O''Reilly'"
    assert format_sql_literal(12.5) == "12.5"
    assert format_sql_literal(None) == "NULL"
    assert format_sql_literal(["A", 2]) == "'A', 2"


def test_replace_sql_variables_formats_values_outside_or_inside_literals():
    sql = "SELECT * FROM t WHERE amount > {ExcelProcessor@result} AND name = {sys.name}"

    replaced = replace_sql_variables(
        sql,
        {
            "ExcelProcessor@result": 99.5,
            "sys.name": "O'Reilly",
        },
    )

    assert replaced == "SELECT * FROM t WHERE amount > 99.5 AND name = 'O''Reilly'"

    inside_literal = replace_sql_variables(
        "SELECT * FROM t WHERE name = '{sys.name}'",
        {"sys.name": "O'Reilly"},
    )

    assert inside_literal == "SELECT * FROM t WHERE name = 'O''Reilly'"


def test_replaced_sql_is_still_readonly_checked_after_injection_attempt():
    replaced = replace_sql_variables(
        "SELECT * FROM t WHERE name = {sys.name}",
        {"sys.name": "x'; DELETE FROM t; --"},
    )

    assert prepare_readonly_sqls(replaced) == [
        "SELECT * FROM t WHERE name = 'x''; DELETE FROM t; --'"
    ]
