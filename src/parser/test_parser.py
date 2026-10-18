import unittest
from src.lexer.lexer import Lexer
from src.parser.parser import Parser, ParserError
from src.parser.ast_nodes import ProgramNode


def parse_source(src: str) -> ProgramNode:
    lexer = Lexer(src)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    return parser.parse()


class TestParser(unittest.TestCase):
    def test_variable_declaration(self):
        src = "int x = 10;"
        ast = parse_source(src)
        # Expect a single VarDeclNode in program
        self.assertEqual(len(ast.declarations), 1)
        decl = ast.declarations[0]
        self.assertEqual(decl.__class__.__name__, 'VarDeclNode')
        self.assertEqual(decl.name, 'x')
        print('Variable declaration AST:', repr(ast))

    def test_function_with_if_else(self):
        src = """
        int foo(int a) {
            if (a > 0) {
                return a;
            } else {
                return -a;
            }
        }
        """
        ast = parse_source(src)
        self.assertEqual(len(ast.declarations), 1)
        func = ast.declarations[0]
        self.assertEqual(func.__class__.__name__, 'FuncDefNode')
        self.assertEqual(func.name, 'foo')
        print('Function with if/else AST:', repr(ast))

    def test_while_loop(self):
        src = """
        while (i < 10) {
            i = i + 1;
        }
        """
        ast = parse_source(src)
        self.assertEqual(len(ast.declarations), 1)
        while_node = ast.declarations[0]
        self.assertEqual(while_node.__class__.__name__, 'WhileNode')
        print('While loop AST:', repr(ast))

    def test_for_loop(self):
        src = """
        for (int i = 0; i < 5; i = i + 1) {
            print(i);
        }
        """
        ast = parse_source(src)
        self.assertEqual(len(ast.declarations), 1)
        for_node = ast.declarations[0]
        self.assertEqual(for_node.__class__.__name__, 'ForNode')
        print('For loop AST:', repr(ast))

    def test_array_declaration_and_access(self):
        src = """
        int arr[3] = {1, 2, 3};
        int x = arr[1];
        """
        # Note: initializer list not in grammar, but we test declaration and simple access
        ast = parse_source(src)
        self.assertEqual(len(ast.declarations), 2)
        decl = ast.declarations[0]
        self.assertEqual(decl.__class__.__name__, 'VarDeclNode')
        self.assertEqual(decl.init_expr.__class__.__name__, 'InitListNode')
        self.assertEqual(len(decl.init_expr.elements), 3)
        self.assertEqual([e.value for e in decl.init_expr.elements], ['1', '2', '3'])
        
        assign = ast.declarations[1]
        # This is a variable declaration with an initializer that accesses the array
        self.assertEqual(assign.__class__.__name__, 'VarDeclNode')
        self.assertEqual(assign.init_expr.__class__.__name__, 'ArrayAccessNode')
        print('Array declaration/access AST:', repr(ast))

    def test_malformed_input(self):
        src = "int x = ;"
        lexer = Lexer(src)
        tokens = lexer.tokenize()
        parser = Parser(tokens)
        ast = parser.parse()
        self.assertTrue(parser.has_errors())
        errors = parser.get_errors()
        self.assertEqual(len(errors), 1)
        self.assertIn('Unexpected token', str(errors[0]))
        print('Malformed input error:', errors[0])

if __name__ == '__main__':
    unittest.main()
