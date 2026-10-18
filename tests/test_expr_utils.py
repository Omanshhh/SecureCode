"""Unit tests for the use/def extraction every other analysis is built on."""

from src.lexer.lexer import Lexer
from src.parser.parser import Parser
from src.dataflow.expr_utils import (
    stmt_defs,
    stmt_uses,
    collect_uses,
    find_all,
    functions,
    call_arg_identifiers,
)
from src.parser.ast_nodes import FuncCallNode


def statements_of(source):
    ast = Parser(Lexer(source).tokenize()).parse()
    return list(functions(ast))[0].body.statements


def names(pairs):
    return sorted({name for name, _line in pairs})


def test_declaration_without_initialiser_defines_nothing():
    stmt = statements_of("int f() { int x; }")[0]
    assert stmt_defs(stmt) == []
    assert stmt_uses(stmt) == []


def test_declaration_with_initialiser_defines_and_uses():
    stmt = statements_of("int f() { int x = y + 1; }")[0]
    assert names(stmt_defs(stmt)) == ["x"]
    assert names(stmt_uses(stmt)) == ["y"]


def test_scalar_assignment_defines_target():
    stmt = statements_of("int f() { int x; x = a + b; }")[1]
    assert names(stmt_defs(stmt)) == ["x"]
    assert names(stmt_uses(stmt)) == ["a", "b"]


def test_array_element_write_is_not_a_definition():
    # A symbolic-index write does not define the whole array 'a' as a 
    # scalar, but it DOES emit the wildcard marker so definite-assignment 
    # conservatively treats it as covering every known element - this is 
    # the soundness guarantee that avoids false positives on indexed writes.
    stmt = statements_of("int f() { int a[3]; a[i] = v; }")[1]
    defs = stmt_defs(stmt)
    assert defs == [('__ANY_ELEM__:a', 1)]
    assert names(stmt_uses(stmt)) == ["a", "i", "v"]


def test_array_read_uses_array_and_index():
    stmt = statements_of("int f() { int x; x = a[i]; }")[1]
    assert names(stmt_uses(stmt)) == ["a", "i"]


def test_call_arguments_are_uses_but_callee_name_is_not():
    stmt = statements_of("int f() { foo(x, y); }")[0]
    assert names(stmt_uses(stmt)) == ["x", "y"]


def test_bare_expression_is_accepted():
    # CFG condition nodes hold an expression, not a statement.
    ast = Parser(Lexer("int f() { if (a > b) { c = 1; } }").tokenize()).parse()
    condition = list(functions(ast))[0].body.statements[0].condition
    assert names(stmt_uses(condition)) == ["a", "b"]
    assert names(collect_uses(condition)) == ["a", "b"]


def test_find_all_locates_nested_calls():
    ast = Parser(Lexer("int f() { x = g(h(1)); }").tokenize()).parse()
    assert sorted(c.name for c in find_all(ast, FuncCallNode)) == ["g", "h"]


def test_call_arg_identifiers_flags_address_of():
    stmt = statements_of("int f() { foo(buf, &n, 1 + 2); }")[0]
    found = dict(call_arg_identifiers(stmt))
    assert found == {"buf": False, "n": True}
