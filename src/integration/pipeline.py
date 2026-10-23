"""
Pipeline integration - Member 4.

Runs the full compiler pipeline (lexer -> parser -> semantic analysis ->
CFG -> data-flow + rule engine) through `RuleEngine.analyze_source` and turns
every stage's Python objects into plain JSON-serialisable data for the GUI
and the test runner.

    from src.integration.pipeline import run_pipeline
    report = run_pipeline(source_text)      # dict, safe for json.dumps
"""

import dataclasses
import time

from src.parser.ast_nodes import (
    ASTNode,
    BinOpNode,
    UnaryOpNode,
    LiteralNode,
    IdentifierNode,
    ArrayAccessNode,
    FuncCallNode,
    InitListNode,
)
from src.rules.engine import RuleEngine
from src.rules.finding import Severity


# Weight of each severity in the 0-100 risk score shown in the GUI.
SEVERITY_WEIGHT = {Severity.HIGH: 35, Severity.MEDIUM: 15, Severity.LOW: 5}


# ---------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------

def serialize_tokens(tokens):
    return [
        {
            "index": index,
            "type": token.type.name,
            "lexeme": token.value,
            "line": token.line,
            "column": token.column,
        }
        for index, token in enumerate(tokens)
    ]


# ---------------------------------------------------------------
# AST
# ---------------------------------------------------------------

def _is_node(value):
    return isinstance(value, ASTNode)


def serialize_ast(node):
    """
    Convert an AST node into a tree of dicts:

        {"node": "VarDeclNode", "attrs": {...scalars...},
         "children": [{"field": "init_expr", "nodes": [...]}]}

    Scalar fields go in `attrs`, node-valued fields in `children`, so the GUI
    can render the tree without knowing the node classes.
    """
    if node is None:
        return None

    attrs = {}
    children = []

    for field in dataclasses.fields(node):
        value = getattr(node, field.name)

        if _is_node(value):
            children.append({"field": field.name, "nodes": [serialize_ast(value)]})
        elif isinstance(value, list) and (not value or _is_node(value[0])):
            children.append({
                "field": field.name,
                "nodes": [serialize_ast(item) for item in value],
            })
        else:
            attrs[field.name] = value

    return {"node": type(node).__name__, "attrs": attrs, "children": children}


def pretty_ast(node, indent=0):
    """Indented text form of the AST, one node per line."""
    pad = "  " * indent

    if node is None:
        return f"{pad}None"

    scalars = []
    nested = []
    for field in dataclasses.fields(node):
        value = getattr(node, field.name)
        if _is_node(value) or (isinstance(value, list) and (not value or _is_node(value[0]))):
            nested.append((field.name, value))
        else:
            scalars.append(f"{field.name}={value!r}")

    lines = [f"{pad}{type(node).__name__}({', '.join(scalars)})"]
    for name, value in nested:
        lines.append(f"{pad}  {name}:")
        items = value if isinstance(value, list) else [value]
        for item in items:
            lines.append(pretty_ast(item, indent + 2))
    return "\n".join(lines)


def expr_to_c(expr):
    """Render an expression node back to compact C text (for CFG labels)."""
    if expr is None:
        return ""
    if isinstance(expr, BinOpNode):
        return f"{expr_to_c(expr.left)} {expr.op} {expr_to_c(expr.right)}"
    if isinstance(expr, UnaryOpNode):
        return f"{expr.op}{expr_to_c(expr.operand)}"
    if isinstance(expr, LiteralNode):
        return f'"{expr.value}"' if expr.literal_type == "string" else str(expr.value)
    if isinstance(expr, IdentifierNode):
        return expr.name
    if isinstance(expr, ArrayAccessNode):
        return f"{expr.name}[{expr_to_c(expr.index_expr)}]"
    if isinstance(expr, FuncCallNode):
        return f"{expr.name}({', '.join(expr_to_c(a) for a in expr.args)})"
    if isinstance(expr, InitListNode):
        return "{" + ", ".join(expr_to_c(e) for e in expr.elements) + "}"
    return type(expr).__name__.replace("Node", "")


# ---------------------------------------------------------------
# Symbol table
# ---------------------------------------------------------------

