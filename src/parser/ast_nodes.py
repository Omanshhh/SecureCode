from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional

# Base class for all AST nodes (optional, for type checking)
class ASTNode:
    pass


@dataclass
class ProgramNode(ASTNode):
    declarations: List[ASTNode]
    line: int


# Variable declaration node
@dataclass
class VarDeclNode(ASTNode):
    var_type: str  # e.g., "int", "char", "float"
    name: str
    is_pointer: bool = False
    array_size: Optional[int] = None  # For static array size, if any
    array_size2: Optional[int] = None  # For 2D static array size, if any
    init_expr: Optional[ASTNode] = None
    line: int = 0


@dataclass
class FuncDefNode(ASTNode):
    return_type: str
    name: str
    params: List[ParamNode]
    body: BlockNode
    line: int = 0


@dataclass
class ParamNode(ASTNode):
    param_type: str
    name: str
    is_pointer: bool = False
    line: int = 0


@dataclass
class BlockNode(ASTNode):
    statements: List[ASTNode]
    line: int = 0


@dataclass
class AssignNode(ASTNode):
    target_name: str
    index_expr: Optional[ASTNode] = None  # For array element assignment
    index_expr2: Optional[ASTNode] = None  # For 2D array element assignment
    value_expr: ASTNode = None
    line: int = 0


@dataclass
class IfNode(ASTNode):
    condition: ASTNode
    then_block: BlockNode
    else_block: Optional[BlockNode] = None
    line: int = 0


@dataclass
class WhileNode(ASTNode):
    condition: ASTNode
    body: BlockNode
    line: int = 0


@dataclass
class DoWhileNode(ASTNode):
    body: BlockNode
    condition: ASTNode
    line: int = 0


@dataclass
class ForNode(ASTNode):
    init: ASTNode  # Could be VarDeclNode or AssignNode
    condition: ASTNode
    update: ASTNode
    body: BlockNode
    line: int = 0


@dataclass
class BreakNode(ASTNode):
    line: int = 0


@dataclass
class CaseClauseNode(ASTNode):
    match_value: ASTNode  # LiteralNode or IdentifierNode
    body: List[ASTNode]
    line: int = 0


@dataclass
class SwitchNode(ASTNode):
    switch_expr: ASTNode
    cases: List[CaseClauseNode]
    default_body: Optional[List[ASTNode]] = None
    line: int = 0


@dataclass
class ReturnNode(ASTNode):
    value: Optional[ASTNode] = None
    line: int = 0


@dataclass
class ExprStmtNode(ASTNode):
    expr: ASTNode
    line: int = 0


@dataclass
class BinOpNode(ASTNode):
    op: str
    left: ASTNode
    right: ASTNode
    line: int = 0


@dataclass
class UnaryOpNode(ASTNode):
    op: str
    operand: ASTNode
    line: int = 0


@dataclass
class LiteralNode(ASTNode):
    value: str
    literal_type: str  # "int", "float", "string"
    line: int = 0


@dataclass
class IdentifierNode(ASTNode):
    name: str
    line: int = 0


@dataclass
class ArrayAccessNode(ASTNode):
    name: str
    index_expr: ASTNode
    index_expr2: Optional[ASTNode] = None
    line: int = 0


@dataclass
class FuncCallNode(ASTNode):
    name: str
    args: List[ASTNode]
    line: int = 0


@dataclass
class InitListNode(ASTNode):
    elements: List[ASTNode]
    line: int = 0
