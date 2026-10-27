"""
Show Member 3's part of the pipeline for ANY C file.

The web GUI displays the findings but not the data-flow tables behind them.
This script prints everything, in presentation order:

  1. The source, with line numbers
  2. The security report (rule engine output)
  3. Per function: the CFG, reaching definitions, definite assignment
  4. Symbol table vs data-flow: where the flow-insensitive flag is wrong

Usage, from the repository root:

    python scratch/show_dataflow.py test_cases/13_demo_path_sensitivity.c
    python scratch/show_dataflow.py test_cases/11_demo_all_rules.c process
    python scratch/show_dataflow.py my_code.c --report-only

Output is plain ASCII so it prints on a Windows console.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.rules.engine import RuleEngine, summarize   # noqa: E402
from src.dataflow.expr_utils import stmt_uses        # noqa: E402


def banner(title):
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def show_source(lines):
    banner("1. SOURCE")
    for number, text in enumerate(lines, start=1):
        print(f"{number:>4} | {text}")


def show_report(findings, lines):
    banner("2. SECURITY REPORT  (rule engine output)")
    if not findings:
        print("\n  No vulnerabilities found.")
        return

    for f in findings:
        where = f" in {f.function}()" if f.function else ""
        code = lines[f.line - 1].strip() if 0 < f.line <= len(lines) else ""
        print()
        print(f"  [{f.severity}] line {f.line}{where}: {f.type}")
        print(f"    code : {code}")
        print(f"    why  : {f.message}")
        print(f"    fix  : {f.suggested_fix}")

    counts = summarize(findings)
    print()
    print(f"  Total {len(findings)}:  HIGH {counts['HIGH']}  |  "
          f"MEDIUM {counts['MEDIUM']}  |  LOW {counts['LOW']}")


def show_cfg(cfg):
    print("\nControl-flow graph  (node -> successors, edge type)")
    print("-" * 78)
    for node_id in sorted(cfg.nodes):
        label = cfg.nodes[node_id].get("label", "")
        stmts = cfg.nodes[node_id].get("statements") or []
        line = getattr(stmts[0], "line", "") if stmts else ""
        succ = ", ".join(
            f"{s}({cfg.edges[node_id, s].get('edge_type')})"
            for s in cfg.successors(node_id)
        ) or "(none)"
        at = f"line {line}" if line else ""
        print(f"  {node_id:<4}{label:<18}{at:<10}-> {succ}")


def show_function(ctx, function):
    banner(f"3. DATA-FLOW ANALYSIS  -  {function}()")

    show_cfg(ctx.cfgs[function])

    print("\nReaching definitions  -  forward MAY analysis, UNION at merge points")
    print("  IN[n]  = union of OUT[p] over predecessors p")
    print("  OUT[n] = GEN[n] + (IN[n] - KILL[n])")
    print("-" * 78)
    print(ctx.reaching_defs(function).format_table())

    print("\nDefinite assignment  -  forward MUST analysis, INTERSECTION at merge points")
    print("  ASSIGNED_IN[n]  = intersection of ASSIGNED_OUT[p] over predecessors p")
    print("  ASSIGNED_OUT[n] = ASSIGNED_IN[n] + DEF[n]")
    print("-" * 78)
    print(ctx.definite_assignment(function).format_table())


def show_contrast(ctx, function):
    """Compare the symbol table's single flag against the per-path answer."""
    banner(f"4. SYMBOL TABLE vs DATA-FLOW  -  {function}()")

    cfg = ctx.cfgs[function]
    analysis = ctx.definite_assignment(function)
    params = ctx.param_names(function)

    # For every read of a local, is it assigned on every path to that read?
    unsafe_reads = {}
    for node_id in sorted(cfg.nodes):
        assigned = analysis.IN.get(node_id, analysis.universe)
        for stmt in cfg.nodes[node_id].get("statements") or []:
            for name, line in stmt_uses(stmt):
                if name not in assigned:
                    unsafe_reads.setdefault(name, set()).add(line)

    print()
    print(f"  {'Variable':<12}{'Symbol table':<22}Data-flow (path-sensitive)")
    print(f"  {'':<12}{'is_initialized':<22}")
    print("  " + "-" * 74)

    disagreements = 0
    for name, symbol in sorted(ctx.locals.get(function, {}).items()):
        if name in params:
            verdict = "parameter - assigned on entry"
        elif symbol.array_size is not None:
            verdict = "array - tracked per constant index"
        elif name in unsafe_reads:
            lines = ", ".join(str(n) for n in sorted(unsafe_reads[name]))
            verdict = f"NOT assigned on every path (read at line {lines})"
            if symbol.is_initialized:
                verdict += "   <-- symbol table is WRONG"
                disagreements += 1
        else:
            verdict = "assigned on every path before use"

        print(f"  {name:<12}{str(symbol.is_initialized):<22}{verdict}")

    print()
    if disagreements:
        print(f"  The symbol table's flag means 'assigned somewhere'. Data-flow")
        print(f"  intersects facts at merge points, so it catches {disagreements} "
              f"variable(s) the flag misses.")
    else:
        print("  No disagreement in this function.")


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    report_only = "--report-only" in argv

    if not args:
        print(__doc__)
        return 2

    path = args[0]
    only_function = args[1] if len(args) > 1 else None

    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    lines = source.splitlines()

    engine = RuleEngine()
    result = engine.analyze_source(source)

    show_source(lines)

    if not result["ok"]:
        banner("SYNTAX ERROR")
        print(f"\n  {result['error']}")
        return 1

    show_report(result["findings"], lines)
    if report_only:
        return 0

    ctx = engine.context
    functions = [only_function] if only_function else list(ctx.functions)

    for function in functions:
        if function not in ctx.functions:
            print(f"\nNo function named '{function}'. "
                  f"Available: {', '.join(ctx.functions)}")
            return 1
        show_function(ctx, function)
        show_contrast(ctx, function)

    if result["rule_errors"]:
        banner("RULE ERRORS")
        for err in result["rule_errors"]:
            print(f"  {err['rule_id']}: {err['error']}")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
