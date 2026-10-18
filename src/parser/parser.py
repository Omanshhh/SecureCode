import sys
from typing import List, Optional

from src.lexer.tokens import Token, TokenType
from .ast_nodes import (
    ASTNode,
    ProgramNode, VarDeclNode, FuncDefNode, ParamNode, BlockNode, AssignNode,
    IfNode, WhileNode, ForNode, ReturnNode, ExprStmtNode, BinOpNode,
    UnaryOpNode, LiteralNode, IdentifierNode, ArrayAccessNode, FuncCallNode,
    InitListNode
)
from src.dataflow.expr_utils import parse_c_int_literal

class ParserError(Exception):
    def __init__(self, message: str, token: Token):
        line = token.line if token else -1
        column = token.column if token else -1
        super().__init__(f"Parse error at line {line}, column {column}: {message}")
        self.line = line
        self.column = column
        self.token = token

class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0
        self.current: Token = self.tokens[0] if self.tokens else Token(TokenType.EOF, "", -1, -1)
        self.errors: List[ParserError] = []

    # Helper methods -----------------------------------------------------
    def _peek(self, offset: int = 0) -> Token:
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return Token(TokenType.EOF, "", self.current.line, self.current.column)

    def _advance(self) -> Token:
        token = self.current
        self.pos += 1
        if self.pos < len(self.tokens):
            self.current = self.tokens[self.pos]
        else:
            self.current = Token(TokenType.EOF, "", token.line, token.column)
        return token

    def _match(self, typ: TokenType, value: Optional[str] = None) -> bool:
        if self.current.type == typ and (value is None or self.current.value == value):
            self._advance()
            return True
        return False

    def _expect(self, typ: TokenType, value: Optional[str] = None) -> Token:
        if self.current.type == typ and (value is None or self.current.value == value):
            return self._advance()
        raise ParserError(f"Expected {value if value else typ.name}, got '{self.current.value}'", self.current)

    # Error recovery -----------------------------------------------------
    _SYNC_KEYWORDS = {"int", "char", "float", "if", "while", "for", "return"}

    def synchronize(self) -> None:
        """Advance tokens until a safe resume point: ';', '}', or a statement-starting keyword."""
        while self.current.type != TokenType.EOF:
            if self.current.type == TokenType.PUNCTUATION and self.current.value == ';':
                self._advance()   # consume the ';' so the next iteration starts fresh
                return
            if self.current.type == TokenType.PUNCTUATION and self.current.value == '}':
                return            # don't consume '}' — let the enclosing block close itself
            if self.current.type == TokenType.KEYWORD and self.current.value in self._SYNC_KEYWORDS:
                return
            self._advance()

    def has_errors(self) -> bool:
        return bool(self.errors)

    def get_errors(self) -> List[ParserError]:
        return list(self.errors)

    # Parsing entry point ------------------------------------------------
    def parse(self) -> ProgramNode:
        program = self.parse_program()
        # Only expect EOF when no error recovery consumed all tokens
        if self.current.type != TokenType.EOF and not self.errors:
            try:
                self._expect(TokenType.EOF)
            except ParserError as e:
                self.errors.append(e)
        return program

    # Grammar rule methods ----------------------------------------------
    def parse_program(self) -> ProgramNode:
        decls: List[ASTNode] = []
        while self.current.type != TokenType.EOF:
            if self.current.type == TokenType.KEYWORD and self.current.value in {"int", "char", "float"}:
                try:
                    decls.append(self._parse_decl_or_func())
                except ParserError as e:
                    self.errors.append(e)
                    self.synchronize()
            elif self.current.type == TokenType.KEYWORD and self.current.value in {"if", "while", "for", "return"}:
                try:
                    decls.append(self.parse_stmt())
                except ParserError as e:
                    self.errors.append(e)
                    self.synchronize()
            elif self.current.type == TokenType.IDENTIFIER:
                try:
                    decls.append(self.parse_stmt())
                except ParserError as e:
                    self.errors.append(e)
                    self.synchronize()
            else:
                self.errors.append(ParserError("Unexpected token in program", self.current))
                self.synchronize()
        return ProgramNode(decls, line=1)

    def _parse_decl_or_func(self) -> ASTNode:
        # Parse type (including pointer)
        base_type, is_pointer = self._parse_type()
        name_tok = self._expect(TokenType.IDENTIFIER)
        name = name_tok.value
        if self._match(TokenType.PUNCTUATION, '('):
            # function definition
            params = self._parse_params()
            self._expect(TokenType.PUNCTUATION, ')')
            body = self.parse_block()
            return FuncDefNode(return_type=base_type, name=name, params=params, body=body, line=name_tok.line)
        else:
            # variable declaration
            array_size = None
            array_size2 = None
            if self._match(TokenType.PUNCTUATION, '['):
                size_tok = self._expect(TokenType.INT_LITERAL)
                array_size = parse_c_int_literal(size_tok.value)
                self._expect(TokenType.PUNCTUATION, ']')
                if self._match(TokenType.PUNCTUATION, '['):
                    size_tok2 = self._expect(TokenType.INT_LITERAL)
                    array_size2 = parse_c_int_literal(size_tok2.value)
                    self._expect(TokenType.PUNCTUATION, ']')
            init_expr = None
            if self._match(TokenType.OPERATOR, '='):
                if self.current.type == TokenType.PUNCTUATION and self.current.value == '{':
                    brace_tok = self._expect(TokenType.PUNCTUATION, '{')
                    elements = []
                    if not (self.current.type == TokenType.PUNCTUATION and self.current.value == '}'):
                        elements.append(self.parse_expr())
                        while self._match(TokenType.PUNCTUATION, ','):
                            elements.append(self.parse_expr())
                    self._expect(TokenType.PUNCTUATION, '}')
                    init_expr = InitListNode(elements=elements, line=brace_tok.line)
                else:
                    init_expr = self.parse_expr()
            self._expect(TokenType.PUNCTUATION, ';')
            return VarDeclNode(
                var_type=base_type,
                name=name,
                is_pointer=is_pointer,
                array_size=array_size,
                array_size2=array_size2,
                init_expr=init_expr,
                line=name_tok.line,
            )

    def _parse_type(self) -> (str, bool):
        # keyword
        typ_tok = self._expect(TokenType.KEYWORD)
        base = typ_tok.value
        is_pointer = False
        while self._match(TokenType.OPERATOR, '*'):
            is_pointer = True
        return base, is_pointer

    def _parse_params(self) -> List[ParamNode]:
        params: List[ParamNode] = []
        if self.current.type == TokenType.PUNCTUATION and self.current.value == ')':
            return params  # empty
        while True:
            base_type, is_pointer = self._parse_type()
            name_tok = self._expect(TokenType.IDENTIFIER)
            params.append(ParamNode(param_type=base_type, name=name_tok.value, is_pointer=is_pointer, line=name_tok.line))
            if not self._match(TokenType.PUNCTUATION, ','):
                break
        return params

    def parse_block(self) -> BlockNode:
        open_tok = self._expect(TokenType.PUNCTUATION, '{')
        stmts: List[ASTNode] = []
        while not (self.current.type == TokenType.PUNCTUATION and self.current.value == '}'):
            if self.current.type == TokenType.EOF:
                break
            try:
                stmts.append(self.parse_stmt())
            except ParserError as e:
                self.errors.append(e)
                self.synchronize()
        self._expect(TokenType.PUNCTUATION, '}')
        return BlockNode(stmts, line=open_tok.line)

    def parse_stmt(self) -> ASTNode:
        if self.current.type == TokenType.KEYWORD:
            kw = self.current.value
            if kw in {"int", "char", "float"}:
                return self._parse_decl_or_func()
            if kw == "if":
                return self.parse_if_stmt()
            if kw == "while":
                return self.parse_while_stmt()
            if kw == "for":
                return self.parse_for_stmt()
            if kw == "return":
                return self.parse_return_stmt()
        # identifier based statements
        if self.current.type == TokenType.IDENTIFIER:
            # lookahead
            next_tok = self._peek(1)
            if next_tok.type == TokenType.PUNCTUATION and next_tok.value == '(':
                expr = self.parse_expr()
                self._expect(TokenType.PUNCTUATION, ';')
                return ExprStmtNode(expr, line=expr.line)
            else:
                # could be assignment or expression statement
                # We'll try assignment parsing first
                start_tok = self.current
                target_name = self._expect(TokenType.IDENTIFIER).value
                index_expr = None
                index_expr2 = None
                if self._match(TokenType.PUNCTUATION, '['):
                    index_expr = self.parse_expr()
                    self._expect(TokenType.PUNCTUATION, ']')
                    if self._match(TokenType.PUNCTUATION, '['):
                        index_expr2 = self.parse_expr()
                        self._expect(TokenType.PUNCTUATION, ']')
                self._expect(TokenType.OPERATOR, '=')
                value_expr = self.parse_expr()
                self._expect(TokenType.PUNCTUATION, ';')
                return AssignNode(target_name=target_name, index_expr=index_expr, index_expr2=index_expr2, value_expr=value_expr, line=start_tok.line)
        if self.current.type == TokenType.PUNCTUATION and self.current.value == '{':
            return self.parse_block()
        raise ParserError("Unexpected statement", self.current)

    def parse_if_stmt(self) -> IfNode:
        kw_tok = self._expect(TokenType.KEYWORD, 'if')
        self._expect(TokenType.PUNCTUATION, '(')
        cond = self.parse_expr()
        self._expect(TokenType.PUNCTUATION, ')')
        then_block = self.parse_block()
        else_block = None
        if self._match(TokenType.KEYWORD, 'else'):
            if self.current.type == TokenType.KEYWORD and self.current.value == 'if':
                else_block = BlockNode([self.parse_if_stmt()], line=self.current.line)
            else:
                else_block = self.parse_block()
        return IfNode(condition=cond, then_block=then_block, else_block=else_block, line=kw_tok.line)

    def parse_while_stmt(self) -> WhileNode:
        kw_tok = self._expect(TokenType.KEYWORD, 'while')
        self._expect(TokenType.PUNCTUATION, '(')
        cond = self.parse_expr()
        self._expect(TokenType.PUNCTUATION, ')')
        body = self.parse_block()
        return WhileNode(condition=cond, body=body, line=kw_tok.line)

    def parse_for_stmt(self) -> ForNode:
        kw_tok = self._expect(TokenType.KEYWORD, 'for')
        self._expect(TokenType.PUNCTUATION, '(')
        # init can be decl or assign
        if self.current.type == TokenType.KEYWORD:
            init = self._parse_decl_or_func()
        else:
            # assignment style init
            target = self._expect(TokenType.IDENTIFIER).value
            self._expect(TokenType.OPERATOR, '=')
            value = self.parse_expr()
            init = AssignNode(target_name=target, value_expr=value, line=self.current.line)
        cond = self.parse_expr()
        self._expect(TokenType.PUNCTUATION, ';')
        update = self.parse_assign_expr()
        self._expect(TokenType.PUNCTUATION, ')')
        body = self.parse_block()
        return ForNode(init=init, condition=cond, update=update, body=body, line=kw_tok.line)

    def parse_assign_expr(self) -> AssignNode:
        # simple assignment used in for‑update (IDENTIFIER = expr)
        target = self._expect(TokenType.IDENTIFIER).value
        self._expect(TokenType.OPERATOR, '=')
        value = self.parse_expr()
        return AssignNode(target_name=target, value_expr=value, line=self.current.line)

    def parse_return_stmt(self) -> ReturnNode:
        kw_tok = self._expect(TokenType.KEYWORD, 'return')
        if self.current.type != TokenType.PUNCTUATION or self.current.value != ';':
            expr = self.parse_expr()
        else:
            expr = None
        self._expect(TokenType.PUNCTUATION, ';')
        return ReturnNode(value=expr, line=kw_tok.line)

    def parse_expr(self) -> ASTNode:
        return self.parse_logic_or()

    def parse_logic_or(self) -> ASTNode:
        node = self.parse_logic_and()
        while self._match(TokenType.OPERATOR, '||'):
            op_tok = self.tokens[self.pos - 1]
            right = self.parse_logic_and()
            node = BinOpNode(op='||', left=node, right=right, line=op_tok.line)
        return node

    def parse_logic_and(self) -> ASTNode:
        node = self.parse_equality()
        while self._match(TokenType.OPERATOR, '&&'):
            op_tok = self.tokens[self.pos - 1]
            right = self.parse_equality()
            node = BinOpNode(op='&&', left=node, right=right, line=op_tok.line)
        return node

    def parse_equality(self) -> ASTNode:
        node = self.parse_comparison()
        while True:
            if self._match(TokenType.OPERATOR, '=='):
                op = '=='
            elif self._match(TokenType.OPERATOR, '!='):
                op = '!='
            else:
                break
            op_tok = self.tokens[self.pos - 1]
            right = self.parse_comparison()
            node = BinOpNode(op=op, left=node, right=right, line=op_tok.line)
        return node

    def parse_comparison(self) -> ASTNode:
        node = self.parse_term()
        while True:
            if self._match(TokenType.OPERATOR, '<'):
                op = '<'
            elif self._match(TokenType.OPERATOR, '>'):
                op = '>'
            elif self._match(TokenType.OPERATOR, '<='):
                op = '<='
            elif self._match(TokenType.OPERATOR, '>='):
                op = '>='
            else:
                break
            op_tok = self.tokens[self.pos - 1]
            right = self.parse_term()
            node = BinOpNode(op=op, left=node, right=right, line=op_tok.line)
        return node

    def parse_term(self) -> ASTNode:
        node = self.parse_factor()
        while True:
            if self._match(TokenType.OPERATOR, '+'):
                op = '+'
            elif self._match(TokenType.OPERATOR, '-'):
                op = '-'
            else:
                break
            op_tok = self.tokens[self.pos - 1]
            right = self.parse_factor()
            node = BinOpNode(op=op, left=node, right=right, line=op_tok.line)
        return node

    def parse_factor(self) -> ASTNode:
        node = self.parse_unary()
        while True:
            if self._match(TokenType.OPERATOR, '*'):
                op = '*'
            elif self._match(TokenType.OPERATOR, '/'):
                op = '/'
            elif self._match(TokenType.OPERATOR, '%'):
                op = '%'
            else:
                break
            op_tok = self.tokens[self.pos - 1]
            right = self.parse_unary()
            node = BinOpNode(op=op, left=node, right=right, line=op_tok.line)
        return node

    def parse_unary(self) -> ASTNode:
        if self.current.type == TokenType.OPERATOR and self.current.value in ('!', '-', '*', '&'):
            op_tok = self._advance()
            operand = self.parse_unary()
            return UnaryOpNode(op=op_tok.value, operand=operand, line=op_tok.line)
        return self.parse_primary()

    def parse_primary(self) -> ASTNode:
        tok = self.current
        if tok.type == TokenType.INT_LITERAL:
            self._advance()
            return LiteralNode(value=tok.value, literal_type='int', line=tok.line)
        if tok.type == TokenType.FLOAT_LITERAL:
            self._advance()
            return LiteralNode(value=tok.value, literal_type='float', line=tok.line)
        if tok.type == TokenType.STRING_LITERAL:
            self._advance()
            return LiteralNode(value=tok.value, literal_type='string', line=tok.line)
        if tok.type == TokenType.IDENTIFIER:
            # could be array access, function call, or simple identifier
            name = tok.value
            self._advance()
            if self._match(TokenType.PUNCTUATION, '('):
                args: List[ASTNode] = []
                if not (self.current.type == TokenType.PUNCTUATION and self.current.value == ')'):
                    while True:
                        args.append(self.parse_expr())
                        if not self._match(TokenType.PUNCTUATION, ','):
                            break
                self._expect(TokenType.PUNCTUATION, ')')
                return FuncCallNode(name=name, args=args, line=tok.line)
            if self._match(TokenType.PUNCTUATION, '['):
                index = self.parse_expr()
                self._expect(TokenType.PUNCTUATION, ']')
                index2 = None
                if self._match(TokenType.PUNCTUATION, '['):
                    index2 = self.parse_expr()
                    self._expect(TokenType.PUNCTUATION, ']')
                return ArrayAccessNode(name=name, index_expr=index, index_expr2=index2, line=tok.line)
            return IdentifierNode(name=name, line=tok.line)
        if tok.type == TokenType.PUNCTUATION and tok.value == '(':
            self._advance()
            expr = self.parse_expr()
            self._expect(TokenType.PUNCTUATION, ')')
            return expr
        raise ParserError('Unexpected token in expression', tok)
