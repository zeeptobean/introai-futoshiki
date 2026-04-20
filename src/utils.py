"""Utilities to convert between puzzle objects and the project input-file format."""

import os
from typing import List, Optional, Sequence, Tuple


Constraint = Tuple[Tuple[int, int], Tuple[int, int]]


def _skip_empty_lines(lines: Sequence[str], start_idx: int) -> int:
    while start_idx < len(lines) and not lines[start_idx].strip():
        start_idx += 1
    return start_idx


def _skip_ignorable_lines(lines: Sequence[str], start_idx: int) -> int:
    while start_idx < len(lines):
        stripped = lines[start_idx].strip()
        if stripped and not stripped.startswith("#"):
            break
        start_idx += 1
    return start_idx


def _parse_csv_int_row(line: str, expected_len: int, section_name: str) -> List[int]:
    values = [part.strip() for part in line.strip().split(",")]
    if len(values) != expected_len:
        raise ValueError(
            f"Invalid {section_name} row length: expected {expected_len}, got {len(values)}"
        )
    try:
        return [int(value) for value in values]
    except ValueError as exc:
        raise ValueError(f"Invalid integer in {section_name} row: {line.strip()}") from exc


def _read_matrix(
    lines: Sequence[str],
    start_idx: int,
    rows: int,
    cols: int,
    section_name: str,
) -> Tuple[List[List[int]], int]:
    matrix: List[List[int]] = []
    idx = start_idx
    for _ in range(rows):
        if idx >= len(lines):
            raise ValueError(f"Unexpected end of file while reading {section_name}")
        matrix.append(_parse_csv_int_row(lines[idx], cols, section_name))
        idx += 1
    return matrix, idx


def _validate_square_board(n: int, board: Sequence[Sequence[int]]) -> None:
    if n <= 0:
        raise ValueError("Size N must be positive")
    if len(board) != n or any(len(row) != n for row in board):
        raise ValueError("Invalid board shape, expected NxN")


def _validate_constraint_matrices(
    n: int,
    h_constraints: Sequence[Sequence[int]],
    v_constraints: Sequence[Sequence[int]],
) -> None:
    if len(h_constraints) != n or any(len(row) != n - 1 for row in h_constraints):
        raise ValueError("Invalid horizontal constraints shape, expected N x (N-1)")
    if len(v_constraints) != n - 1 or any(len(row) != n for row in v_constraints):
        raise ValueError("Invalid vertical constraints shape, expected (N-1) x N")


def puzzle_to_input_format(
    n: int,
    board: Sequence[Sequence[int]],
    constraints: Sequence[Constraint],
) -> Tuple[List[List[int]], List[List[int]]]:
    """Convert a puzzle into horizontal/vertical matrices for file output.

    Args:
        n: Board size NxN.
        board: Current board matrix (used to validate shape).
        constraints: Constraint list in form ((r1, c1), (r2, c2)) meaning
            (r1, c1) < (r2, c2).

    Returns:
        Tuple containing:
            - h_constraints: N x (N-1) matrix.
            - v_constraints: (N-1) x N matrix.

    Raises:
        ValueError: If board shape is invalid or a constraint is non-adjacent.
    """
    _validate_square_board(n, board)

    h = [[0] * (n - 1) for _ in range(n)]
    v = [[0] * n for _ in range(n - 1)]

    for (r1, c1), (r2, c2) in constraints:
        if r1 == r2 and abs(c1 - c2) == 1:
            left_col = min(c1, c2)
            h[r1][left_col] = 1 if c1 < c2 else -1
            continue

        if c1 == c2 and abs(r1 - r2) == 1:
            top_row = min(r1, r2)
            v[top_row][c1] = 1 if r1 < r2 else -1
            continue

        raise ValueError(f"Constraint must connect adjacent cells: {((r1, c1), (r2, c2))}")

    return h, v


