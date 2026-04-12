class FutoshikiKB:
    def __init__(self, N):
        self.N = N
        self.clauses = [] # This will hold our Knowledge Base in CNF

    def var(self, i, j, v):
        """
        Maps the 3D coordinate (row i, col j, value v) to a unique 1D integer.
        Assumes i, j, v are 1-indexed (from 1 to N).
        """
        return (i - 1) * (self.N ** 2) + (j - 1) * self.N + v

    def generate_base_rules(self):
        """Generates the grounded CNF clauses for Axioms 1 through 4."""
        
        # Axiom 1: Every cell has at least one value (v=1 OR v=2 OR ... OR v=N)
        for i in range(1, self.N + 1):
            for j in range(1, self.N + 1):
                clause = [self.var(i, j, v) for v in range(1, self.N + 1)]
                self.clauses.append(clause)

        # Axiom 2: Every cell has at most one value (NOT v1 OR NOT v2)
        for i in range(1, self.N + 1):
            for j in range(1, self.N + 1):
                for v1 in range(1, self.N + 1):
                    for v2 in range(v1 + 1, self.N + 1):
                        self.clauses.append([-self.var(i, j, v1), -self.var(i, j, v2)])

        # Axiom 3: Row uniqueness (If v is in (i, j1), it cannot be in (i, j2))
        for i in range(1, self.N + 1):
            for v in range(1, self.N + 1):
                for j1 in range(1, self.N + 1):
                    for j2 in range(j1 + 1, self.N + 1):
                        self.clauses.append([-self.var(i, j1, v), -self.var(i, j2, v)])

        # Axiom 4: Column uniqueness (If v is in (i1, j), it cannot be in (i2, j))
        for j in range(1, self.N + 1):
            for v in range(1, self.N + 1):
                for i1 in range(1, self.N + 1):
                    for i2 in range(i1 + 1, self.N + 1):
                        self.clauses.append([-self.var(i1, j, v), -self.var(i2, j, v)])

    def add_clue(self, i, j, v):
        """Axiom 5: Enforces a given starting number."""
        # A unit clause (a list with one literal) forces this variable to be True
        self.clauses.append([self.var(i, j, v)])

    def add_less_than_constraint(self, i1, j1, i2, j2):
        """
        Axioms 6-9: Enforces Cell(i1, j1) < Cell(i2, j2).
        If v1 >= v2, they cannot simultaneously be the values in these cells.
        Therefore: NOT Val(i1, j1, v1) OR NOT Val(i2, j2, v2)
        """
        for v1 in range(1, self.N + 1):
            for v2 in range(1, self.N + 1):
                if v1 >= v2:
                    self.clauses.append([-self.var(i1, j1, v1), -self.var(i2, j2, v2)])

    def add_greater_than_constraint(self, i1, j1, i2, j2):
        """Enforces Cell(i1, j1) > Cell(i2, j2)."""
        self.add_less_than_constraint(i2, j2, i1, j1)

    def get_kb(self):
        return self.clauses

# --- Example Usage ---
if __name__ == "__main__":
    N = 4 # Example for a 4x4 grid
    kb_generator = FutoshikiKB(N)
    
    # 1. Generate the standard grid rules (Axioms 1-4)
    kb_generator.generate_base_rules()
    
    # 2. Add specific puzzle clues (Axiom 5)
    # E.g., The cell at Row 1, Col 1 is a 3
    kb_generator.add_clue(1, 1, 3) 
    
    # 3. Add specific inequality constraints (Axioms 6-9)
    # E.g., Cell(1, 2) < Cell(1, 3)  -- Horizontal less than
    kb_generator.add_less_than_constraint(1, 2, 1, 3)
    
    # Extract the final grounded Knowledge Base
    knowledge_base = kb_generator.get_kb()
    
    print(f"Generated {len(knowledge_base)} CNF clauses for a {N}x{N} grid.")
    print(knowledge_base)
    # You would now pass 'knowledge_base' into a SAT solver.