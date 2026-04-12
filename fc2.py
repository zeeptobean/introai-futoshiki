# solve using CSP techniques: forward chaining + backtracking
class FutoshikiSolver:
    def __init__(self, size):
        self.size = size
        # Start with all cells having the full domain of possible values {1 ... size}
        # Val(i, j, v) will be true when len(self.domains[(i, j)]) == 1
        self.domains = {
            (i, j): set(range(1, size + 1))
            for i in range(1, size + 1)
            for j in range(1, size + 1)
        }
        self.constraints = []

    # --- Predicate Initializers ---

    def add_given(self, i, j, v):
        """Given(i, j, v): Cell (i,j) has the pre-filled clue value v"""
        self.domains[(i, j)] = {v}

    def add_less_h(self, i, j):
        """LessH(i, j): '<' constraint between (i,j) and (i,j+1)"""
        self.constraints.append(("LessH", i, j))

    def add_greater_h(self, i, j):
        """GreaterH(i, j): '>' constraint between (i,j) and (i,j+1)"""
        self.constraints.append(("GreaterH", i, j))

    def add_less_v(self, i, j):
        """LessV(i, j): '<' constraint between (i,j) and (i+1,j)"""
        self.constraints.append(("LessV", i, j))

    def add_greater_v(self, i, j):
        """GreaterV(i, j): '>' constraint between (i,j) and (i+1,j)"""
        self.constraints.append(("GreaterV", i, j))

    def less(self, v1, v2):
        """Less(v1, v2): Integer v1 < v2 (background arithmetic relation)"""
        return v1 < v2

    # --- Forward Chaining Engine ---

    def forward_chain(self):
        """
        Applies forward chaining rules until no more deductions can be made.
        Returns False if a contradiction is found, True otherwise.
        """
        changed = True
        while changed:
            changed = False

            # Rule 1: Row and Column Uniqueness (Sudoku rules)
            # If Val(i, j, v) is deduced (domain size 1), remove v from its row and col
            for i in range(1, self.size + 1):
                for j in range(1, self.size + 1):
                    if len(self.domains[(i, j)]) == 1:
                        val = list(self.domains[(i, j)])[0]

                        # Propagate through row
                        for c in range(1, self.size + 1):
                            if c != j and val in self.domains[(i, c)]:
                                self.domains[(i, c)].remove(val)
                                changed = True

                        # Propagate through column
                        for r in range(1, self.size + 1):
                            if r != i and val in self.domains[(r, j)]:
                                self.domains[(r, j)].remove(val)
                                changed = True

            # Rule 2: Enforce Inequality Predicates
            for constraint in self.constraints:
                ctype, i, j = constraint

                if ctype == "LessH":
                    c_changed = self._apply_inequality((i, j), (i, j + 1))
                elif ctype == "GreaterH":
                    c_changed = self._apply_inequality((i, j + 1), (i, j))
                elif ctype == "LessV":
                    c_changed = self._apply_inequality((i, j), (i + 1, j))
                elif ctype == "GreaterV":
                    c_changed = self._apply_inequality((i + 1, j), (i, j))

                if c_changed:
                    changed = True

            # Contradiction Check: Did any cell run out of possible values?
            for dom in self.domains.values():
                if len(dom) == 0:
                    return False  

        return True

    def _apply_inequality(self, cell_smaller, cell_larger):
        """
        Filters domains of two cells based on the Less(v1, v2) predicate.
        Returns True if domains were modified.
        """
        changed = False

        # Filter the smaller cell: Must have at least one valid larger pair
        valid_smaller = {
            v1 for v1 in self.domains[cell_smaller]
            if any(self.less(v1, v2) for v2 in self.domains[cell_larger])
        }
        if len(valid_smaller) < len(self.domains[cell_smaller]):
            self.domains[cell_smaller] = valid_smaller
            changed = True

        # Filter the larger cell: Must have at least one valid smaller pair
        valid_larger = {
            v2 for v2 in self.domains[cell_larger]
            if any(self.less(v1, v2) for v1 in self.domains[cell_smaller])
        }
        if len(valid_larger) < len(self.domains[cell_larger]):
            self.domains[cell_larger] = valid_larger
            changed = True

        return changed

    # --- Solver ---

    def solve(self):
        """Recursively solves the puzzle using Forward Chaining + Backtracking."""
        # Step 1: Deduce everything possible given the current state
        if not self.forward_chain():
            return False

        # Step 2: Find the next Val(i, j) to guess (Minimum Remaining Values heuristic)
        unassigned = [pos for pos, dom in self.domains.items() if len(dom) > 1]
        if not unassigned:
            return True  # All cells have exactly 1 value. Puzzle solved!

        unassigned.sort(key=lambda pos: len(self.domains[pos]))
        target_i, target_j = unassigned[0]

        # Step 3: Branch out
        saved_state = {k: set(v) for k, v in self.domains.items()}
        
        for guess in self.domains[(target_i, target_j)]:
            self.domains[(target_i, target_j)] = {guess} # Assume Val(i, j, guess)
            
            if self.solve():
                return True
                
            # Backtrack if assumption led to contradiction
            self.domains = {k: set(v) for k, v in saved_state.items()}

        return False

    def print_board(self):
        """Prints the deduced Val(i, j, v) matrix."""
        for i in range(1, self.size + 1):
            row = []
            for j in range(1, self.size + 1):
                val = list(self.domains[(i, j)])[0] if len(self.domains[(i, j)]) == 1 else "?"
                row.append(str(val))
            print(" ".join(row))

# ==========================================
# Example Usage
# ==========================================
if __name__ == "__main__":
    # Initialize a 4x4 board
    solver = FutoshikiSolver(4)

    # 1. Provide Given clues
    solver.add_given(1, 1, 4)  # Given(1, 1, 4)
    solver.add_given(2, 2, 2)  # Given(2, 2, 2)

    # 2. Add Inequality Constraints
    solver.add_less_h(1, 2)    # LessH(1, 2)    -> (1,2) < (1,3)
    solver.add_greater_v(3, 1) # GreaterV(3, 1) -> (3,1) > (4,1)

    print("Initial state loaded. Solving...")
    if solver.solve():
        print("\nSolution Found:")
        solver.print_board()
    else:
        print("\nNo solution exists for these constraints.")