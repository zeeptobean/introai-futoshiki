# automatic SMT solver for futoshiki puzzles using Z3
from z3 import *
import time

def solve_futoshiki_smt(N, givens, less_h, greater_h, less_v, greater_v):
    """
    Solves the Futoshiki puzzle using Z3's SMT Integer solver.
    """
    s = Solver()

    # V[i][j] holds an integer value from 1 to N
    V = [[Int(f"V_{i}_{j}") for j in range(N)] for i in range(N)]

    # 1 & 2. Domain constraints
    for i in range(N):
        for j in range(N):
            s.add(V[i][j] >= 1, V[i][j] <= N)

    # 3. Row uniqueness
    for i in range(N):
        s.add(Distinct(V[i]))

    # 4. Column uniqueness
    for j in range(N):
        s.add(Distinct([V[i][j] for i in range(N)]))

    # 5. Given clues are enforced
    for r, c, val in givens:
        s.add(V[r][c] == val) # 'val' from file is already 1-based

    # 6. Horizontal less-than constraint
    for r, c in less_h:
        s.add(V[r][c] < V[r][c+1])

    # 7. Horizontal greater-than constraint
    for r, c in greater_h:
        s.add(V[r][c] > V[r][c+1])

    # 8. Vertical less-than constraint
    for r, c in less_v:
        s.add(V[r][c] < V[r+1][c])

    # 9. Vertical greater-than constraint
    for r, c in greater_v:
        s.add(V[r][c] > V[r+1][c])

    # Solve the SMT constraints
    if s.check() == sat:
        m = s.model()
        print(f"\n--- Solved {N}x{N} Futoshiki ---")
        for i in range(N):
            row = [str(m[V[i][j]].as_long()) for j in range(N)]
            print(" ".join(row))
    else:
        print("\nUnsatisfiable puzzle.")

def load_and_solve_futoshiki(file_name: str):
    """
    Parses a Futoshiki puzzle text file and feeds it to the Z3 SMT solver.
    Expects 0 for empty cells, 1 for '<' constraints, -1 for '>' constraints.
    """
    with open(file_name, 'r') as f:
        file_content = f.read()
        
    lines = [line.strip() for line in file_content.strip().split('\n')]
    data = [line for line in lines if line and not line.startswith('#')]
    
    print(f"Loaded puzzle from {file_name} with {len(data)} lines of data (excluding comments/whitespace).")

    if not data:
        raise ValueError("Input file is empty or only contains comments/whitespace.")

    N = int(data[0])
    
    givens = []
    less_h, greater_h = [], []
    less_v, greater_v = [], []

    # 1. Parse Grid (Given Clues)
    grid_start = 1
    for i in range(N):
        row_vals = [int(x.strip()) for x in data[grid_start + i].split(',')]
        for j, val in enumerate(row_vals):
            if val > 0:
                givens.append((i, j, val)) # Append 0-indexed coords, 1-based val

    # 2. Parse Horizontal Constraints
    horiz_start = grid_start + N
    for i in range(N):
        row_vals = [int(x.strip()) for x in data[horiz_start + i].split(',')]
        for j, val in enumerate(row_vals):
            if val == 1: less_h.append((i, j))
            elif val == -1: greater_h.append((i, j))

    # 3. Parse Vertical Constraints
    vert_start = horiz_start + N
    for i in range(N - 1): # There are only N-1 rows of vertical constraints
        row_vals = [int(x.strip()) for x in data[vert_start + i].split(',')]
        for j, val in enumerate(row_vals):
            if val == 1: less_v.append((i, j))
            elif val == -1: greater_v.append((i, j))

    # Execute Solver
    solve_futoshiki_smt(N, givens, less_h, greater_h, less_v, greater_v)


# === Example Execution ===
if __name__ == "__main__":
    # Assuming you have a file named 'puzzle.txt'
    start_time = time.perf_counter()
    load_and_solve_futoshiki('Inputs/input-18.txt')
    time_taken = time.perf_counter() - start_time
    print(f"\nTotal time taken: {time_taken:.4f} seconds")
    pass