def serialize_symbols(symbol_table):
    if symbol_table is None:
        return []

    rows = []
    for symbol in symbol_table.get_all_symbols():
        type_name = symbol.type + ("*" if symbol.is_pointer else "")
        if symbol.array_size is not None:
            type_name += f"[{symbol.array_size}]"
        rows.append({
            "name": symbol.name,
            "type": type_name,
            "scope": symbol.scope_id,
            "line": symbol.line_declared,
            "initialized": bool(symbol.is_initialized),
            "is_pointer": bool(symbol.is_pointer),
            "array_size": symbol.array_size,
        })
    return rows


# ---------------------------------------------------------------
# CFG
# ---------------------------------------------------------------

def _node_detail(data):
    condition = data.get("condition")
    if condition is not None:
        return expr_to_c(condition)

    parts = []
    for stmt in data.get("statements") or []:
        kind = type(stmt).__name__.replace("Node", "")
        line = getattr(stmt, "line", None)
        parts.append(f"{kind} | line {line}" if line else kind)
    return "; ".join(parts)


def _dot_escape(text):
    return str(text).replace("\\", "\\\\").replace('"', '\\"')


def serialize_cfg(graph):
    nodes = []
    for node_id in sorted(graph.nodes):
        data = graph.nodes[node_id]
        lines = sorted({
            getattr(stmt, "line", 0)
            for stmt in data.get("statements") or []
            if getattr(stmt, "line", 0)
        })
        nodes.append({
            "id": node_id,
            "label": data.get("label", f"Block {node_id}"),
            "detail": _node_detail(data),
            "lines": lines,
        })

    edges = [
        {"source": src, "target": dst, "type": data.get("edge_type", "normal")}
        for src, dst, data in graph.edges(data=True)
    ]

    return {"nodes": nodes, "edges": edges, "dot": cfg_to_dot(nodes, edges)}


EDGE_STYLE = {
    "true": 'color="#2f7d4f", fontcolor="#2f7d4f"',
    "false": 'color="#b3261e", fontcolor="#b3261e"',
    "back": 'color="#7a5af5", fontcolor="#7a5af5", style=dashed',
}


def cfg_to_dot(nodes, edges):
    out = [
        "digraph CFG {",
        "  rankdir=TB;",
        "  node [shape=box];",
        '  node [fontname="JetBrains Mono", fontsize=11, margin="0.15,0.06"];',
        '  edge [fontname="Space Mono", fontsize=9, arrowsize=0.7];',
        "  ranksep=0.35;",
    ]
    for node in nodes:
        label = node["label"]
        if node["detail"]:
            label += "\\n" + _dot_escape(node["detail"])
        out.append(f'  n{node["id"]} [label="{label}"];')
    for edge in edges:
        style = EDGE_STYLE.get(edge["type"], "")
        extra = f", {style}" if style else ""
        out.append(f'  n{edge["source"]} -> n{edge["target"]} [label="{edge["type"]}"{extra}];')
    out.append("}")
    return "\n".join(out)


# ---------------------------------------------------------------
# Whole pipeline
# ---------------------------------------------------------------

def risk_score(findings):
    return min(100, sum(SEVERITY_WEIGHT.get(f.severity, 0) for f in findings))


def run_pipeline(source):
    """Run every stage and return a JSON-ready report dict."""
    started = time.perf_counter()
    result = RuleEngine().analyze_source(source)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

    findings = result["findings"]
    counts = {Severity.HIGH: 0, Severity.MEDIUM: 0, Severity.LOW: 0}
    for finding in findings:
        if finding.severity in counts:
            counts[finding.severity] += 1

    ast = result["ast"]
    functions = sorted(result["cfgs"].keys())

    return {
        "ok": result["ok"],
        "error": result["error"],
        "elapsed_ms": elapsed_ms,
        "tokens": serialize_tokens(result["tokens"]),
        "ast": serialize_ast(ast),
        "ast_text": pretty_ast(ast) if ast is not None else "",
        "symbols": serialize_symbols(result["symbol_table"]),
        "semantic_errors": result["semantic_errors"],
        "cfgs": {name: serialize_cfg(result["cfgs"][name]) for name in functions},
        "findings": [f.to_dict() for f in findings],
        "rule_errors": result["rule_errors"],
        "summary": {
            "risk_score": risk_score(findings),
            "counts": counts,
            "total": len(findings),
            "functions": len(functions),
        },
    }
