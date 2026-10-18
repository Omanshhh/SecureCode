import unittest

from src.lexer.lexer import Lexer
from src.parser.parser import Parser
from src.parser.ast_nodes import (
    ProgramNode,
    VarDeclNode,
    ArrayAccessNode,
    AssignNode,
    LiteralNode,
    IdentifierNode,
)


def parse_src(src: str):
    lexer = Lexer(src)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()
    return parser, ast


class Test2DArrays(unittest.TestCase):
    def test_2d_array_declaration(self):
        src = "int grid[3][4];"
        parser, ast = parse_src(src)
        self.assertFalse(parser.has_errors())
        self.assertEqual(len(ast.declarations), 1)
        decl = ast.declarations[0]
        self.assertIsInstance(decl, VarDeclNode)
        self.assertEqual(decl.name, "grid")
        self.assertEqual(decl.array_size, 3)
        self.assertEqual(decl.array_size2, 4)

    def test_2d_array_access_and_assignment(self):
        src = """
        int x = grid[1][2];
        grid[0][3] = 5;
        """
        parser, ast = parse_src(src)
        self.assertFalse(parser.has_errors())
        self.assertEqual(len(ast.declarations), 2)
        
        # Access in variable declaration initializer
        decl = ast.declarations[0]
        self.assertIsInstance(decl, VarDeclNode)
        self.assertIsInstance(decl.init_expr, ArrayAccessNode)
        self.assertEqual(decl.init_expr.name, "grid")
        self.assertIsInstance(decl.init_expr.index_expr, LiteralNode)
        self.assertEqual(decl.init_expr.index_expr.value, "1")
        self.assertIsInstance(decl.init_expr.index_expr2, LiteralNode)
        self.assertEqual(decl.init_expr.index_expr2.value, "2")
        
        # 2D Array assignment
        assign = ast.declarations[1]
        self.assertIsInstance(assign, AssignNode)
        self.assertEqual(assign.target_name, "grid")
        self.assertIsInstance(assign.index_expr, LiteralNode)
        self.assertEqual(assign.index_expr.value, "0")
        self.assertIsInstance(assign.index_expr2, LiteralNode)
        self.assertEqual(assign.index_expr2.value, "3")
        self.assertIsInstance(assign.value_expr, LiteralNode)
        self.assertEqual(assign.value_expr.value, "5")

    def test_1d_array_regression(self):
        src = """
        int arr[10];
        arr[2] = 42;
        int y = arr[2];
        """
        parser, ast = parse_src(src)
        self.assertFalse(parser.has_errors())
        self.assertEqual(len(ast.declarations), 3)

        decl = ast.declarations[0]
        self.assertIsInstance(decl, VarDeclNode)
        self.assertEqual(decl.name, "arr")
        self.assertEqual(decl.array_size, 10)
        self.assertIsNone(decl.array_size2)

        assign = ast.declarations[1]
        self.assertIsInstance(assign, AssignNode)
        self.assertEqual(assign.target_name, "arr")
        self.assertIsInstance(assign.index_expr, LiteralNode)
        self.assertEqual(assign.index_expr.value, "2")
        self.assertIsNone(assign.index_expr2)

        read = ast.declarations[2]
        self.assertIsInstance(read, VarDeclNode)
        self.assertIsInstance(read.init_expr, ArrayAccessNode)
        self.assertEqual(read.init_expr.name, "arr")
        self.assertIsInstance(read.init_expr.index_expr, LiteralNode)
        self.assertEqual(read.init_expr.index_expr.value, "2")
        self.assertIsNone(read.init_expr.index_expr2)

    def test_3d_array_raises_parser_error(self):
        # 3D array access is not supported by grammar and should produce a ParserError
        src = "int x = grid[1][2][3];"
        parser, ast = parse_src(src)
        self.assertTrue(parser.has_errors())
        errors = parser.get_errors()
        self.assertTrue(any("Expected" in str(e) or "Unexpected" in str(e) for e in errors))


if __name__ == '__main__':
    unittest.main()