def input_format_to_constraints(
    n: int,
    h_constraints: Sequence[Sequence[int]],
    v_constraints: Sequence[Sequence[int]],
) -> List[Constraint]:
    """Convert H/V matrices from input format into a constraint list.

    Args:
        n: Board size NxN.
        h_constraints: Horizontal N x (N-1) matrix with 1/-1/0 values.
        v_constraints: Vertical (N-1) x N matrix with 1/-1/0 values.

    Returns:
        Constraint list in form ((r1, c1), (r2, c2)) meaning
        (r1, c1) < (r2, c2).

    Raises:
        ValueError: If shape is invalid or a value is outside {-1, 0, 1}.
    """
    _validate_constraint_matrices(n, h_constraints, v_constraints)

    constraints: List[Constraint] = []

    for r in range(n):
        for c in range(n - 1):
            value = h_constraints[r][c]
            if value == 1:
                constraints.append(((r, c), (r, c + 1)))
            elif value == -1:
                constraints.append(((r, c + 1), (r, c)))
            elif value != 0:
                raise ValueError(f"Invalid horizontal constraint value {value} at ({r}, {c})")

    for r in range(n - 1):
        for c in range(n):
            value = v_constraints[r][c]
            if value == 1:
                constraints.append(((r, c), (r + 1, c)))
            elif value == -1:
                constraints.append(((r + 1, c), (r, c)))
            elif value != 0:
                raise ValueError(f"Invalid vertical constraint value {value} at ({r}, {c})")

    return constraints


def input_format_to_puzzle(
    n: int,
    board: Sequence[Sequence[int]],
    h_constraints: Sequence[Sequence[int]],
    v_constraints: Sequence[Sequence[int]],
) -> Tuple[int, List[List[int]], List[Constraint]]:
    """Bundle parsed input data into the project's puzzle tuple format.

    Args:
        n: Board size NxN.
        board: N x N board matrix.
        h_constraints: Horizontal N x (N-1) matrix.
        v_constraints: Vertical (N-1) x N matrix.

    Returns:
        Tuple `(n, board, constraints)`.

    Raises:
        ValueError: If board or constraint matrices have invalid shape/value.
    """
    _validate_square_board(n, board)
    constraints = input_format_to_constraints(n, h_constraints, v_constraints)
    return n, [list(row) for row in board], constraints


