import unittest
from .lexer import Lexer
from .tokens import TokenType

class TestLexerLiterals(unittest.TestCase):
    def test_hex_literal_declaration(self):
        source = "int x = 0x1F;"
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        
        # Expect tokens: int, x, =, 0x1F, ;, EOF
        self.assertEqual(tokens[0].type, TokenType.KEYWORD)
        self.assertEqual(tokens[0].value, "int")
        self.assertEqual(tokens[1].type, TokenType.IDENTIFIER)
        self.assertEqual(tokens[1].value, "x")
        self.assertEqual(tokens[2].type, TokenType.OPERATOR)
        self.assertEqual(tokens[2].value, "=")
        self.assertEqual(tokens[3].type, TokenType.INT_LITERAL)
        self.assertEqual(tokens[3].value, "0x1F")
        self.assertEqual(int(tokens[3].value, 0), 31)
        self.assertEqual(tokens[4].type, TokenType.PUNCTUATION)
        self.assertEqual(tokens[4].value, ";")

    def test_octal_literal(self):
        source = "int y = 017;"
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        
        self.assertEqual(tokens[3].type, TokenType.INT_LITERAL)
        self.assertEqual(tokens[3].value, "017")
        val = tokens[3].value
        num = int(val, 8) if len(val) > 1 and val.startswith("0") and not val.lower().startswith("0x") else int(val, 0)
        self.assertEqual(num, 15)

    def test_string_escapes_newline_tab(self):
        source = r'char* s = "line1\nline2\ttab";'
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        
        string_token = next(t for t in tokens if t.type == TokenType.STRING_LITERAL)
        self.assertEqual(string_token.value, "line1\nline2\ttab")

    def test_string_escaped_quote(self):
        source = r'char* s = "He said \"hello\"!";'
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        
        string_token = next(t for t in tokens if t.type == TokenType.STRING_LITERAL)
        self.assertEqual(string_token.value, 'He said "hello"!')

if __name__ == '__main__':
    unittest.main()
