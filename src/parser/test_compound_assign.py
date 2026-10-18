import unittest

from src.lexer.lexer import Lexer
from src.parser.parser import Parser
from src.parser.ast_nodes import (
    ProgramNode,
    AssignNode,
    BinOpNode,
    IdentifierNode,
    ArrayAccessNode,
    LiteralNode,
    ForNode,
)


def parse_src(src: str):
    lexer = Lexer(src)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()
    return parser, ast


class TestCompoundAssign(unittest.TestCase):
    def test_scalar_compound_assign(self):
        src_compound = "x += 5;"
        src_expanded = "x = x + 5;"

        parser1, ast1 = parse_src(src_compound)
        parser2, ast2 = parse_src(src_expanded)

        self.assertFalse(parser1.has_errors())
        self.assertFalse(parser2.has_errors())

        assign = ast1.declarations[0]
        self.assertIsInstance(assign, AssignNode)
        self.assertEqual(assign.target_name, "x")
        self.assertIsNone(assign.index_expr)
        self.assertIsNone(assign.index_expr2)

        # Confirm value_expr is BinOpNode(op='+', left=IdentifierNode('x'), right=LiteralNode('5'))
        self.assertIsInstance(assign.value_expr, BinOpNode)
        self.assertEqual(assign.value_expr.op, "+")
        self.assertIsInstance(assign.value_expr.left, IdentifierNode)
        self.assertEqual(assign.value_expr.left.name, "x")
        self.assertIsInstance(assign.value_expr.right, LiteralNode)
        self.assertEqual(assign.value_expr.right.value, "5")

        # Compare shapes with manually expanded assignment
        expanded_assign = ast2.declarations[0]
        self.assertEqual(assign.target_name, expanded_assign.target_name)
        self.assertEqual(assign.value_expr.op, expanded_assign.value_expr.op)
        self.assertEqual(assign.value_expr.left.name, expanded_assign.value_expr.left.name)
        self.assertEqual(assign.value_expr.right.value, expanded_assign.value_expr.right.value)

    def test_indexed_compound_assign_1d(self):
        src = "arr[i] -= 10;"
        parser, ast = parse_src(src)
        self.assertFalse(parser.has_errors())

        assign = ast.declarations[0]
        self.assertIsInstance(assign, AssignNode)
        self.assertEqual(assign.target_name, "arr")
        self.assertIsInstance(assign.index_expr, IdentifierNode)
        self.assertEqual(assign.index_expr.name, "i")
        self.assertIsNone(assign.index_expr2)

        # value_expr must be BinOpNode('-', arr[i], 10)
        self.assertIsInstance(assign.value_expr, BinOpNode)
        self.assertEqual(assign.value_expr.op, "-")
        self.assertIsInstance(assign.value_expr.left, ArrayAccessNode)
        self.assertEqual(assign.value_expr.left.name, "arr")
        self.assertEqual(assign.value_expr.left.index_expr.name, "i")
        self.assertIsNone(assign.value_expr.left.index_expr2)
        self.assertIsInstance(assign.value_expr.right, LiteralNode)
        self.assertEqual(assign.value_expr.right.value, "10")

    def test_indexed_compound_assign_2d(self):
        src = "grid[1][2] *= 3;"
        parser, ast = parse_src(src)
        self.assertFalse(parser.has_errors())

        assign = ast.declarations[0]
        self.assertIsInstance(assign, AssignNode)
        self.assertEqual(assign.target_name, "grid")
        self.assertIsInstance(assign.index_expr, LiteralNode)
        self.assertEqual(assign.index_expr.value, "1")
        self.assertIsInstance(assign.index_expr2, LiteralNode)
        self.assertEqual(assign.index_expr2.value, "2")

        # value_expr must be BinOpNode('*', grid[1][2], 3)
        self.assertIsInstance(assign.value_expr, BinOpNode)
        self.assertEqual(assign.value_expr.op, "*")
        self.assertIsInstance(assign.value_expr.left, ArrayAccessNode)
        self.assertEqual(assign.value_expr.left.name, "grid")
        self.assertEqual(assign.value_expr.left.index_expr.value, "1")
        self.assertEqual(assign.value_expr.left.index_expr2.value, "2")
        self.assertIsInstance(assign.value_expr.right, LiteralNode)
        self.assertEqual(assign.value_expr.right.value, "3")

    def test_for_loop_compound_update(self):
        src = """
        for (i = 0; i < 10; i += 2) {
            x = x + 1;
        }
        """
        parser, ast = parse_src(src)
        self.assertFalse(parser.has_errors())

        for_node = ast.declarations[0]
        self.assertIsInstance(for_node, ForNode)

        update = for_node.update
        self.assertIsInstance(update, AssignNode)
        self.assertEqual(update.target_name, "i")
        self.assertIsInstance(update.value_expr, BinOpNode)
        self.assertEqual(update.value_expr.op, "+")
        self.assertIsInstance(update.value_expr.left, IdentifierNode)
        self.assertEqual(update.value_expr.left.name, "i")
        self.assertIsInstance(update.value_expr.right, LiteralNode)
        self.assertEqual(update.value_expr.right.value, "2")


if __name__ == '__main__':
    unittest.main()