def read_input_file(filepath: str) -> Tuple[int, List[List[int]], List[Constraint]]:
    """Read an input file and return `(n, board, constraints)`.

    Args:
        filepath: Path to an input file in project format.

    Returns:
        Tuple `(n, board, constraints)`.

    Raises:
        ValueError: If the file is empty or has invalid format.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        lines = [line.rstrip("\n") for line in f]

    idx = _skip_ignorable_lines(lines, 0)
    if idx >= len(lines):
        raise ValueError("Input file is empty")

    try:
        n = int(lines[idx].strip())
    except ValueError as exc:
        raise ValueError("First non-empty line must be integer size N") from exc

    if n <= 0:
        raise ValueError("Size N must be positive")

    idx = _skip_ignorable_lines(lines, idx + 1)
    board, idx = _read_matrix(lines, idx, n, n, "board")

    idx = _skip_ignorable_lines(lines, idx)
    h_constraints, idx = _read_matrix(lines, idx, n, n - 1, "horizontal constraints")

    idx = _skip_ignorable_lines(lines, idx)
    v_constraints, idx = _read_matrix(lines, idx, n - 1, n, "vertical constraints")

    return input_format_to_puzzle(n, board, h_constraints, v_constraints)


def write_input_file(
    filepath: str,
    n: int,
    board: Sequence[Sequence[int]],
    constraints: Sequence[Constraint],
    header_comment: Optional[str] = None,
) -> None:
    """Write a puzzle to the project's input-file format.

    Args:
        filepath: Output file path.
        n: Board size NxN.
        board: N x N board matrix.
        constraints: Constraint list in form ((r1, c1), (r2, c2)).

    Returns:
        None

    Raises:
        ValueError: If puzzle data is invalid.
    """
    h_constraints, v_constraints = puzzle_to_input_format(n, board, constraints)

    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        if header_comment:
            f.write(f"# {header_comment}\n")
        f.write(f"{n}\n")
        for row in board:
            f.write(", ".join(map(str, row)) + "\n")
        f.write("\n")
        for row in h_constraints:
            f.write(", ".join(map(str, row)) + "\n")
        f.write("\n")
        for row in v_constraints:
            f.write(", ".join(map(str, row)) + "\n")

    print(f"Written: {filepath}")


def batch_write(puzzles: Sequence, output_dir: str = "Inputs") -> None:
    """Write multiple puzzles to `input-XX.txt` files.

    Args:
        puzzles: Puzzle list where each item is either:
            - dict with keys `n` or `size`, `board`, `constraints`, or
            - tuple `(n, board, constraints)`.
        output_dir: Output directory.

    Returns:
        None

    Raises:
        ValueError: If a puzzle item does not match the expected format.
    """
    for idx, puzzle in enumerate(puzzles, start=1):
        if isinstance(puzzle, dict):
            n = puzzle.get("n", puzzle.get("size"))
            board = puzzle.get("board")
            constraints = puzzle.get("constraints")
            if n is None or board is None or constraints is None:
                raise ValueError("Each puzzle dict must contain n/size, board, constraints")
        else:
            try:
                n, board, constraints = puzzle
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "Each puzzle must be dict or tuple (n, board, constraints)"
                ) from exc

        filepath = os.path.join(output_dir, f"input-{idx:02d}.txt")
        write_input_file(filepath, n, board, constraints)

def parse_futoshiki2(filepath: str) -> tuple[list[list[int]], list[list[int]], list[list[int]]]:
    """
    Returns:
        tuple containing:
        - grid
        - horiz_constraints
        - vert_constraints
    """
    with open(filepath, 'r') as f:
        lines = f.readlines()

    clean_lines = []
    for line in lines:
        line = line.split('#')[0].strip()
        if line:
            clean_lines.append(line)

    if ',' not in clean_lines[0]:
        N = int(clean_lines[0])
        clean_lines = clean_lines[1:]
    else:
        N = len(clean_lines[0].split(','))

    grid = []
    for i in range(N):
        row = [int(val.strip()) for val in clean_lines[i].split(',')]
        grid.append(row)

    horiz_constraints = []
    for i in range(N):
        row = [int(val.strip()) for val in clean_lines[N + i].split(',')]
        horiz_constraints.append(row)

    vert_constraints = []
    for i in range(N - 1):
        row = [int(val.strip()) for val in clean_lines[2 * N + i].split(',')]
        vert_constraints.append(row)

    return grid, horiz_constraints, vert_constraints

def print_futoshiki2(grid: list[list[int]], horiz: list[list[int]], vert: list[list[int]], has_border: bool = True):
    """
    Prints the Futoshiki board nicely
    Use '<', '>', '^', and 'v' to represent constraints.
    """
    N = len(grid)
    width = 4 * N - 3
    border = "+" + "-" * (width + 2) + "+"
    
    if has_border:
        print(border)
    for r in range(N):
        row_str = ""
        for c in range(N):
            val = grid[r][c]
            row_str += str(val)
            
            if c < N - 1:
                if horiz[r][c] == 1:
                    row_str += " < "
                elif horiz[r][c] == -1:
                    row_str += " > "
                else:
                    row_str += "   "
        if has_border:
            print(f"| {row_str} |")
        else:
            print(f"{row_str}")

        if r < N - 1:
            vert_str = ""
            for c in range(N):
                if vert[r][c] == 1:
                    vert_str += "^"
                elif vert[r][c] == -1:
                    vert_str += "v"
                else:
                    vert_str += " "
                
                if c < N - 1:
                    vert_str += "   "
            if has_border:
                print(f"| {vert_str} |")
            else:
                print(f"{vert_str}")
    if has_border:
        print(border)