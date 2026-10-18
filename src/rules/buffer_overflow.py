"""
Rule: writes and reads past the end of a fixed-size array.

Two checks, both of which use `Symbol.array_size` from the symbol table and
are *provable* rather than heuristic, so neither produces false positives:

1. A constant subscript outside the declared bounds - `int a[3]; a[5] = 1;`
   or a negative index.
2. A string literal copied into an array too small to hold it, including its
   null terminator - `char b[8]; strcpy(b, "much too long");`

Not covered: indices computed at runtime, such as a loop bound that runs one
past the end. That needs interval/range analysis, which is beyond Review 1.
"""

from src.rules.base import Rule
from src.rules.finding import Finding, Severity
from src.parser.ast_nodes import (
    ArrayAccessNode,
    AssignNode,
    LiteralNode,
    FuncCallNode,
    IdentifierNode,
)
from src.dataflow.expr_utils import walk, parse_c_int_literal


# Functions that write their 2nd argument into their 1st, unbounded.
COPY_FUNCTIONS = {"strcpy", "strcat", "sprintf"}


def _constant_int(expr):
    """Return the value of an integer literal expression, or None."""
    if isinstance(expr, LiteralNode) and expr.literal_type == "int":
        try:
            return parse_c_int_literal(expr.value)
        except (TypeError, ValueError):
            return None
    return None


class BufferOverflowRule(Rule):

    rule_id = "BUFFER_OVERFLOW"
    name = "Buffer Overflow"

    def run(self, ctx):
        findings = []

        for func_name, func_node in ctx.functions.items():
            for node in walk(func_node):

                if isinstance(node, ArrayAccessNode):
                    findings.extend(self._check_index(
                        ctx, func_name, node.name, node.index_expr, node.line))

                elif isinstance(node, AssignNode) and node.index_expr is not None:
                    findings.extend(self._check_index(
                        ctx, func_name, node.target_name, node.index_expr,
                        node.line))

                elif isinstance(node, FuncCallNode):
                    findings.extend(self._check_copy(ctx, func_name, node))

        return findings

    # -----------------------------------------------------------

    def _check_index(self, ctx, func_name, array_name, index_expr, line):
        index = _constant_int(index_expr)
        if index is None:
            return []

        symbol = ctx.lookup(array_name, func_name)
        if symbol is None or symbol.array_size is None:
            return []

        size = symbol.array_size

        if 0 <= index < size:
            return []

        if index < 0:
            message = (
                f"Negative index {index} on array '{array_name}'. This reads "
                f"or writes memory before the start of the buffer."
            )
        else:
            message = (
                f"Index {index} is out of bounds for array '{array_name}', "
                f"which has {size} element(s) with valid indices "
                f"0 to {size - 1}."
            )

        return [Finding(
            rule_id=self.rule_id,
            type=self.name,
            line=line,
            severity=Severity.HIGH,
            message=message,
            suggested_fix=(
                f"Keep the index within 0 to {size - 1}, or declare "
                f"'{array_name}' large enough for the access."
            ),
            function=func_name,
        )]

    def _check_copy(self, ctx, func_name, call):
        if call.name not in COPY_FUNCTIONS or len(call.args) < 2:
            return []

        destination = call.args[0]
        if not isinstance(destination, IdentifierNode):
            return []

        symbol = ctx.lookup(destination.name, func_name)
        if symbol is None or symbol.array_size is None:
            return []

        # Only a literal source lets us prove the overflow.
        source = call.args[1]
        if not (isinstance(source, LiteralNode)
                and source.literal_type == "string"):
            return []

        needed = len(source.value) + 1   # + null terminator
        if needed <= symbol.array_size:
            return []

        return [Finding(
            rule_id=self.rule_id,
            type=self.name,
            line=call.line,
            severity=Severity.HIGH,
            message=(
                f"{call.name}() writes {needed} bytes (a {len(source.value)}"
                f"-character string plus its null terminator) into "
                f"'{destination.name}', which holds only "
                f"{symbol.array_size} bytes. This overflows the buffer."
            ),
            suggested_fix=(
                f"Declare '{destination.name}' with at least {needed} bytes, "
                f"or use snprintf({destination.name}, "
                f"sizeof({destination.name}), ...)."
            ),
            function=func_name,
        )]
