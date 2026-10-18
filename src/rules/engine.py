"""
The security rule engine.

This is the single entry point the GUI calls. It owns the list of rules, runs
each of them over a shared AnalysisContext, and returns the vulnerability
report as a flat list of Finding objects sorted by source line.

Integration contract (agreed with Member 4):

    engine = RuleEngine()
    findings = engine.analyze(ast, symbol_table)
    report = [f.to_dict() for f in findings]

`analyze_source` is a convenience wrapper that runs the whole compiler
pipeline - lexer, parser, semantic analysis, CFG, rules - in one call.
"""

from src.rules.context import AnalysisContext
from src.rules.finding import Finding, Severity

from src.rules.dangerous_functions import DangerousFunctionRule
from src.rules.hardcoded_credentials import HardcodedCredentialRule
from src.rules.unreachable_code import UnreachableCodeRule
from src.rules.uninitialized_vars import UninitializedVariableRule
from src.rules.buffer_overflow import BufferOverflowRule
from src.rules.null_deref import NullDereferenceRule
from src.rules.integer_overflow import IntegerOverflowRule


DEFAULT_RULES = [
    DangerousFunctionRule,
    HardcodedCredentialRule,
    UnreachableCodeRule,
    UninitializedVariableRule,
    BufferOverflowRule,
    NullDereferenceRule,
    IntegerOverflowRule,
]


class RuleEngine:
    """Runs every registered security rule and collects the findings."""

    def __init__(self, rules=None):
        """
        `rules` accepts a list of Rule classes, so a rule can be disabled for
        a demo without editing this file.
        """
        rule_classes = rules if rules is not None else DEFAULT_RULES
        self.rules = [cls() for cls in rule_classes]

        # Rules that raised are recorded rather than propagated: one broken
        # rule should not take down the whole report.
        self.errors = []

    def analyze(self, ast, symbol_table, cfgs=None, source=None):
        """Return a list of Finding, sorted by line then severity."""
        self.errors = []

        ctx = AnalysisContext(ast, symbol_table, cfgs=cfgs, source=source)
        findings = []

        for rule in self.rules:
            try:
                findings.extend(rule.run(ctx))
            except Exception as exc:  # noqa: BLE001 - deliberate isolation
                self.errors.append({
                    "rule_id": rule.rule_id,
                    "error": f"{type(exc).__name__}: {exc}",
                })

        findings.sort(key=Finding.sort_key)
        self.context = ctx
        return findings

    def analyze_source(self, source):
        """
        Run the full pipeline on C source text.

        Returns a dict with every stage's output, which is what the GUI needs
        to populate its tabs. Syntax errors are returned rather than raised so
        the interface can show them instead of crashing.
        """
        from src.lexer.lexer import Lexer, LexerError
        from src.parser.parser import Parser, ParserError
        from src.analysis.semantic_analyzer import SemanticAnalyzer

        result = {
            "ok": False,
            "error": None,
            "tokens": [],
            "ast": None,
            "symbol_table": None,
            "semantic_errors": [],
            "cfgs": {},
            "findings": [],
            "rule_errors": [],
        }

        try:
            tokens = Lexer(source).tokenize()
            result["tokens"] = tokens

            parser = Parser(tokens)
            ast = parser.parse()
            result["ast"] = ast
            if parser.has_errors():
                messages = [f"ParserError: {e}" for e in parser.get_errors()]
                result["error"] = "; ".join(messages)
                return result
        except (LexerError, ParserError) as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
            return result

        analyzer = SemanticAnalyzer()
        symbol_table = analyzer.analyze(ast)

        result["symbol_table"] = symbol_table
        result["semantic_errors"] = analyzer.get_errors()

        findings = self.analyze(ast, symbol_table, source=source)

        result["cfgs"] = self.context.cfgs
        result["findings"] = findings
        result["rule_errors"] = self.errors
        result["ok"] = True

        return result


def summarize(findings):
    """Count findings per severity - handy for a report header."""
    counts = {Severity.HIGH: 0, Severity.MEDIUM: 0, Severity.LOW: 0}
    for finding in findings:
        if finding.severity in counts:
            counts[finding.severity] += 1
    return counts
