"""
Rule: a variable read on a path where it was never assigned.

This is the rule that needs real data-flow. It reads the definite-assignment
solution, which is path-sensitive, rather than `SymbolTable.is_initialized`,
which is a single flag meaning "assigned somewhere" and reports True for a
variable assigned in only one arm of an if/else.

Out-parameters
--------------
`char buf[64]; gets(buf);` must not be reported: `gets` writes `buf`. Since we
have no interprocedural analysis, any array or pointer passed bare to a call,
and anything passed with `&`, is treated as possibly written by the callee.
"""

from src.rules.base import Rule
from src.rules.finding import Finding, Severity
from src.parser.ast_nodes import ArrayAccessNode
from src.dataflow.expr_utils import stmt_uses, call_arg_identifiers, find_all, array_element_name


class UninitializedVariableRule(Rule):

    rule_id = "UNINITIALIZED_VAR"
    name = "Uninitialized Variable Use"
    uses_dataflow = True

    def run(self, ctx):
        findings = []

        for func_name in ctx.functions:
            findings.extend(self._run_function(ctx, func_name))

        return findings

    def _run_function(self, ctx, func_name):
        findings = []

        cfg = ctx.cfgs[func_name]
        analysis = ctx.definite_assignment(func_name)
        params = ctx.param_names(func_name)

        reported = set()

        for node_id in sorted(cfg.nodes):
            assigned = analysis.IN.get(node_id, analysis.universe)

            for stmt in cfg.nodes[node_id].get("statements") or []:

                skip = self._out_params(ctx, func_name, stmt)

                for name, line in stmt_uses(stmt):

                    # Only locals are tracked; globals default to zero in C
                    # and parameters arrive assigned.
                    if not ctx.is_local(name, func_name):
                        continue
                    if name in params:
                        continue
                    if name in assigned:
                        continue
                    if name in skip:
                        continue
                    if (name, line) in reported:
                        continue

                    symbol = ctx.lookup(name, func_name)

                    # An array's storage always exists - `int a[3]; a[0] = 1;`
                    # is not a read of an uninitialised value. Only the
                    # elements can be uninitialised, and we do not track the
                    # array element-wise, so arrays are left alone.
                    if symbol is not None and symbol.array_size is not None:
                        continue

                    reported.add((name, line))
                    declared = symbol.line_declared if symbol else None
                    where = f" (declared at line {declared})" if declared else ""

                    findings.append(Finding(
                        rule_id=self.rule_id,
                        type=self.name,
                        line=line,
                        severity=Severity.HIGH,
                        message=(
                            f"Variable '{name}'{where} is read here but is "
                            f"not assigned on every path that reaches this "
                            f"point. Its value is whatever happened to be on "
                            f"the stack."
                        ),
                        suggested_fix=(
                            f"Give '{name}' an initial value at its "
                            f"declaration, or assign it on every branch "
                            f"before this use."
                        ),
                        function=func_name,
                    ))

                # Check array element reads with constant index
                for access in find_all(stmt, ArrayAccessNode):
                    elem_name = array_element_name(access.name, access.index_expr, getattr(access, "index_expr2", None))
                    if elem_name is None:
                        continue
                    if not ctx.is_local(access.name, func_name):
                        continue
                    if access.name in params:
                        continue
                    if access.name in skip:
                        continue
                    if elem_name in assigned:
                        continue
                    if (elem_name, access.line) in reported:
                        continue

                    reported.add((elem_name, access.line))
                    symbol = ctx.lookup(access.name, func_name)
                    declared = symbol.line_declared if symbol else None
                    where = f" (declared at line {declared})" if declared else ""

                    findings.append(Finding(
                        rule_id=self.rule_id,
                        type=self.name,
                        line=access.line,
                        severity=Severity.HIGH,
                        message=(
                            f"Array element '{elem_name}'{where} is read here but is "
                            f"not assigned on every path that reaches this point. "
                            f"Its value is whatever happened to be on the stack."
                        ),
                        suggested_fix=(
                            f"Assign a value to '{elem_name}' before reading it, or "
                            f"initialize the array at its declaration."
                        ),
                        function=func_name,
                    ))

        return findings

    def _out_params(self, ctx, func_name, stmt):
        """Names in `stmt` that a callee might be writing rather than reading."""
        skip = set()

        for name, by_address in call_arg_identifiers(stmt):
            if by_address:
                skip.add(name)
                continue

            symbol = ctx.lookup(name, func_name)
            if symbol is not None and (symbol.array_size is not None
                                       or symbol.is_pointer):
                skip.add(name)

        return skip
