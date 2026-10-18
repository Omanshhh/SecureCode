import unittest

from src.lexer.lexer import Lexer
from src.parser.parser import Parser
from src.parser.ast_nodes import (
    ProgramNode,
    DoWhileNode,
    BlockNode,
    BinOpNode,
    IdentifierNode,
    LiteralNode,
    AssignNode,
)
from src.analysis.semantic_analyzer import SemanticAnalyzer
from src.analysis.cfg_builder import CFGBuilder


def parse_src(src: str):
    lexer = Lexer(src)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()
    return parser, ast


class TestDoWhile(unittest.TestCase):

    def test_do_while_parser_shape(self):
        src = """
        int main() {
            int x = 0;
            do {
                x += 1;
            } while (x < 10);
            return x;
        }
        """
        parser, ast = parse_src(src)
        self.assertFalse(parser.has_errors())
        self.assertEqual(len(ast.declarations), 1)

        func = ast.declarations[0]
        stmts = func.body.statements
        self.assertEqual(len(stmts), 3)

        do_while = stmts[1]
        self.assertIsInstance(do_while, DoWhileNode)

        # Body is BlockNode
        self.assertIsInstance(do_while.body, BlockNode)
        self.assertEqual(len(do_while.body.statements), 1)
        self.assertIsInstance(do_while.body.statements[0], AssignNode)

        # Condition is BinOpNode(op='<', left=IdentifierNode('x'), right=LiteralNode('10'))
        self.assertIsInstance(do_while.condition, BinOpNode)
        self.assertEqual(do_while.condition.op, "<")
        self.assertIsInstance(do_while.condition.left, IdentifierNode)
        self.assertEqual(do_while.condition.left.name, "x")
        self.assertIsInstance(do_while.condition.right, LiteralNode)
        self.assertEqual(do_while.condition.right.value, "10")

    def test_do_while_semantic_scoping(self):
        # Variable declared inside the do-while body block should not be visible outside
        src = """
        int main() {
            do {
                int inside_var = 42;
            } while (1);
            int y = inside_var;
            return y;
        }
        """
        _parser, ast = parse_src(src)
        analyzer = SemanticAnalyzer()
        analyzer.analyze(ast)

        errors = analyzer.get_errors()
        self.assertTrue(any(e["type"] == "UndeclaredIdentifier" and "inside_var" in e["message"] for e in errors),
                        f"Expected UndeclaredIdentifier error for 'inside_var', got {errors}")

    def test_do_while_cfg_structure(self):
        src = """
        int foo() {
            int x = 0;
            do {
                x += 1;
            } while (x < 10);
            return x;
        }
        """
        _parser, ast = parse_src(src)
        func = ast.declarations[0]

        builder = CFGBuilder()
        cfg = builder.build(func)

        # Find DO-WHILE CONDITION node
        cond_nodes = [n for n, d in cfg.nodes(data=True) if d.get("label") == "DO-WHILE CONDITION"]
        self.assertEqual(len(cond_nodes), 1)
        cond_node = cond_nodes[0]

        # Condition node must have condition expression attached
        self.assertIsNotNone(cfg.nodes[cond_node].get("condition"))

        # Outgoing edges from condition node: exactly one 'true' (loop back) and one 'false' (continuation)
        out_edges = list(cfg.out_edges(cond_node, data=True))
        edge_types = {d.get("edge_type"): v for u, v, d in out_edges}
        self.assertIn("true", edge_types)
        self.assertIn("false", edge_types)

        body_entry = edge_types["true"]

        # Confirm the body's first statement executes BEFORE the condition on the first pass:
        # Predecessors of body_entry must include the node from the statement before the loop (int x = 0),
        # not just the condition node.
        preds = list(cfg.predecessors(body_entry))
        self.assertIn(cond_node, preds)  # loop back
        self.assertTrue(len(preds) >= 2, f"Expected body entry to have incoming edge from outside loop, preds={preds}")

        # The condition node's predecessors must come from the loop body
        cond_preds = list(cfg.predecessors(cond_node))
        self.assertIn(body_entry, cond_preds)


if __name__ == '__main__':
    unittest.main()
