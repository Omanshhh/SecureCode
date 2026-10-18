"""
Tests for the two data-flow analyses.

The important case is the one the symbol table gets wrong: a variable assigned
in only one arm of an if/else. `SymbolTable.is_initialized` reports True for
it; definite assignment must report that it is not assigned on all paths.
"""

from src.lexer.lexer import Lexer
from src.parser.parser import Parser
from src.analysis.semantic_analyzer import SemanticAnalyzer
from src.rules.context import AnalysisContext


BRANCH_SOURCE = """
int main(int flag) {
    int x;
    int y = 0;
    if (flag > 0) {
        x = 5;
    }
    y = x + 1;
    return y;
}
"""


def context_for(source):
    ast = Parser(Lexer(source).tokenize()).parse()
    analyzer = SemanticAnalyzer()
    symbol_table = analyzer.analyze(ast)
    return AnalysisContext(ast, symbol_table), symbol_table


def node_with_statement_on_line(cfg, line):
    """Find the CFG node holding the statement that starts on `line`."""
    for node_id in sorted(cfg.nodes):
        for stmt in cfg.nodes[node_id].get("statements") or []:
            if getattr(stmt, "line", None) == line:
                return node_id
    raise AssertionError(f"no CFG node holds a statement on line {line}")


# ---------------------------------------------------------------
# The headline result
# ---------------------------------------------------------------

def test_symbol_table_is_flow_insensitive():
    """Establishes the baseline this analysis exists to improve on."""
    _ctx, symbol_table = context_for(BRANCH_SOURCE)
    x = [s for s in symbol_table.get_all_symbols() if s.name == "x"][0]

    # Assigned only inside the if, yet the flag says initialised.
    assert x.is_initialized is True


def test_definite_assignment_is_flow_sensitive():
    ctx, _symbol_table = context_for(BRANCH_SOURCE)
    analysis = ctx.definite_assignment("main")
    cfg = ctx.cfgs["main"]

    use_node = node_with_statement_on_line(cfg, 8)   # y = x + 1

    assert analysis.is_assigned(use_node, "y") is True
    assert analysis.is_assigned(use_node, "x") is False


# ---------------------------------------------------------------
# Reaching definitions
# ---------------------------------------------------------------

def test_reaching_definitions_carry_the_branch_definition():
    ctx, _ = context_for(BRANCH_SOURCE)
    reaching = ctx.reaching_defs("main")
    cfg = ctx.cfgs["main"]

    use_node = node_with_statement_on_line(cfg, 8)
    lines = {d.line for d in reaching.reaching(use_node, "x")}

    assert lines == {6}      # x = 5, inside the if


def test_redefinition_kills_the_earlier_definition():
    ctx, _ = context_for("""
int main() {
    int a = 1;
    a = 2;
    return a;
}
""")
    reaching = ctx.reaching_defs("main")
    cfg = ctx.cfgs["main"]

    return_node = node_with_statement_on_line(cfg, 5)
    lines = {d.line for d in reaching.reaching(return_node, "a")}

    assert lines == {4}      # only the second assignment survives


def test_parameters_are_definitions_on_entry():
    ctx, _ = context_for("int f(int n) { return n; }")
    analysis = ctx.definite_assignment("f")
    cfg = ctx.cfgs["f"]

    return_node = node_with_statement_on_line(cfg, 1)
    assert analysis.is_assigned(return_node, "n") is True


# ---------------------------------------------------------------
# Termination
# ---------------------------------------------------------------

def test_nested_loops_reach_a_fixed_point():
    """Back-edges make the solver iterative; it must still terminate."""
    ctx, _ = context_for(open("tests/fixtures/loops.c").read())

    reaching = ctx.reaching_defs("sum_matrix")
    definite = ctx.definite_assignment("sum_matrix")

    assert reaching.iterations > 0
    assert definite.iterations > 0

    # Every node got a solution.
    assert set(reaching.IN) == set(ctx.cfgs["sum_matrix"].nodes)
    assert set(definite.IN) == set(ctx.cfgs["sum_matrix"].nodes)


def test_condition_expressions_reach_the_cfg():
    """
    Regression test for the CFG fix: condition nodes used to carry no
    statements, so a variable read only in `if (x > 0)` was invisible to
    data-flow and every use-in-condition bug was missed.
    """
    ctx, _ = context_for(BRANCH_SOURCE)
    cfg = ctx.cfgs["main"]

    condition_nodes = [
        n for n in cfg.nodes
        if "CONDITION" in (cfg.nodes[n].get("label") or "")
    ]

    assert condition_nodes, "expected at least one condition node"
    for node_id in condition_nodes:
        assert cfg.nodes[node_id].get("statements"), (
            "condition node lost its expression"
        )


def test_array_element_definite_assignment_cases():
    from src.rules.engine import RuleEngine

    engine = RuleEngine()

    # Case 1: arr[3] read with no write anywhere -> flagged
    src1 = """
    int main() {
        int arr[10];
        int x = arr[3];
        return x;
    }
    """
    res1 = engine.analyze_source(src1)
    assert res1["ok"] is True
    uninit1 = [f for f in res1["findings"] if f.rule_id == "UNINITIALIZED_VAR"]
    assert len(uninit1) == 1
    assert "arr[3]" in uninit1[0].message

    # Case 2: arr[3] written, then arr[3] read -> NOT flagged
    src2 = """
    int main() {
        int arr[10];
        arr[3] = 42;
        int x = arr[3];
        return x;
    }
    """
    res2 = engine.analyze_source(src2)
    assert res2["ok"] is True
    uninit2 = [f for f in res2["findings"] if f.rule_id == "UNINITIALIZED_VAR"]
    assert len(uninit2) == 0

    # Case 3: arr[3] written, arr[7] read (different constant index) -> flagged
    src3 = """
    int main() {
        int arr[10];
        arr[3] = 42;
        int x = arr[7];
        return x;
    }
    """
    res3 = engine.analyze_source(src3)
    assert res3["ok"] is True
    uninit3 = [f for f in res3["findings"] if f.rule_id == "UNINITIALIZED_VAR"]
    assert len(uninit3) == 1
    assert "arr[7]" in uninit3[0].message

    # Case 4: arr[3] written, then arr[i] written with non-constant i, then arr[7] read -> NOT flagged
    src4 = """
    int main(int i) {
        int arr[10];
        arr[3] = 42;
        arr[i] = 100;
        int x = arr[7];
        return x;
    }
    """
    res4 = engine.analyze_source(src4)
    assert res4["ok"] is True
    uninit4 = [f for f in res4["findings"] if f.rule_id == "UNINITIALIZED_VAR"]
    assert len(uninit4) == 0
