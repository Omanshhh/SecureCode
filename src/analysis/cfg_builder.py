import networkx as nx

from src.parser.ast_nodes import (
    BlockNode,
    VarDeclNode,
    AssignNode,
    IfNode,
    WhileNode,
    DoWhileNode,
    ForNode,
    ReturnNode,
    ExprStmtNode,
    BreakNode,
    CaseClauseNode,
    SwitchNode,
)


class CFGBuilder:

    def __init__(self):
        self.graph = nx.DiGraph()
        self.node_counter = 0
        self._break_target = None  # Set to a merge_node when inside a switch

    def new_node(self, statements=None, label=None):
        """Create a new CFG node."""

        node_id = self.node_counter
        self.node_counter += 1

        if statements is None:
            statements = []

        self.graph.add_node(
            node_id,
            statements=statements,
            label=label if label is not None else f"Block {node_id}"
        )

        return node_id

    def add_edge(self, source, target, edge_type="normal"):
        """Add an edge between two CFG nodes."""

        self.graph.add_edge(
            source,
            target,
            edge_type=edge_type
        )

    def build(self, function_node):
        """Build CFG for a function."""

        self.graph = nx.DiGraph()
        self.node_counter = 0

        entry = self.new_node(label="ENTRY")

        exit_node = self.new_node(label="EXIT")

        self.graph.graph["entry"] = entry
        self.graph.graph["exit"] = exit_node
        self.graph.graph["function"] = function_node.name

        first_node, last_nodes = self.build_block(function_node.body)

        if first_node is not None:
            self.add_edge(entry, first_node)

            for item in last_nodes:
                if isinstance(item, tuple):
                    node, edge_type = item
                    self.add_edge(node, exit_node, edge_type=edge_type)
                else:
                    self.add_edge(item, exit_node)

    # Return statements terminate the function.
            for node, data in self.graph.nodes(data=True):
                if data.get("label") == "RETURN":
                    self.add_edge(node, exit_node)

        else:
            self.add_edge(entry, exit_node)
    
        return self.graph

    def build_block(self, block):
        """
        Build CFG for a block.

        Returns:
            first node
            list of nodes where control can continue
        """

        first_node = None
        current_nodes = []

        for statement in block.statements:

            statement_first, statement_last = self.build_statement(
                statement
            )

            if statement_first is None:
                continue

            if first_node is None:
                first_node = statement_first

            # Connect previous statements to current statement.
            for item in current_nodes:
                if isinstance(item, tuple):
                    node, edge_type = item
                    self.add_edge(node, statement_first, edge_type=edge_type)
                else:
                    self.add_edge(item, statement_first)

            current_nodes = statement_last

        return first_node, current_nodes

    def build_statement(self, statement):

        # ---------------------------------------------
        # SIMPLE STATEMENTS
        # ---------------------------------------------

        if isinstance(
            statement,
            (VarDeclNode, AssignNode, ExprStmtNode)
        ):
            node = self.new_node(
                statements=[statement]
            )

            return node, [node]

        # ---------------------------------------------
        # RETURN
        # ---------------------------------------------

        if isinstance(statement, ReturnNode):

            node = self.new_node(
                statements=[statement],
                label="RETURN"
            )

            # Return does not continue to the next statement.
            return node, []

        # ---------------------------------------------
        # IF / ELSE
        # ---------------------------------------------

        if isinstance(statement, IfNode):

            # The condition expression is attached to the node so that
            # data-flow analysis can see the variables it reads.
            # A condition is pure USE: it never defines a variable.
            condition_node = self.new_node(
                statements=[statement.condition] if statement.condition is not None else [],
                label="IF CONDITION"
            )

            self.graph.nodes[condition_node]["condition"] = statement.condition

            then_first, then_last = self.build_block(
                statement.then_block
            )

            # THEN branch
            if then_first is not None:
                self.add_edge(
                    condition_node,
                    then_first,
                    edge_type="true"
                )
            else:
                then_last = [(condition_node, "true")]

            # ELSE branch
            if statement.else_block is not None:

                # Special case:
                # else { if (...) { ... } }
                # This is how the parser represents else-if.
                if (
                    len(statement.else_block.statements) == 1
                    and isinstance(
                        statement.else_block.statements[0],
                        IfNode
                    )
                ):
                    else_if = statement.else_block.statements[0]

                    else_first, else_last = self.build_statement(
                        else_if
                    )

                else:
                    else_first, else_last = self.build_block(
                        statement.else_block
                    )

                if else_first is not None:
                    self.add_edge(
                        condition_node,
                        else_first,
                        edge_type="false"
                    )
                else:
                    else_last = [(condition_node, "false")]

            else:
                else_last = [(condition_node, "false")]

            # If both branches never return control (e.g. both return from function)
            if not then_last and not else_last:
                return condition_node, []

            # Merge point
            merge_node = self.new_node(
                statements=[],
                label="IF MERGE"
            )

            for item in then_last:
                if isinstance(item, tuple):
                    node, edge_type = item
                    self.add_edge(node, merge_node, edge_type=edge_type)
                else:
                    self.add_edge(item, merge_node)

            for item in else_last:
                if isinstance(item, tuple):
                    node, edge_type = item
                    self.add_edge(node, merge_node, edge_type=edge_type)
                else:
                    self.add_edge(item, merge_node)

            return condition_node, [merge_node]

        # ---------------------------------------------
        # WHILE LOOP
        # ---------------------------------------------

        if isinstance(statement, WhileNode):

            # The condition expression is attached to the node so that
            # data-flow analysis can see the variables it reads.
            # A condition is pure USE: it never defines a variable.
            condition_node = self.new_node(
                statements=[statement.condition] if statement.condition is not None else [],
                label="WHILE CONDITION"
            )

            self.graph.nodes[condition_node]["condition"] = statement.condition

            body_first, body_last = self.build_block(
                statement.body
            )

            # True → loop body
            if body_first is not None:
                self.add_edge(
                    condition_node,
                    body_first,
                    edge_type="true"
                )

                # Body → condition
                for item in body_last:
                    if isinstance(item, tuple):
                        node = item[0]
                    else:
                        node = item
                    self.add_edge(
                        node,
                        condition_node,
                        edge_type="back"
                    )

            # False → next statement
            return condition_node, [(condition_node, "false")]

        # ---------------------------------------------
        # DO-WHILE LOOP
        # ---------------------------------------------

        if isinstance(statement, DoWhileNode):

            # The body executes first, unconditionally.
            body_first, body_last = self.build_block(
                statement.body
            )

            # The condition expression is attached to the condition node
            # so data-flow analysis sees the variables it reads.
            condition_node = self.new_node(
                statements=[statement.condition] if statement.condition is not None else [],
                label="DO-WHILE CONDITION"
            )

            self.graph.nodes[condition_node]["condition"] = statement.condition

            # Body → condition
            for item in body_last:
                if isinstance(item, tuple):
                    node = item[0]
                    edge_type = item[1]
                    self.add_edge(node, condition_node, edge_type=edge_type)
                else:
                    self.add_edge(item, condition_node)

            # Condition: True → loop back to body_first
            if body_first is not None:
                self.add_edge(
                    condition_node,
                    body_first,
                    edge_type="true"
                )

            # Condition: False → next statement
            # Entry to this loop statement is body_first (or condition_node if body is empty)
            entry_node = body_first if body_first is not None else condition_node
            return entry_node, [(condition_node, "false")]

        # ---------------------------------------------
        # FOR LOOP
        # ---------------------------------------------

        if isinstance(statement, ForNode):

            init_node = None

            if statement.init is not None:
                init_node = self.new_node(
                    statements=[statement.init],
                    label="FOR INIT"
                )

            # The condition expression is attached to the node so that
            # data-flow analysis can see the variables it reads.
            # A condition is pure USE: it never defines a variable.
            condition_node = self.new_node(
                statements=[statement.condition] if statement.condition is not None else [],
                label="FOR CONDITION"
            )

            self.graph.nodes[condition_node]["condition"] = statement.condition

            update_node = None

            if statement.update is not None:
                update_node = self.new_node(
                    statements=[statement.update],
                    label="FOR UPDATE"
                )

            body_first, body_last = self.build_block(
                statement.body
            )

            # Init → condition
            if init_node is not None:
                self.add_edge(
                    init_node,
                    condition_node
                )
                first_node = init_node
            else:
                first_node = condition_node

            # Condition → body
            if body_first is not None:
                self.add_edge(
                    condition_node,
                    body_first,
                    edge_type="true"
                )

                # Body → update
                if update_node is not None:
                    for item in body_last:
                        if isinstance(item, tuple):
                            node = item[0]
                        else:
                            node = item
                        self.add_edge(
                            node,
                            update_node
                        )

                    # Update → condition
                    self.add_edge(
                        update_node,
                        condition_node,
                        edge_type="back"
                    )

                else:
                    for item in body_last:
                        if isinstance(item, tuple):
                            node = item[0]
                        else:
                            node = item
                        self.add_edge(
                            node,
                            condition_node,
                            edge_type="back"
                        )

            # False condition continues forward.
            return first_node, [(condition_node, "false")]

        # ---------------------------------------------
        # BREAK
        # ---------------------------------------------

        if isinstance(statement, BreakNode):
            node = self.new_node(statements=[statement], label="BREAK")
            # Route to the enclosing switch's merge node if one is set.
            if self._break_target is not None:
                self.add_edge(node, self._break_target, edge_type="break")
            # Break terminates this path (like return), so return empty continuations.
            return node, []

        # ---------------------------------------------
        # SWITCH
        # ---------------------------------------------

        if isinstance(statement, SwitchNode):
            # Dispatch node holds the switch expression for data-flow analysis.
            dispatch_node = self.new_node(
                statements=[statement.switch_expr],
                label="SWITCH DISPATCH",
            )
            self.graph.nodes[dispatch_node]["switch_expr"] = statement.switch_expr

            # Merge node — all break edges land here; this is the switch exit.
            merge_node = self.new_node(statements=[], label="SWITCH MERGE")

            # Save and set break target so BreakNodes inside case bodies route here.
            saved_break_target = self._break_target
            self._break_target = merge_node

            # Build each case clause.
            for case in statement.cases:
                # Determine edge label from the case match value.
                if hasattr(case.match_value, "value"):
                    edge_label = f"case:{case.match_value.value}"
                elif hasattr(case.match_value, "name"):
                    edge_label = f"case:{case.match_value.name}"
                else:
                    edge_label = "case:?"

                # Build the case body as a synthetic block.
                from src.parser.ast_nodes import BlockNode as _BlockNode
                synthetic_block = _BlockNode(statements=case.body, line=case.line)
                case_first, case_last = self.build_block(synthetic_block)

                if case_first is not None:
                    self.add_edge(dispatch_node, case_first, edge_type=edge_label)
                    # Any non-break continuations (should not exist in valid code,
                    # but handle defensively) wire to merge.
                    for item in case_last:
                        n = item[0] if isinstance(item, tuple) else item
                        et = item[1] if isinstance(item, tuple) else "normal"
                        self.add_edge(n, merge_node, edge_type=et)
                else:
                    # Empty case body — direct dispatch to merge.
                    self.add_edge(dispatch_node, merge_node, edge_type=edge_label)

            # Default clause.
            if statement.default_body is not None:
                from src.parser.ast_nodes import BlockNode as _BlockNode
                default_block = _BlockNode(statements=statement.default_body, line=statement.line)
                default_first, default_last = self.build_block(default_block)
                if default_first is not None:
                    self.add_edge(dispatch_node, default_first, edge_type="default")
                    for item in default_last:
                        n = item[0] if isinstance(item, tuple) else item
                        et = item[1] if isinstance(item, tuple) else "normal"
                        self.add_edge(n, merge_node, edge_type=et)
                else:
                    self.add_edge(dispatch_node, merge_node, edge_type="default")
            else:
                # No default: dispatch falls through to merge directly.
                self.add_edge(dispatch_node, merge_node, edge_type="default")

            # Restore break target.
            self._break_target = saved_break_target

            return dispatch_node, [merge_node]

        # ---------------------------------------------
        # UNKNOWN STATEMENT
        # ---------------------------------------------

        node = self.new_node(
            statements=[statement]
        )

        return node, [node]

    def export_dot(self, filename):
        """Export CFG to Graphviz DOT format."""

        nx.drawing.nx_pydot.write_dot(
            self.graph,
            filename
        )