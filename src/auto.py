# automatic SMT solver for futoshiki puzzles using Z3
import time
from typing import List, Optional, Sequence, Tuple

from z3 import Distinct, Int, Solver, sat

Constraint = Tuple[Tuple[int, int], Tuple[int, int]]


def _split_constraints(constraints: Sequence[Constraint]) -> Tuple[list, list, list, list]:
    """Convert normalized constraints into directional pairs for solver clauses."""
    less_h, greater_h = [], []
    less_v, greater_v = [], []
    for (r1, c1), (r2, c2) in constraints:
        if r1 == r2:
            if c2 == c1 + 1:
                less_h.append((r1, c1))
            elif c1 == c2 + 1:
                greater_h.append((r1, c2))
        elif c1 == c2:
            if r2 == r1 + 1:
                less_v.append((r1, c1))
            elif r1 == r2 + 1:
                greater_v.append((r2, c1))
    return less_h, greater_h, less_v, greater_v


def solve_futoshiki_smt(N, givens, less_h, greater_h, less_v, greater_v, timeout_ms=None):
    """Solve puzzle with Z3 and return solved board (or None if UNSAT)."""
    s = Solver()
    if timeout_ms is not None:
        s.set(timeout=int(timeout_ms))

    # V[i][j] holds an integer value from 1 to N
    V = [[Int("V_{}_{}".format(i, j)) for j in range(N)] for i in range(N)]

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
        s.add(V[r][c] == val)

    # 6. Horizontal less-than constraint
    for r, c in less_h:
        s.add(V[r][c] < V[r][c + 1])

    # 7. Horizontal greater-than constraint
    for r, c in greater_h:
        s.add(V[r][c] > V[r][c + 1])

    # 8. Vertical less-than constraint
    for r, c in less_v:
        s.add(V[r][c] < V[r + 1][c])

    # 9. Vertical greater-than constraint
    for r, c in greater_v:
        s.add(V[r][c] > V[r + 1][c])

    # Solve the SMT constraints
    if s.check() != sat:
        return None

    m = s.model()
    return [[m[V[i][j]].as_long() for j in range(N)] for i in range(N)]


def solve_puzzle_spec(size: int, board: Sequence[Sequence[int]], constraints: Sequence[Constraint], timeout_ms=None):
    """Programmatic API used by GUI adapters.

    Returns:
        Solved board (List[List[int]]) or None when no satisfying model is found.
    """
    givens = []
    for i in range(size):
        for j in range(size):
            val = int(board[i][j])
            if val > 0:
                givens.append((i, j, val))

    less_h, greater_h, less_v, greater_v = _split_constraints(constraints)
    return solve_futoshiki_smt(size, givens, less_h, greater_h, less_v, greater_v, timeout_ms=timeout_ms)


def _parse_input_file(file_name: str):
    with open(file_name, "r") as f:
        file_content = f.read()

    lines = [line.strip() for line in file_content.strip().split("\n")]
    data = [line for line in lines if line and not line.startswith("#")]

    if not data:
        raise ValueError("Input file is empty or only contains comments/whitespace.")

    N = int(data[0])
    board = [[0 for _ in range(N)] for _ in range(N)]

    grid_start = 1
    for i in range(N):
        row_vals = [int(x.strip()) for x in data[grid_start + i].split(",")]
        for j, val in enumerate(row_vals):
            board[i][j] = val

    constraints = []

    # Parse Horizontal Constraints
    horiz_start = grid_start + N
    for i in range(N):
        row_vals = [int(x.strip()) for x in data[horiz_start + i].split(",")]
        for j, val in enumerate(row_vals):
            if val == 1:
                constraints.append(((i, j), (i, j + 1)))
            elif val == -1:
                constraints.append(((i, j + 1), (i, j)))

    # Parse Vertical Constraints
    vert_start = horiz_start + N
    for i in range(N - 1):
        row_vals = [int(x.strip()) for x in data[vert_start + i].split(",")]
        for j, val in enumerate(row_vals):
            if val == 1:
                constraints.append(((i, j), (i + 1, j)))
            elif val == -1:
                constraints.append(((i + 1, j), (i, j)))

    return N, board, constraints


def load_and_solve_futoshiki(file_name: str, timeout_ms=None) -> Optional[List[List[int]]]:
    """File-based helper that returns solved board for scripting/testing."""
    N, board, constraints = _parse_input_file(file_name)
    return solve_puzzle_spec(N, board, constraints, timeout_ms=timeout_ms)


def _print_board(board):
    for row in board:
        print(" ".join(str(v) for v in row))


# === Example Execution ===
if __name__ == "__main__":
    start_time = time.perf_counter()
    solved = load_and_solve_futoshiki("Inputs/input-18.txt")
    time_taken = time.perf_counter() - start_time

    if solved is None:
        print("\nUnsatisfiable puzzle.")
    else:
        print("\n--- Solved ---")
        _print_board(solved)
    print("\nTotal time taken: {:.4f} seconds".format(time_taken))