"""
The bundle of analysis results every security rule reads from.

Building this object is what makes the rules independent of two awkward
details of the upstream modules:

1. `SymbolTable.lookup()` is useless after analysis finishes. `exit_scope()`
   pops the scope stack, so once `SemanticAnalyzer.analyze()` returns, only
   globals are reachable and every local resolves to None. We therefore build
   our own index from `get_all_symbols()`.

2. Scope ids are flat strings ("global", "function_main", "block_8", "for_5"),
   so the symbol table alone cannot tell us which function a local belongs to.
   We recover that by walking the AST per function and matching declarations
   to Symbol records on (name, line_declared), which is unique per declaration.
   The Symbol record stays the authoritative source of type / array_size /
   is_pointer - we only fix up the ownership the flat scope ids lost.
"""

from src.parser.ast_nodes import VarDeclNode, ParamNode, ArrayAccessNode, AssignNode
from src.analysis.cfg_builder import CFGBuilder
from src.dataflow.expr_utils import walk, functions, global_decls, array_element_name
from src.dataflow.reaching_defs import ReachingDefinitions, Definition
from src.dataflow.definite_assignment import DefiniteAssignment


class AnalysisContext:
    """Everything a rule needs: AST, symbol table, CFGs, and a usable index."""

    def __init__(self, ast, symbol_table, cfgs=None, source=None):
        self.ast = ast
        self.symbol_table = symbol_table
        self.source = source

        # {function_name: networkx.DiGraph}
        self.cfgs = cfgs if cfgs is not None else build_cfgs(ast)

        # {function_name: FuncDefNode}
        self.functions = {fn.name: fn for fn in functions(ast)}

        # Index Symbol records by declaration site so we can resolve locals.
        self._by_site = {}
        for symbol in symbol_table.get_all_symbols():
            self._by_site.setdefault((symbol.name, symbol.line_declared), symbol)

        self.globals = self._index_globals()
        self.locals = {name: self._index_function(fn)
                       for name, fn in self.functions.items()}

        # Data-flow results are solved on demand and cached per function.
        self._reaching = {}
        self._definite = {}

    # -----------------------------------------------------------
    # INDEX CONSTRUCTION
    # -----------------------------------------------------------

    def _index_globals(self):
        index = {}
        for decl in global_decls(self.ast):
            symbol = self._by_site.get((decl.name, decl.line))
            if symbol is not None:
                index[decl.name] = symbol
        return index

    def _index_function(self, func_node):
        """
        Map every variable name declared anywhere inside a function to its
        Symbol. Shadowed names in nested blocks collapse onto the innermost
        declaration seen last - a known Review 1 limitation, and the reason
        we report it rather than silently guessing.
        """
        index = {}
        for node in walk(func_node):
            if isinstance(node, (VarDeclNode, ParamNode)):
                symbol = self._by_site.get((node.name, node.line))
                if symbol is not None:
                    index[node.name] = symbol
        return index

    # -----------------------------------------------------------
    # LOOKUP
    # -----------------------------------------------------------

    def lookup(self, name, function=None):
        """Resolve a variable to its Symbol: locals first, then globals."""
        if function is not None:
            symbol = self.locals.get(function, {}).get(name)
            if symbol is not None:
                return symbol
        return self.globals.get(name)

    def is_local(self, name, function):
        return name in self.locals.get(function, {})

    def param_names(self, function):
        func_node = self.functions.get(function)
        if func_node is None:
            return set()
        return {p.name for p in func_node.params}


    # -----------------------------------------------------------
    # DATA-FLOW
    # -----------------------------------------------------------

    def _entry_state(self, function):
        """
        What is already assigned when a function starts: its parameters, plus
        any global that was given an initialiser at its declaration.
        """
        names = set()
        defs = set()

        func_node = self.functions.get(function)
        cfg = self.cfgs.get(function)
        entry = cfg.graph.get("entry") if cfg is not None else None

        if func_node is not None:
            for param in func_node.params:
                names.add(param.name)
                defs.add(Definition(param.name, param.line, entry))

        for decl in global_decls(self.ast):
            if decl.init_expr is not None:
                names.add(decl.name)
                defs.add(Definition(decl.name, decl.line, entry))

        return names, defs

    def reaching_defs(self, function):
        """Reaching-definitions solution for one function (cached)."""
        if function not in self._reaching:
            _names, defs = self._entry_state(function)
            self._reaching[function] = ReachingDefinitions(
                self.cfgs[function], entry_defs=defs
            )
        return self._reaching[function]

    def definite_assignment(self, function):
        """Definite-assignment solution for one function (cached)."""
        if function not in self._definite:
            names, _defs = self._entry_state(function)
            universe = set(self.locals.get(function, {}))

            func_node = self.functions.get(function)
            if func_node is not None:
                for node in walk(func_node):
                    if isinstance(node, ArrayAccessNode):
                        elem = array_element_name(node.name, node.index_expr, getattr(node, "index_expr2", None))
                        if elem is not None:
                            universe.add(elem)
                    elif isinstance(node, AssignNode) and node.index_expr is not None:
                        elem = array_element_name(node.target_name, node.index_expr, getattr(node, "index_expr2", None))
                        if elem is not None:
                            universe.add(elem)

            self._definite[function] = DefiniteAssignment(
                self.cfgs[function],
                universe=universe,
                entry_assigned=names,
            )
        return self._definite[function]


def build_cfgs(ast):
    """
    Build one CFG per function.

    `CFGBuilder.build()` resets its own state on every call, so a fresh
    builder per function keeps the graphs independent.
    """
    cfgs = {}
    for func_node in functions(ast):
        cfgs[func_node.name] = CFGBuilder().build(func_node)
    return cfgs
