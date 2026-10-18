from dataclasses import dataclass
from typing import Optional


@dataclass
class Symbol:
    name: str
    type: str
    scope_id: str
    line_declared: int
    is_initialized: bool = False
    is_pointer: bool = False
    array_size: Optional[int] = None
    array_size2: Optional[int] = None


class SymbolTable:
    def __init__(self):
        # Active scopes.
        # The last item is the current scope.
        self.scopes = []

        # Keep every scope ever created.
        # This allows us to display the complete symbol table
        # even after leaving a scope.
        self.all_scopes = []

        # Start with the global scope.
        self.enter_scope("global")

    def enter_scope(self, scope_id: str):
        """Enter a new scope."""

        scope = {
            "scope_id": scope_id,
            "symbols": {}
        }

        self.scopes.append(scope)
        self.all_scopes.append(scope)

    def exit_scope(self):
        """Exit the current scope."""

        if len(self.scopes) > 1:
            self.scopes.pop()

    def current_scope(self):
        """Return the current active scope."""

        return self.scopes[-1]

    def lookup_current_scope(self, name: str):
        """Look for a symbol only in the current scope."""

        current = self.current_scope()

        return current["symbols"].get(name)

    def lookup(self, name: str):
        """Look for a symbol from current scope outward."""

        for scope in reversed(self.scopes):
            if name in scope["symbols"]:
                return scope["symbols"][name]

        return None

    def declare(
        self,
        name: str,
        var_type: str,
        line_declared: int,
        is_initialized: bool = False,
        is_pointer: bool = False,
        array_size: Optional[int] = None,
        array_size2: Optional[int] = None
    ):
        """
        Declare a variable in the current scope.

        Returns:
            Symbol if declaration succeeds.
            None if the variable already exists
            in the current scope.
        """

        # Check redeclaration in the same scope.
        if self.lookup_current_scope(name) is not None:
            return None

        scope_id = self.current_scope()["scope_id"]

        symbol = Symbol(
            name=name,
            type=var_type,
            scope_id=scope_id,
            line_declared=line_declared,
            is_initialized=is_initialized,
            is_pointer=is_pointer,
            array_size=array_size,
            array_size2=array_size2
        )

        self.current_scope()["symbols"][name] = symbol

        return symbol

    def mark_initialized(self, name: str):
        """Mark a variable as initialized."""

        symbol = self.lookup(name)

        if symbol is not None:
            symbol.is_initialized = True
            return True

        return False

    def get_all_symbols(self):
        """Return symbols from every scope."""

        result = []

        for scope in self.all_scopes:
            for symbol in scope["symbols"].values():
                result.append(symbol)

        return result