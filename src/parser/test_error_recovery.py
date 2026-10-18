"""
Tests for panic-mode error recovery in Parser.

Verifies that:
  1. A single error in a 3-statement program yields 2 valid AST nodes + 1 error.
  2. Three separate errors are all captured with distinct line numbers.
  3. A valid program produces no errors.
  4. An error inside a block resumes correctly inside that same block.
"""
import unittest

from src.lexer.lexer import Lexer
from src.parser.parser import Parser, ParserError
from src.parser.ast_nodes import ProgramNode


def parse(src: str) -> Parser:
    """Lex + parse src, return the Parser (so callers can inspect both AST and errors)."""
    lexer = Lexer(src)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    parser.parse()
    return parser


class TestErrorRecovery(unittest.TestCase):

    # ------------------------------------------------------------------
    # Case 1: single error — two valid statements still in AST
    # ------------------------------------------------------------------
    def test_single_error_two_valid_statements(self):
        src = """\
int x = 10;
int y = ;
int z = 30;
"""
        # line 2: "int y = ;" — missing initializer expression
        p = parse(src)

        self.assertTrue(p.has_errors(), "Expected at least one error")
        self.assertEqual(len(p.get_errors()), 1, "Expected exactly 1 error")

        # Only the two valid declarations should be in the AST
        # parse() returns a ProgramNode; re-parse to get it
        lexer = Lexer(src)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        self.assertEqual(len(ast.declarations), 2,
                         f"Expected 2 valid AST nodes, got {len(ast.declarations)}: {ast.declarations}")
        names = [d.name for d in ast.declarations]
        self.assertIn('x', names)
        self.assertIn('z', names)
        self.assertNotIn('y', names)

        print(f"[Case 1] Errors: {[str(e) for e in parser.get_errors()]}")
        print(f"[Case 1] AST declarations: {names}")

    # ------------------------------------------------------------------
    # Case 2: three separate errors — all captured with different lines
    # ------------------------------------------------------------------
    def test_three_errors_all_captured(self):
        src = """\
int a = ;
int b = ;
int c = ;
"""
        # Each line has a missing initializer expression
        p = parse(src)

        errors = p.get_errors()
        self.assertEqual(len(errors), 3, f"Expected 3 errors, got {len(errors)}: {errors}")

        lines = [e.line for e in errors]
        self.assertEqual(len(set(lines)), 3, f"Expected 3 distinct error lines, got {lines}")
        self.assertIn(1, lines)
        self.assertIn(2, lines)
        self.assertIn(3, lines)

        messages = [str(e) for e in errors]
        self.assertEqual(len(set(messages)), 3, "Expected 3 distinct error messages")

        print(f"[Case 2] Errors:")
        for e in errors:
            print(f"  line {e.line}: {e}")

    # ------------------------------------------------------------------
    # Case 3: valid program — no errors, has_errors() is False
    # ------------------------------------------------------------------
    def test_valid_program_no_errors(self):
        src = """\
int foo(int a) {
    if (a > 0) {
        return a;
    }
    return 0;
}
"""
        lexer = Lexer(src)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()

        self.assertFalse(parser.has_errors(), f"Expected no errors, got: {parser.get_errors()}")
        self.assertEqual(parser.get_errors(), [])
        self.assertEqual(len(ast.declarations), 1)
        self.assertEqual(ast.declarations[0].name, 'foo')

        print(f"[Case 3] No errors. AST: {ast.declarations[0].__class__.__name__} '{ast.declarations[0].name}'")

    # ------------------------------------------------------------------
    # Case 4: error inside a block — rest of block still parses
    # ------------------------------------------------------------------
    def test_error_inside_block_resumes(self):
        src = """\
int foo(int a) {
    int x = 1;
    int y = ;
    int z = 3;
    return x;
}
"""
        # line 3 inside the function body is broken; lines 2, 4, 5 should still parse
        lexer = Lexer(src)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()

        self.assertTrue(parser.has_errors())
        self.assertEqual(len(parser.get_errors()), 1)

        # The function should still be in the AST
        self.assertEqual(len(ast.declarations), 1)
        func = ast.declarations[0]
        self.assertEqual(func.__class__.__name__, 'FuncDefNode')

        # Body should contain the 3 valid statements (x=1, z=3, return x)
        body_stmts = func.body.statements
        stmt_types = [s.__class__.__name__ for s in body_stmts]
        self.assertEqual(len(body_stmts), 3,
                         f"Expected 3 body statements, got {len(body_stmts)}: {stmt_types}")
        self.assertIn('VarDeclNode', stmt_types)
        self.assertIn('ReturnNode', stmt_types)

        print(f"[Case 4] Error: {parser.get_errors()[0]}")
        print(f"[Case 4] Body statements: {stmt_types}")


if __name__ == '__main__':
    unittest.main()
