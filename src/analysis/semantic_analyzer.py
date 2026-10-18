from src.parser.ast_nodes import (
    ProgramNode,
    VarDeclNode,
    FuncDefNode,
    ParamNode,
    BlockNode,
    AssignNode,
    IfNode,
    WhileNode,
    ForNode,
    ReturnNode,
    ExprStmtNode,
    BinOpNode,
    UnaryOpNode,
    LiteralNode,
    IdentifierNode,
    ArrayAccessNode,
    FuncCallNode,
    InitListNode
)

from src.analysis.symbol_table import SymbolTable


class SemanticAnalyzer:

    def __init__(self):
        self.symbol_table = SymbolTable()
        self.errors = []

    def analyze(self, program):
        """Start semantic analysis of the program."""
        self.visit(program)
        return self.symbol_table

    def get_errors(self):
        """Return all semantic errors."""
        return self.errors

    def add_error(self, error_type, message, line):
        """Add a semantic error."""
        self.errors.append({
            "type": error_type,
            "message": message,
            "line": line
        })

    def visit(self, node):
        """Visit an AST node."""

        if node is None:
            return

        if isinstance(node, ProgramNode):
            self.visit_program(node)

        elif isinstance(node, FuncDefNode):
            self.visit_function(node)

        elif isinstance(node, BlockNode):
            self.visit_block(node)

        elif isinstance(node, VarDeclNode):
            self.visit_variable_declaration(node)

        elif isinstance(node, AssignNode):
            self.visit_assignment(node)

        elif isinstance(node, IfNode):
            self.visit_if(node)

        elif isinstance(node, WhileNode):
            self.visit_while(node)

        elif isinstance(node, ForNode):
            self.visit_for(node)

        elif isinstance(node, ReturnNode):
            self.visit_return(node)

        elif isinstance(node, ExprStmtNode):
            self.visit(node.expr)

        elif isinstance(node, BinOpNode):
            self.visit(node.left)
            self.visit(node.right)

        elif isinstance(node, UnaryOpNode):
            self.visit(node.operand)

        elif isinstance(node, IdentifierNode):
            self.visit_identifier(node)

        elif isinstance(node, ArrayAccessNode):
            self.visit_array_access(node)

        elif isinstance(node, FuncCallNode):
            self.visit_function_call(node)

        elif isinstance(node, InitListNode):
            self.visit_init_list(node)

        elif isinstance(node, LiteralNode):
            pass

    # --------------------------------------------------
    # PROGRAM
    # --------------------------------------------------

    def visit_program(self, node):
        for declaration in node.declarations:
            self.visit(declaration)

    # --------------------------------------------------
    # FUNCTION
    # --------------------------------------------------

    def visit_function(self, node):
        # Enter function scope
        self.symbol_table.enter_scope("function_" + node.name)

        # Add function parameters to function scope
        for param in node.params:
            self.visit_parameter(param)

        # Visit function body statements directly.
        # We don't create another unnecessary scope here.
        for statement in node.body.statements:
            self.visit(statement)

        # Leave function scope
        self.symbol_table.exit_scope()

    def visit_parameter(self, node):
        result = self.symbol_table.declare(
            name=node.name,
            var_type=node.param_type,
            line_declared=node.line,
            is_initialized=True,
            is_pointer=node.is_pointer
        )

        if result is None:
            self.add_error(
                "Redeclaration",
                f"Parameter '{node.name}' redeclared in the same scope",
                node.line
            )

    # --------------------------------------------------
    # BLOCK
    # --------------------------------------------------

    def visit_block(self, node):
        # A normal block creates a new scope.
        self.symbol_table.enter_scope("block_" + str(node.line))

        for statement in node.statements:
            self.visit(statement)

        self.symbol_table.exit_scope()

    # --------------------------------------------------
    # VARIABLE DECLARATION
    # --------------------------------------------------

    def visit_variable_declaration(self, node):
        # First analyze initializer, if one exists.
        if node.init_expr is not None:
            self.visit(node.init_expr)

        initialized = node.init_expr is not None

        result = self.symbol_table.declare(
            name=node.name,
            var_type=node.var_type,
            line_declared=node.line,
            is_initialized=initialized,
            is_pointer=node.is_pointer,
            array_size=node.array_size,
            array_size2=node.array_size2
        )

        if result is None:
            self.add_error(
                "Redeclaration",
                f"Variable '{node.name}' redeclared in the same scope",
                node.line
            )
        else:
            if isinstance(node.init_expr, InitListNode) and node.array_size is not None:
                if len(node.init_expr.elements) > node.array_size:
                    self.add_error(
                        "InitializerOverflow",
                        f"Too many initializer values for array '{node.name}' (expected {node.array_size}, got {len(node.init_expr.elements)})",
                        node.line
                    )

    # --------------------------------------------------
    # ASSIGNMENT
    # --------------------------------------------------

    def visit_assignment(self, node):
        # Analyze array index if present.
        if node.index_expr is not None:
            self.visit(node.index_expr)
        if getattr(node, "index_expr2", None) is not None:
            self.visit(node.index_expr2)

        # Check that the assignment target exists.
        symbol = self.symbol_table.lookup(node.target_name)

        if symbol is None:
            self.add_error(
                "UndeclaredIdentifier",
                f"Identifier '{node.target_name}' is not declared",
                node.line
            )
        else:
            # Analyze the value being assigned.
            self.visit(node.value_expr)

            # Assignment means the variable is initialized.
            self.symbol_table.mark_initialized(node.target_name)

    # --------------------------------------------------
    # IF
    # --------------------------------------------------

    def visit_if(self, node):
        # Analyze condition
        self.visit(node.condition)

        # Then block creates its own scope
        self.visit_block(node.then_block)

        # Else block, if present
        if node.else_block is not None:
            self.visit_block(node.else_block)

    # --------------------------------------------------
    # WHILE
    # --------------------------------------------------

    def visit_while(self, node):
        # Analyze condition
        self.visit(node.condition)

        # Analyze loop body
        self.visit_block(node.body)

    # --------------------------------------------------
    # FOR
    # --------------------------------------------------

    def visit_for(self, node):
        # The for loop gets its own scope.
        self.symbol_table.enter_scope("for_" + str(node.line))

        # Initialization
        if node.init is not None:
            self.visit(node.init)

        # Condition
        if node.condition is not None:
            self.visit(node.condition)

        # Body
        for statement in node.body.statements:
            self.visit(statement)

        # Update
        if node.update is not None:
            self.visit(node.update)

        self.symbol_table.exit_scope()

    # --------------------------------------------------
    # RETURN
    # --------------------------------------------------

    def visit_return(self, node):
        if node.value is not None:
            self.visit(node.value)

    # --------------------------------------------------
    # IDENTIFIER
    # --------------------------------------------------

    def visit_identifier(self, node):
        symbol = self.symbol_table.lookup(node.name)

        if symbol is None:
            self.add_error(
                "UndeclaredIdentifier",
                f"Identifier '{node.name}' is not declared",
                node.line
            )

    # --------------------------------------------------
    # ARRAY ACCESS
    # --------------------------------------------------

    def visit_array_access(self, node):
        # Check that the array exists.
        symbol = self.symbol_table.lookup(node.name)

        if symbol is None:
            self.add_error(
                "UndeclaredIdentifier",
                f"Identifier '{node.name}' is not declared",
                node.line
            )

        # Analyze array index
        self.visit(node.index_expr)
        if getattr(node, "index_expr2", None) is not None:
            self.visit(node.index_expr2)

    # --------------------------------------------------
    # FUNCTION CALL
    # --------------------------------------------------

    def visit_function_call(self, node):
        # Analyze all arguments.
        for argument in node.args:
            self.visit(argument)

    # --------------------------------------------------
    # INIT LIST
    # --------------------------------------------------

    def visit_init_list(self, node):
        for element in node.elements:
            self.visit(element)