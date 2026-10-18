"""Tests for switch/case support.

Covers:
  1. Parser shape — 2-case + default switch produces correct AST.
  2. Parser error — missing 'break;' raises ParserError.
  3. Semantic analysis — switch inside a function passes without errors.
  4. CFG structure — dispatch node has case-labeled edges; all break points
     converge on one SWITCH MERGE node.
"""

import pytest
from src.lexer.lexer import Lexer
from src.parser.parser import Parser, ParserError
from src.parser.ast_nodes import (
    SwitchNode, CaseClauseNode, BreakNode, LiteralNode,
    IdentifierNode, ReturnNode, VarDeclNode,
)
from src.analysis.semantic_analyzer import SemanticAnalyzer
from src.analysis.cfg_builder import CFGBuilder


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def parse_source(src: str):
    tokens = Lexer(src).tokenize()
    parser = Parser(tokens)
    tree = parser.parse()
    return parser, tree


def first_switch(tree) -> SwitchNode:
    """Walk the tree and return the first SwitchNode found."""
    from src.dataflow.expr_utils import walk
    for node in walk(tree):
        if isinstance(node, SwitchNode):
            return node
    raise AssertionError("No SwitchNode found in tree")


# ---------------------------------------------------------------------------
# 1. Parser shape test
# ---------------------------------------------------------------------------

SWITCH_SRC = """
int f(int x) {
    switch (x) {
        case 1:
            int a;
            a = 10;
            break;
        case 2:
            a = 20;
            break;
        default:
            a = 0;
            break;
    }
    return a;
}
"""


def test_switch_parser_shape():
    parser, tree = parse_source(SWITCH_SRC)
    assert not parser.has_errors(), parser.get_errors()

    sw = first_switch(tree)
    assert isinstance(sw, SwitchNode)

    # switch expression is identifier 'x'
    assert isinstance(sw.switch_expr, IdentifierNode)
    assert sw.switch_expr.name == "x"

    # two case clauses
    assert len(sw.cases) == 2

    case1 = sw.cases[0]
    assert isinstance(case1, CaseClauseNode)
    assert isinstance(case1.match_value, LiteralNode)
    assert case1.match_value.value == "1"
    # last stmt in case1 body is BreakNode
    assert isinstance(case1.body[-1], BreakNode)

    case2 = sw.cases[1]
    assert isinstance(case2.match_value, LiteralNode)
    assert case2.match_value.value == "2"
    assert isinstance(case2.body[-1], BreakNode)

    # default body present and ends with BreakNode
    assert sw.default_body is not None
    assert isinstance(sw.default_body[-1], BreakNode)


# ---------------------------------------------------------------------------
# 2. Parser error — missing break
# ---------------------------------------------------------------------------

SWITCH_NO_BREAK = """
int f(int x) {
    switch (x) {
        case 1:
            int a;
            a = 10;
    }
    return 0;
}
"""


def test_switch_missing_break_is_error():
    """A case clause without break; must produce a parser error."""
    parser, tree = parse_source(SWITCH_NO_BREAK)
    assert parser.has_errors(), "Expected a ParserError for missing break"
    err_msgs = " ".join(str(e) for e in parser.get_errors())
    assert "fallthrough" in err_msgs.lower() or "break" in err_msgs.lower()


# ---------------------------------------------------------------------------
# 3. Semantic analysis
# ---------------------------------------------------------------------------

def test_switch_semantic_no_errors():
    parser, tree = parse_source(SWITCH_SRC)
    assert not parser.has_errors()
    sa = SemanticAnalyzer()
    sa.analyze(tree)
    assert sa.get_errors() == [], sa.get_errors()


# ---------------------------------------------------------------------------
# 4. CFG structure
# ---------------------------------------------------------------------------

SWITCH_CFG_SRC = """
int f(int x) {
    switch (x) {
        case 1:
            x = 10;
            break;
        case 2:
            x = 20;
            break;
        default:
            x = 0;
            break;
    }
    return x;
}
"""


def test_switch_cfg_structure():
    parser, tree = parse_source(SWITCH_CFG_SRC)
    assert not parser.has_errors(), parser.get_errors()

    # Find the function node
    func = tree.declarations[0]
    builder = CFGBuilder()
    cfg = builder.build(func)

    # Collect node labels
    labels = {n: data.get("label", "") for n, data in cfg.nodes(data=True)}

    # There must be exactly one SWITCH DISPATCH node and one SWITCH MERGE node
    dispatch_nodes = [n for n, lbl in labels.items() if lbl == "SWITCH DISPATCH"]
    merge_nodes    = [n for n, lbl in labels.items() if lbl == "SWITCH MERGE"]
    assert len(dispatch_nodes) == 1, f"Expected 1 SWITCH DISPATCH, got {dispatch_nodes}"
    assert len(merge_nodes) == 1,    f"Expected 1 SWITCH MERGE, got {merge_nodes}"

    dispatch = dispatch_nodes[0]
    merge    = merge_nodes[0]

    # Edges from dispatch — should include case:1, case:2, default
    out_edges = cfg.out_edges(dispatch, data=True)
    edge_types = {data["edge_type"] for _, _, data in out_edges}
    assert "case:1"  in edge_types, f"Missing case:1 edge, got {edge_types}"
    assert "case:2"  in edge_types, f"Missing case:2 edge, got {edge_types}"
    assert "default" in edge_types, f"Missing default edge, got {edge_types}"

    # All BREAK nodes must have an edge to merge
    break_nodes = [n for n, lbl in labels.items() if lbl == "BREAK"]
    assert len(break_nodes) == 3, f"Expected 3 BREAK nodes (one per clause), got {break_nodes}"
    for bn in break_nodes:
        successors = list(cfg.successors(bn))
        assert merge in successors, (
            f"BREAK node {bn} does not connect to SWITCH MERGE; successors={successors}"
        )

    # The merge node must have an outgoing edge to the return statement
    # (i.e. it is not a dead end — something follows it)
    merge_successors = list(cfg.successors(merge))
    assert len(merge_successors) >= 1, "SWITCH MERGE has no successors"
