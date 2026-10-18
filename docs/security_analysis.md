# Data-Flow Analysis and Security Rule Engine

Member 3's component. It occupies the last two stages of the project pipeline:

```
Source -> Lexer -> Parser/AST -> Semantic Analysis + Symbol Table -> CFG
       -> [ Data-Flow Analysis ] -> [ Security Rule Engine ] -> Vulnerability Report
```

## Module map

| File | Purpose |
|---|---|
| `src/dataflow/expr_utils.py` | AST traversal; extracts variable *definitions* and *uses* from a statement |
| `src/dataflow/reaching_defs.py` | Reaching definitions - forward "may" analysis, worklist to fixed point |
| `src/dataflow/definite_assignment.py` | Definite assignment - forward "must" analysis, intersection at joins |
| `src/rules/context.py` | `AnalysisContext`: bundles AST, symbol table, CFGs, and the data-flow solutions |
| `src/rules/finding.py` | `Finding` - the vulnerability report record |
| `src/rules/engine.py` | `RuleEngine` - runs every rule, returns the report |
| `src/rules/*.py` | One module per security rule |
| `tests/fixtures/*.c` | Seeded validation corpus (10 files) |

## Integration contract

This is the API the GUI calls. It is stable; changes will be announced.

```python
from src.rules.engine import RuleEngine

engine = RuleEngine()

# Option A - you already have the AST and symbol table:
findings = engine.analyze(ast, symbol_table)

# Option B - one call for the whole pipeline:
result = engine.analyze_source(source_text)
```

`analyze_source` returns:

| Key | Contents |
|---|---|
| `ok` | `False` if the source failed to lex or parse |
| `error` | The lexer/parser error message, or `None` |
| `tokens` | Token list from the lexer |
| `ast` | `ProgramNode` |
| `symbol_table` | `SymbolTable` |
| `semantic_errors` | List of dicts from `SemanticAnalyzer.get_errors()` |
| `cfgs` | `{function_name: networkx.DiGraph}` |
| `findings` | `list[Finding]`, sorted by line then severity |
| `rule_errors` | Rules that raised, if any - the rest of the report still returns |

Each `Finding` serialises with `.to_dict()` to exactly these keys, which are
the columns of the vulnerability report table:

```python
{
    "rule_id":       "BUFFER_OVERFLOW",
    "type":          "Buffer Overflow",
    "line":          16,
    "severity":      "HIGH",          # HIGH | MEDIUM | LOW
    "message":       "...",           # what is wrong
    "suggested_fix": "...",           # recommended corrective action
    "function":      "handle_request" # or None for file scope
}
```

Syntax errors are returned rather than raised, so the interface can display
them instead of crashing.

## The data-flow equations

Both analyses are solved with a worklist algorithm that iterates until nothing
changes. `CFGBuilder` places at most one statement in each CFG node, so GEN and
KILL are computed per statement and no intra-node ordering is needed.

**Reaching definitions** - forward, union at joins ("may"):

```
IN[n]  = union of OUT[p] for every predecessor p of n
OUT[n] = GEN[n] union (IN[n] - KILL[n])
```

Answers "which assignment could this value have come from", which is what the
null-dereference rule needs.

**Definite assignment** - forward, intersection at joins ("must"):

```
ASSIGNED_IN[n]  = intersection of ASSIGNED_OUT[p] for every predecessor p
ASSIGNED_OUT[n] = ASSIGNED_IN[n] union DEF[n]
```

Answers "is this variable assigned on *every* path to here", which is what
uninitialised-use detection needs.

Two initialisation details matter:

- Non-entry nodes start at the **universe** of variable names, not the empty
  set. Starting empty makes the first intersection empty and the solution
  collapses everywhere, which would report every use as uninitialised.
- A node with no predecessors takes the universe, so unreachable code raises no
  uninitialised-use findings. It is already reported as unreachable.

### Why this is not redundant with the symbol table

`SymbolTable.is_initialized` is a single flag set by `mark_initialized()` and
never reset, so it means "assigned somewhere in the program". For

```c
int total;
if (flag > 0) { total = flag * 2; }
result = total + 1;        /* total may be garbage here */
```

the symbol table reports `total.is_initialized == True` and the semantic
analyzer reports no error. The definite-assignment analysis computes
`ASSIGNED_IN = {flag}` at the use and correctly reports the bug.

Run `python scratch/demo_review1.py` to see this side by side.

## Rules implemented

| Rule ID | Category | Severity | Needs data-flow |
|---|---|---|---|
| `DANGEROUS_FUNC` | Dangerous function usage | HIGH / MEDIUM / LOW | no |
| `HARDCODED_CREDENTIAL` | Hardcoded credentials | HIGH / MEDIUM | no |
| `UNREACHABLE_CODE` | Unreachable code | LOW | CFG only |
| `BUFFER_OVERFLOW` | Buffer overflow | HIGH | no |
| `INTEGER_OVERFLOW` | Integer overflow | HIGH / MEDIUM | no |
| `UNINITIALIZED_VAR` | Uninitialized variable use | HIGH | **yes** |
| `NULL_DEREFERENCE` | Null pointer dereference | HIGH | **yes** |

All seven categories from the project proposal are covered.

## Validation

```bash
python -m pytest          # 45 tests
python scratch/demo_review1.py
```

Over the 10-file seeded corpus: **23 findings, 0 false positives on the 2 clean
files**. `tests/test_rules.py` asserts the exact `(rule_id, line, severity)` set
for every fixture, so a regression fails the build rather than going unnoticed.

## Known limitations

Stated deliberately rather than left to surface during a demo.

- **No interprocedural analysis.** Each function is analysed on its own CFG.
  A variable passed by address, or an array or pointer passed to a call, is
  assumed possibly written by the callee, so `gets(buf)` is not reported as a
  read of an uninitialised variable. This trades false negatives for no false
  positives.
- **Arrays and elements.** Constant-index array elements (e.g. `arr[3]`, `grid[1][2]`)
  ARE now tracked per-element with full path-sensitivity via synthetic pseudo-names.
  A non-constant write (e.g. `arr[i] = ...`) conservatively marks all known elements
  of that array assigned (sound, no false positives, though may miss bugs reached only
  through symbolic writes). Non-constant-index reads still fall back to whole-array
  "was it ever written" reasoning. Full runtime-index tracking across loops and pointer
  arithmetic is undecidable in general and out of scope, same as GCC/Clang's own
  uninitialized-variable analysis.
- **Writes through pointers are not analysable.** `docs/grammar.md` defines an
  assignment target as `IDENTIFIER ('[' expr ']')?`, so `*p = 5;` does not
  parse. The null-dereference rule covers reads (`x = *p`, `p[i]`) only.
- **Runtime indices are out of scope for buffer overflow.** Only constant
  subscripts and provable string-literal copies are reported. A loop that runs
  one past the end needs interval analysis.
- **Shadowed names collapse.** Scope ids in the symbol table are flat strings,
  so a name declared in two nested blocks of one function resolves to the
  innermost declaration seen last.

## Change made to a shared file

`src/analysis/cfg_builder.py` - condition nodes (`IF CONDITION`,
`WHILE CONDITION`, `FOR CONDITION`) were created with `statements=[]`, so the
condition expression never reached the graph and a variable read only in
`if (x > 0)` was invisible to data-flow. The three sites now attach the
expression to `statements` and to a `condition` node attribute. Covered by
`tests/test_dataflow.py::test_condition_expressions_reach_the_cfg`.
