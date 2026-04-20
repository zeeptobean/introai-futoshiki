from pysat.solvers import Glucose3

def parse_futoshiki_file(filepath):
    with open(filepath, 'r') as f:
        lines = f.readlines()

    # 1. Clean the data: ignore comments and empty lines
    cleaned_lines = []
    for line in lines:
        line = line.split('#')[0].strip() # Remove comments and whitespace
        if line:
            cleaned_lines.append(line)

    # 2. Extract N
    N = int(cleaned_lines[0])
    current_line_idx = 1

    # Data structures to store the "Knowledge Base" (using 1-based indexing)
    givens = []       # Format: (i, j, v)
    less_h = []       # Format: (i, j) meaning Cell(i, j) < Cell(i, j+1)
    greater_h = []    # Format: (i, j) meaning Cell(i, j) > Cell(i, j+1)
    less_v = []       # Format: (i, j) meaning Cell(i, j) < Cell(i+1, j)
    greater_v = []    # Format: (i, j) meaning Cell(i, j) > Cell(i+1, j)

    # 3. Parse Grid Data (N lines)
    for i in range(N):
        # Split by comma and convert to integers
        row_values = list(map(int, cleaned_lines[current_line_idx].split(',')))
        for j in range(N):
            if row_values[j] != 0:
                givens.append((i + 1, j + 1, row_values[j]))
        current_line_idx += 1

    # 4. Parse Horizontal Constraints (N lines, N-1 values per line)
    for i in range(N):
        row_values = list(map(int, cleaned_lines[current_line_idx].split(',')))
        for j in range(N - 1):
            if row_values[j] == 1:
                less_h.append((i + 1, j + 1))
            elif row_values[j] == -1:
                greater_h.append((i + 1, j + 1))
        current_line_idx += 1

    # 5. Parse Vertical Constraints (N-1 lines, N values per line)
    for i in range(N - 1):
        row_values = list(map(int, cleaned_lines[current_line_idx].split(',')))
        for j in range(N):
            if row_values[j] == 1:
                less_v.append((i + 1, j + 1))
            elif row_values[j] == -1:
                greater_v.append((i + 1, j + 1))
        current_line_idx += 1

    return N, givens, less_h, greater_h, less_v, greater_v

def generate_cnf_kb(N, givens, less_h, greater_h, less_v, greater_v):
    """
    Translates Futoshiki FOL axioms into a ground CNF Knowledge Base.
    Returns a list of clauses, where each clause is a list of integers.
    """
    clauses = []

    # Helper function to map Val(i, j, v) to a unique integer.
    # 1 <= i, j, v <= N
    def var(i, j, v):
        # Maps to a unique ID starting from 1 to N^3
        return (i - 1) * N * N + (j - 1) * N + v

    # ---------------------------------------------------------
    # Axiom 1: Every cell has at least one value
    # ∀i ∀j ∃v Val(i, j, v)
    # ---------------------------------------------------------
    for i in range(1, N + 1):
        for j in range(1, N + 1):
            clause = [var(i, j, v) for v in range(1, N + 1)]
            clauses.append(clause)

    # ---------------------------------------------------------
    # Axiom 2: Every cell has at most one value
    # ∀i ∀j ∀v1 ∀v2 (Val(i,j,v1) ∧ Val(i,j,v2)) => v1 = v2
    # ---------------------------------------------------------
    for i in range(1, N + 1):
        for j in range(1, N + 1):
            for v1 in range(1, N + 1):
                for v2 in range(v1 + 1, N + 1):
                    # Cannot be v1 AND v2 at the same time
                    clauses.append([-var(i, j, v1), -var(i, j, v2)])

    # ---------------------------------------------------------
    # Axiom 3: Row uniqueness
    # ∀i ∀j1 ∀j2 ∀v (Val(i,j1,v) ∧ Val(i,j2,v) ∧ j1 != j2) => ⊥
    # ---------------------------------------------------------
    for i in range(1, N + 1):
        for v in range(1, N + 1):
            for j1 in range(1, N + 1):
                for j2 in range(j1 + 1, N + 1):
                    clauses.append([-var(i, j1, v), -var(i, j2, v)])

    # ---------------------------------------------------------
    # Axiom 4: Column uniqueness
    # ∀i1 ∀i2 ∀j ∀v (Val(i1,j,v) ∧ Val(i2,j,v) ∧ i1 != i2) => ⊥
    # ---------------------------------------------------------
    for j in range(1, N + 1):
        for v in range(1, N + 1):
            for i1 in range(1, N + 1):
                for i2 in range(i1 + 1, N + 1):
                    clauses.append([-var(i1, j, v), -var(i2, j, v)])

    # ---------------------------------------------------------
    # Axiom 5: Given clues are enforced
    # ∀i ∀j ∀v Given(i,j,v) => Val(i,j,v)
    # ---------------------------------------------------------
    for (i, j, v) in givens:
        # A unit clause forcing this variable to be True
        clauses.append([var(i, j, v)])

    # ---------------------------------------------------------
    # Axiom 6: Horizontal less-than constraint
    # (i, j) < (i, j+1). If v1 >= v2, that combination is illegal.
    # ---------------------------------------------------------
    for (i, j) in less_h:
        for v1 in range(1, N + 1):
            for v2 in range(1, N + 1):
                if v1 >= v2:
                    clauses.append([-var(i, j, v1), -var(i, j + 1, v2)])

    # ---------------------------------------------------------
    # Axiom 7: Horizontal greater-than constraint
    # (i, j) > (i, j+1). If v1 <= v2, that combination is illegal.
    # ---------------------------------------------------------
    for (i, j) in greater_h:
        for v1 in range(1, N + 1):
            for v2 in range(1, N + 1):
                if v1 <= v2:
                    clauses.append([-var(i, j, v1), -var(i, j + 1, v2)])

    # ---------------------------------------------------------
    # Axiom 8: Vertical less-than constraint
    # (i, j) < (i+1, j). If v1 >= v2, that combination is illegal.
    # ---------------------------------------------------------
    for (i, j) in less_v:
        for v1 in range(1, N + 1):
            for v2 in range(1, N + 1):
                if v1 >= v2:
                    clauses.append([-var(i, j, v1), -var(i + 1, j, v2)])

    # ---------------------------------------------------------
    # Axiom 9: Vertical greater-than constraint
    # (i, j) > (i+1, j). If v1 <= v2, that combination is illegal.
    # ---------------------------------------------------------
    for (i, j) in greater_v:
        for v1 in range(1, N + 1):
            for v2 in range(1, N + 1):
                if v1 <= v2:
                    clauses.append([-var(i, j, v1), -var(i + 1, j, v2)])

    return clauses

