"""
Definite-assignment analysis.

A forward "must" data-flow analysis - the companion to reaching definitions,
and the one that actually answers "could this variable be read before it is
ever written?".

    ASSIGNED_IN[n]  = intersection of ASSIGNED_OUT[p] for every predecessor p
    ASSIGNED_OUT[n] = ASSIGNED_IN[n] union DEF[n]

The meet operator is *intersection*, not union: a variable is only definitely
assigned at n if it was assigned on **every** path reaching n. A variable
written in just one arm of an if/else is therefore not definitely assigned
after the merge, which is exactly the bug we want to catch.

Why this is not redundant with the symbol table
-----------------------------------------------
`SymbolTable.is_initialized` is a single flag set by `mark_initialized()` and
never reset, so it means "assigned somewhere in the program". It reports True
for a variable assigned only inside an `if`. This analysis is path-sensitive
and reports the truth.

Initialisation subtlety
-----------------------
For a "must" analysis the optimistic starting point is the **universe** of all
variables, not the empty set. Starting every node at empty makes the first
intersection empty and the solution collapses to empty everywhere - the
analysis would then report every single use as uninitialised. Nodes start at
universe (top) and shrink to the fixed point; only the entry node starts at
the genuinely-assigned set.
"""

from collections import deque

from src.dataflow.expr_utils import stmt_defs, stmt_uses


class DefiniteAssignment:
    """Solves definite assignment for a single function's CFG."""

    def __init__(self, cfg, universe, entry_assigned=None):
        self.cfg = cfg
        self.entry = cfg.graph.get("entry")
        self.universe = frozenset(universe)
        self.entry_assigned = frozenset(entry_assigned or ())

        self.defs = {}
        self.IN = {}
        self.OUT = {}
        self.iterations = 0

        self._build_defs()
        self._solve()

    def _build_defs(self):
        # Collect all pseudo-names for each array in the universe
        array_elems = {}
        for name in self.universe:
            if "[" in name and name.endswith("]"):
                base = name.split("[", 1)[0]
                array_elems.setdefault(base, set()).add(name)

        for node_id in self.cfg.nodes:
            defined = set()
            for stmt in self.cfg.nodes[node_id].get("statements") or []:
                for name, _line in stmt_defs(stmt):
                    if name.startswith("__ANY_ELEM__:"):
                        base = name.split(":", 1)[1]
                        defined.update(array_elems.get(base, set()))
                    else:
                        defined.add(name)
            self.defs[node_id] = defined

    def _solve(self):
        for node_id in self.cfg.nodes:
            if node_id == self.entry:
                self.IN[node_id] = set(self.entry_assigned)
                self.OUT[node_id] = set(self.entry_assigned) | self.defs[node_id]
            else:
                # Optimistic start: assume everything is assigned, then shrink.
                self.IN[node_id] = set(self.universe)
                self.OUT[node_id] = set(self.universe)

        worklist = deque(sorted(self.cfg.nodes))
        queued = set(worklist)

        while worklist:
            self.iterations += 1
            node_id = worklist.popleft()
            queued.discard(node_id)

            if node_id == self.entry:
                incoming = set(self.entry_assigned)
            else:
                preds = list(self.cfg.predecessors(node_id))

                if not preds:
                    # Unreachable node. Intersection over no paths is the
                    # universe, so dead code raises no uninitialised-use
                    # findings - it is already reported as unreachable.
                    incoming = set(self.universe)
                else:
                    incoming = set(self.OUT[preds[0]])
                    for pred in preds[1:]:
                        incoming &= self.OUT[pred]

            self.IN[node_id] = incoming
            new_out = incoming | self.defs[node_id]

            if new_out != self.OUT[node_id]:
                self.OUT[node_id] = new_out

                for succ in self.cfg.successors(node_id):
                    if succ not in queued:
                        worklist.append(succ)
                        queued.add(succ)

    # -----------------------------------------------------------
    # QUERIES / PRESENTATION
    # -----------------------------------------------------------

    def is_assigned(self, node_id, var):
        """True if `var` is assigned on every path reaching `node_id`."""
        return var in self.IN.get(node_id, self.universe)

    def uninitialized_uses(self, is_tracked):
        """
        Yield (var, line, node_id) for each read of a variable that is not
        definitely assigned at that point.

        `is_tracked(name)` decides which names are in scope for this check,
        so callers can exclude globals and function names.
        """
        for node_id in sorted(self.cfg.nodes):
            assigned = self.IN.get(node_id, self.universe)

            for stmt in self.cfg.nodes[node_id].get("statements") or []:
                for name, line in stmt_uses(stmt):
                    if not is_tracked(name):
                        continue
                    if name not in assigned:
                        yield name, line, node_id

    def table(self):
        rows = []
        for node_id in sorted(self.cfg.nodes):
            data = self.cfg.nodes[node_id]
            rows.append({
                "node": node_id,
                "label": data.get("label", ""),
                "def": sorted(self.defs[node_id]),
                "in": sorted(self.IN[node_id]),
                "out": sorted(self.OUT[node_id]),
            })
        return rows

    def format_table(self):
        rows = self.table()
        header = (f"{'Node':<6}{'Label':<16}{'DEF':<12}"
                  f"{'ASSIGNED_IN':<30}ASSIGNED_OUT")
        lines = [header, "-" * len(header)]

        for row in rows:
            lines.append(
                f"{row['node']:<6}{row['label'][:15]:<16}"
                f"{','.join(row['def'])[:11]:<12}"
                f"{','.join(row['in'])[:29]:<30}"
                f"{','.join(row['out'])}"
            )

        lines.append(f"\nFixed point reached after {self.iterations} node visits.")
        return "\n".join(lines)
