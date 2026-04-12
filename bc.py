class FutoshikiSolver:
    def __init__(self, size):
        self.n = size
        
        # Knowledge Base defined by the Predicate Table
        self.Given = set()      # Set of tuples (i, j, v)
        self.LessH = set()      # Set of tuples (i, j)
        self.GreaterH = set()   # Set of tuples (i, j)
        self.LessV = set()      # Set of tuples (i, j)
        self.GreaterV = set()   # Set of tuples (i, j)
        
        # Working Memory: Val(i, j, v) represented as a dictionary mapping (i, j) -> v
        self.Val = {}

    def Less(self, v1, v2):
        """Background arithmetic relation: Integer v1 < v2"""
        return v1 < v2

    def is_consistent(self, i, j, v):
        """
        Evaluates the sub-goal Val(i, j, v) against the current Knowledge Base
        to see if it violates any established rules or predicates.
        """
        # 1. Standard Futoshiki Rules: Row and Column uniqueness
        for k in range(1, self.n + 1):
            if k != j and self.Val.get((i, k)) == v:
                return False
            if k != i and self.Val.get((k, j)) == v:
                return False

        # 2. Horizontal Constraints
        # LessH(i, j): Cell(i, j) < Cell(i, j+1)
        if (i, j) in self.LessH and (i, j+1) in self.Val:
            if not self.Less(v, self.Val[(i, j+1)]): return False
        
        # LessH(i, j-1): Cell(i, j-1) < Cell(i, j)
        if (i, j-1) in self.LessH and (i, j-1) in self.Val:
            if not self.Less(self.Val[(i, j-1)], v): return False

        # GreaterH(i, j): Cell(i, j) > Cell(i, j+1)  => Less(Cell(i, j+1), Cell(i, j))
        if (i, j) in self.GreaterH and (i, j+1) in self.Val:
            if not self.Less(self.Val[(i, j+1)], v): return False
            
        # GreaterH(i, j-1): Cell(i, j-1) > Cell(i, j) => Less(Cell(i, j), Cell(i, j-1))
        if (i, j-1) in self.GreaterH and (i, j-1) in self.Val:
            if not self.Less(v, self.Val[(i, j-1)]): return False

        # 3. Vertical Constraints
        # LessV(i, j): Cell(i, j) < Cell(i+1, j)
        if (i, j) in self.LessV and (i+1, j) in self.Val:
            if not self.Less(v, self.Val[(i+1, j)]): return False
            
        # LessV(i-1, j): Cell(i-1, j) < Cell(i, j)
        if (i-1, j) in self.LessV and (i-1, j) in self.Val:
            if not self.Less(self.Val[(i-1, j)], v): return False

        # GreaterV(i, j): Cell(i, j) > Cell(i+1, j) => Less(Cell(i+1, j), Cell(i, j))
        if (i, j) in self.GreaterV and (i+1, j) in self.Val:
            if not self.Less(self.Val[(i+1, j)], v): return False
            
        # GreaterV(i-1, j): Cell(i-1, j) > Cell(i, j) => Less(Cell(i, j), Cell(i-1, j))
        if (i-1, j) in self.GreaterV and (i-1, j) in self.Val:
            if not self.Less(v, self.Val[(i-1, j)]): return False

        # Sub-goal is logically sound so far
        return True

    def backward_chain(self):
        """
        Recursive backward chaining engine.
        Goal: Prove that all cells (1..n, 1..n) have a valid assignment.
        """
        # Find the next sub-goal (an unassigned cell)
        unassigned = None
        for r in range(1, self.n + 1):
            for c in range(1, self.n + 1):
                if (r, c) not in self.Val:
                    unassigned = (r, c)
                    break
            if unassigned: break

        # Base Case: No unassigned cells left. The main goal is proven!
        if not unassigned:
            return True

        i, j = unassigned

        # Attempt to prove sub-goal Val(i, j, v)
        for v in range(1, self.n + 1):
            if self.is_consistent(i, j, v):
                # Assert Val(i, j, v) into working memory
                self.Val[(i, j)] = v
                
                # Recursively chain to prove the rest of the board
                if self.backward_chain():
                    return True
                
                # Backtrack: the assertion led to a logical contradiction later
                del self.Val[(i, j)]

        # Could not prove this sub-goal with any value
        return False

    def solve(self):
        """Initializes the working memory with Givens and triggers the engine."""
        # Pre-fill working memory with Given(i, j, v) axioms
        for i, j, v in self.Given:
            self.Val[(i, j)] = v

        # Initiate backward chaining
        success = self.backward_chain()
        return self.Val if success else None

    def display(self):
        """Helper to print the resolved Val(i, j, v) state."""
        for r in range(1, self.n + 1):
            row_str = []
            for c in range(1, self.n + 1):
                row_str.append(str(self.Val.get((r, c), ".")))
            print(" ".join(row_str))

if __name__ == "__main__":
    # Create a solver for a 4x4 Futoshiki grid
    kb = FutoshikiSolver(4)

    # Adding Given(i, j, v)
    # E.g., Cell (1, 1) has the clue 4
    kb.Given.add((1, 1, 4))
    kb.Given.add((4, 4, 1))

    # Adding Constraints based on Predicates Table
    # LessH(1, 2) implies Cell(1, 2) < Cell(1, 3)
    kb.LessH.add((1, 2))
    
    # GreaterV(2, 3) implies Cell(2, 3) > Cell(3, 3)
    kb.GreaterV.add((2, 3))

    print("Solving backward chaining...")
    solution = kb.solve()

    if solution:
        print("Proof successful! Deduced values:")
        kb.display()
    else:
        print("No valid assignment found. Contradiction in Given constraints.")