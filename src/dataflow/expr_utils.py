"""
Shared AST helpers for data-flow analysis and the security rules.

Two jobs:

1. Generic traversal (`walk`) so AST-based rules can find every node of a
   given kind without each rule re-implementing a visitor.
2. Extracting the *definitions* and *uses* of variables from a statement,
   which is the input the data-flow equations operate on.

A note on the CFG: `CFGBuilder` stores at most one AST item per node, and for
condition nodes that item is an *expression*, not a statement. So `stmt_uses`
accepts both and falls through to `collect_uses` for bare expressions.
"""

from dataclasses import fields, is_dataclass

from src.parser.ast_nodes import (
    ASTNode,
    ProgramNode,
    VarDeclNode,
    FuncDefNode,
    BlockNode,
    AssignNode,
    IfNode,
    WhileNode,
    ForNode,
    ReturnNode,
    ExprStmtNode,
    BinOpNode,
    UnaryOpNode,
    LiteralNode,
    IdentifierNode,
    ArrayAccessNode,
    FuncCallNode,
    InitListNode,
)


# ---------------------------------------------------------------
# LITERAL HELPERS
# ---------------------------------------------------------------

def parse_c_int_literal(value: str) -> int:
    """Parse a C integer literal string (hex, octal, or decimal) into an int."""
    if len(value) > 1 and value.startswith("0") and not value.lower().startswith("0x"):
        return int(value, 8)
    return int(value, 0)


# ---------------------------------------------------------------
# GENERIC TRAVERSAL
# ---------------------------------------------------------------

def walk(node):
    """
    Yield `node` and every AST node beneath it, pre-order.

    Driven by dataclass introspection rather than a hand-written case per
    node type, so it keeps working if Member 1 adds new node types.
    """
    if node is None:
        return

    if isinstance(node, (list, tuple)):
        for item in node:
            yield from walk(item)
        return

    if not isinstance(node, ASTNode):
        return

    yield node

    if is_dataclass(node):
        for f in fields(node):
            yield from walk(getattr(node, f.name))


def find_all(node, node_type):
    """Yield every descendant of `node` that is an instance of `node_type`."""
    for child in walk(node):
        if isinstance(child, node_type):
            yield child


def functions(program):
    """Yield every FuncDefNode in a ProgramNode."""
    if isinstance(program, ProgramNode):
        for decl in program.declarations:
            if isinstance(decl, FuncDefNode):
                yield decl


def global_decls(program):
    """Yield every top-level VarDeclNode (file-scope globals)."""
    if isinstance(program, ProgramNode):
        for decl in program.declarations:
            if isinstance(decl, VarDeclNode):
                yield decl


def line_of(node, default=0):
    """Best-effort source line for any AST node."""
    return getattr(node, "line", default) or default


# ---------------------------------------------------------------
# USES
# ---------------------------------------------------------------

def collect_uses(node):
    """
    Return [(variable_name, line)] for every variable *read* in an expression.

    Assignment targets are not uses; callers handle those separately. A
    function's own name in a call is not a variable use, but its arguments are.
    """
    uses = []

    if node is None:
        return uses

    if isinstance(node, IdentifierNode):
        uses.append((node.name, node.line))

    elif isinstance(node, ArrayAccessNode):
        # `a[i]` reads both the array and the index.
        uses.append((node.name, node.line))
        uses.extend(collect_uses(node.index_expr))

    elif isinstance(node, BinOpNode):
        uses.extend(collect_uses(node.left))
        uses.extend(collect_uses(node.right))

    elif isinstance(node, UnaryOpNode):
        uses.extend(collect_uses(node.operand))

    elif isinstance(node, FuncCallNode):
        for arg in node.args:
            uses.extend(collect_uses(arg))

    elif isinstance(node, InitListNode):
        for element in node.elements:
            uses.extend(collect_uses(element))

    elif isinstance(node, LiteralNode):
        pass

    return uses


# ---------------------------------------------------------------
# DEFINITIONS
# ---------------------------------------------------------------

def stmt_defs(stmt):
    """
    Return [(variable_name, line)] for every variable *definitely assigned*
    by a statement.

    Deliberately conservative in two places:

    - `int x;` with no initialiser defines nothing.
    - `a[0] = 5;` does not count as defining `a`. Writing one element does
      not initialise the whole array, so treating it as a definition would
      hide genuine uninitialised-use bugs.
    """
    if stmt is None:
        return []

    if isinstance(stmt, VarDeclNode):
        if stmt.init_expr is not None:
            return [(stmt.name, stmt.line)]
        return []

    if isinstance(stmt, AssignNode):
        if stmt.index_expr is None:
            return [(stmt.target_name, stmt.line)]
        return []

    return []


def stmt_uses(stmt):
    """
    Return [(variable_name, line)] for every variable *read* by a statement.

    Accepts a bare expression too, because CFG condition nodes hold the
    condition expression rather than a statement.
    """
    if stmt is None:
        return []

    if isinstance(stmt, VarDeclNode):
        return collect_uses(stmt.init_expr)

    if isinstance(stmt, AssignNode):
        if stmt.index_expr is None:
            return collect_uses(stmt.value_expr)

        # `a[i] = v` reads a, i and v.
        uses = [(stmt.target_name, stmt.line)]
        uses.extend(collect_uses(stmt.index_expr))
        uses.extend(collect_uses(stmt.value_expr))
        return uses

    if isinstance(stmt, ExprStmtNode):
        return collect_uses(stmt.expr)

    if isinstance(stmt, ReturnNode):
        return collect_uses(stmt.value)

    if isinstance(stmt, (IfNode, WhileNode)):
        return collect_uses(stmt.condition)

    if isinstance(stmt, ForNode):
        return collect_uses(stmt.condition)

    # Bare expression (e.g. a CFG condition node).
    return collect_uses(stmt)


def call_arg_identifiers(node):
    """
    Yield (name, by_address) for bare identifiers passed as call arguments.

    These are the arguments a callee could plausibly *write to*: an array or
    pointer passed by value, or any variable passed with `&`. Callers use this
    to avoid reporting `char buf[64]; gets(buf);` as a read of an
    uninitialised variable - `gets` initialises `buf`, it does not read it.

    Without interprocedural analysis we cannot know what a callee really does,
    so treating these as possible out-parameters trades a few false negatives
    for no false positives, which is the right way round for a security tool
    nobody will trust after it cries wolf.
    """
    for call in find_all(node, FuncCallNode):
        for arg in call.args:
            if isinstance(arg, IdentifierNode):
                yield arg.name, False
            elif (isinstance(arg, UnaryOpNode)
                  and arg.op == "&"
                  and isinstance(arg.operand, IdentifierNode)):
                yield arg.operand.name, True
