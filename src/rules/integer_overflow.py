"""
Rule: arithmetic that does not fit the destination type.

Three checks, ordered by how certain they are. The first two are provable by
constant folding and cannot produce false positives. The third is an
acknowledged heuristic and is reported at MEDIUM rather than HIGH, because
proving it would need value-range analysis across the whole program.

1. A constant expression whose value falls outside the 32-bit signed int
   range - `int x = 2147483647 + 1;`
2. A constant that cannot fit the declared type it is assigned to -
   `char c = 300;`
3. A multiplication of non-constant operands used as an allocation size or a
   memory-copy length, where an overflowing product silently produces a tiny
   allocation followed by a large write.
"""

from src.rules.base import Rule
from src.rules.finding import Finding, Severity
from src.dataflow.expr_utils import parse_c_int_literal
from src.parser.ast_nodes import (
    BinOpNode,
    UnaryOpNode,
    LiteralNode,
    VarDeclNode,
    FuncCallNode,
)
from src.dataflow.expr_utils import walk


INT_MAX = 2 ** 31 - 1
INT_MIN = -(2 ** 31)

# Widest plausible range for a `char`, covering both signed and unsigned.
CHAR_MIN, CHAR_MAX = -128, 255

# Functions whose size/length argument is dangerous to get wrong.
SIZE_FUNCTIONS = {"malloc", "calloc", "alloca", "memcpy", "memset", "realloc"}


def fold(expr):
    """Evaluate a constant integer expression, or return None."""
    if isinstance(expr, LiteralNode) and expr.literal_type == "int":
        try:
            return parse_c_int_literal(expr.value)
        except (TypeError, ValueError):
            return None

    if isinstance(expr, UnaryOpNode):
        value = fold(expr.operand)
        if value is None:
            return None
        if expr.op == "-":
            return -value
        if expr.op == "+":
            return value
        return None

    if isinstance(expr, BinOpNode):
        left = fold(expr.left)
        right = fold(expr.right)

        if left is None or right is None:
            return None

        try:
            if expr.op == "+":
                return left + right
            if expr.op == "-":
                return left - right
            if expr.op == "*":
                return left * right
            if expr.op == "/":
                return left // right if right != 0 else None
            if expr.op == "%":
                return left % right if right != 0 else None
        except (ZeroDivisionError, ValueError):
            return None

    return None


class IntegerOverflowRule(Rule):

    rule_id = "INTEGER_OVERFLOW"
    name = "Integer Overflow"

    def run(self, ctx):
        findings = []

        for func_name, func_node in ctx.functions.items():
            reported_lines = set()

            for node in walk(func_node):

                if isinstance(node, BinOpNode):
                    finding = self._check_constant(node, func_name,
                                                   reported_lines)
                    if finding:
                        findings.append(finding)

                elif isinstance(node, VarDeclNode):
                    finding = self._check_narrowing(node, func_name)
                    if finding:
                        findings.append(finding)

                elif isinstance(node, FuncCallNode):
                    findings.extend(self._check_size_arithmetic(node,
                                                                func_name))

        return findings

    # -----------------------------------------------------------

    def _check_constant(self, node, func_name, reported_lines):
        if node.op not in {"+", "-", "*"}:
            return None

        value = fold(node)
        if value is None or INT_MIN <= value <= INT_MAX:
            return None

        # One report per line, so nested sub-expressions do not each fire.
        if node.line in reported_lines:
            return None
        reported_lines.add(node.line)

        return Finding(
            rule_id=self.rule_id,
            type=self.name,
            line=node.line,
            severity=Severity.HIGH,
            message=(
                f"This constant expression evaluates to {value}, which is "
                f"outside the 32-bit signed int range "
                f"({INT_MIN} to {INT_MAX}). The result wraps around at "
                f"runtime instead of being the value written here."
            ),
            suggested_fix=(
                "Use a wider type such as long long, or restructure the "
                "arithmetic so intermediate values stay in range."
            ),
            function=func_name,
        )

    def _check_narrowing(self, node, func_name):
        if node.var_type != "char" or node.array_size is not None:
            return None
        if node.is_pointer or node.init_expr is None:
            return None

        value = fold(node.init_expr)
        if value is None or CHAR_MIN <= value <= CHAR_MAX:
            return None

        return Finding(
            rule_id=self.rule_id,
            type=self.name,
            line=node.line,
            severity=Severity.MEDIUM,
            message=(
                f"The value {value} does not fit in a char and will be "
                f"truncated when assigned to '{node.name}'."
            ),
            suggested_fix=(
                f"Declare '{node.name}' as an int, or use a value within "
                f"{CHAR_MIN} to {CHAR_MAX}."
            ),
            function=func_name,
        )

    def _check_size_arithmetic(self, call, func_name):
        if call.name not in SIZE_FUNCTIONS:
            return []

        findings = []

        for arg in call.args:
            if not isinstance(arg, BinOpNode) or arg.op != "*":
                continue

            # A fully constant product is checked by _check_constant.
            if fold(arg) is not None:
                continue

            findings.append(Finding(
                rule_id=self.rule_id,
                type=self.name,
                line=call.line,
                severity=Severity.MEDIUM,
                message=(
                    f"The size argument to {call.name}() is a multiplication "
                    f"of values not known at compile time. If the product "
                    f"overflows, {call.name}() receives a small size and the "
                    f"following write runs past the allocation."
                ),
                suggested_fix=(
                    "Check the operands against a maximum before "
                    "multiplying, or use calloc(), which detects overflow "
                    "in its own multiplication."
                ),
                function=func_name,
            ))

        return findings