def print_readable_clauses(clauses, N, limit: int | None = 30):
    """
    Translates CNF integer clauses back into readable English.
    'limit' stops it from flooding your console with thousands of lines.
    """
    # 1. Build a reverse-lookup dictionary
    id_to_string = {}
    for i in range(1, N + 1):
        for j in range(1, N + 1):
            for v in range(1, N + 1):
                # This is the exact same formula from your generate_cnf_kb function
                var_id = (i - 1) * N * N + (j - 1) * N + v
                id_to_string[var_id] = f"Cell({i},{j}) is {v}"

    print(f"Printing first {limit} clauses:")
    for count, clause in enumerate(clauses):
        if limit is not None and count >= limit:
            break
        readable_clause = []
        for lit in clause:
            if lit > 0:
                # Positive number
                readable_clause.append(id_to_string[lit])
            else:
                # Negative number (NOT)
                readable_clause.append("NOT " + id_to_string[abs(lit)])
        
        # Join the parts of the clause with " OR "
        print(" OR ".join(readable_clause))

def print_solution(model, N):
    """
    Decodes the PySAT model and prints the solved N x N grid in a basic format.
    """
    # Create an empty N x N grid
    grid = [[0 for _ in range(N)] for _ in range(N)]
    
    # Filter for only the True variables (positive integers)
    true_vars = [val for val in model if val > 0]
    
    for val in true_vars:
        # Reverse the math from var(i, j, v) to get i, j, v back
        val -= 1
        v = (val % N) + 1
        j = ((val // N) % N) + 1
        i = (val // (N * N)) + 1
        
        # Place the value on the grid (converting back to 0-based indexing)
        grid[i - 1][j - 1] = v
        
    # Print the grid in a basic format
    for row in grid:
        print(" ".join(str(x) for x in row))

if __name__ == "__main__":
    N, givens, less_h, greater_h, less_v, greater_v = parse_futoshiki_file('Inputs/input-01.txt')

    # print(f"Grid Size N: {N}")
    # print(f"Givens: {givens}")
    # print(f"Less Horizontal: {less_h}")
    # print(f"Greater Horizontal: {greater_h}")
    # print(f"Less Vertical: {less_v}")
    # print(f"Greater Vertical: {greater_v}")

    clauses = generate_cnf_kb(N, givens, less_h, greater_h, less_v, greater_v)
    print_readable_clauses(clauses, N)
    exit(0)

    with Glucose3() as solver:
        # Add all clauses to the solver
        for clause in clauses:
            solver.add_clause(clause)
            
        print("Solving...")
        
        # 4. Ask the solver for an answer
        if solver.solve():
            print("\nSOLUTION FOUND!\n")
            model = solver.get_model()
            print_solution(model, N)
        else:
            print("\nUNSATISFIABLE: No valid solution exists for this board ruleset.")