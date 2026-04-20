class Futoshiki:
    def __init__(self, size, board, constraints):
        self.n           = size
        self.board       = board
        self.constraints = constraints

        self.given_cells = {
            (r, c): board[r][c]
            for r in range(size) for c in range(size)
            if board[r][c] != 0
        }

        self._ineq_pairs = tuple(
            (r1, c1, r2, c2)
            for (r1, c1), (r2, c2) in constraints
        )

        self._neighbor_index = self._build_neighbor_index()

    # ------------------------------------------------------------------ #
    #  NEIGHBOR INDEX                                                    #
    # ------------------------------------------------------------------ #

    def _build_neighbor_index(self):
        """
        Build {(r,c): set of neighbors}.
        """
        n     = self.n
        cells = [(r, c) for r in range(n) for c in range(n)]
        index = {}

        for r, c in cells:
            nb = set()
            # Same row
            nb.update((r, j) for j in range(n) if j != c)
            # Same col
            nb.update((i, c) for i in range(n) if i != r)
            # Inequality constraints
            for r1, c1, r2, c2 in self._ineq_pairs:
                if r1 == r and c1 == c:
                    nb.add((r2, c2))
                elif r2 == r and c2 == c:
                    nb.add((r1, c1))
            index[(r, c)] = nb

        return index

    def get_neighbors(self, r, c):
        """Return list of cells directly constrained with (r,c)."""
        return list(self._neighbor_index[(r, c)])

    # ------------------------------------------------------------------ #
    #  KIỂM TRA CONSTRAINT                                                 #
    # ------------------------------------------------------------------ #

    def is_valid(self, r, c, val, board):
        """
        Check if val is valid at cell (r,c) with current board.
        """
        # Clue check — if this cell is pre-filled, val must match
        given = self.given_cells.get((r, c))
        if given is not None and val != given:
            return False

        # Row uniqueness
        row = board[r]
        for j in range(self.n):
            if j != c and row[j] == val:
                return False

        # Col uniqueness
        for i in range(self.n):
            if i != r and board[i][c] == val:
                return False

        # Inequality constraints
        for r1, c1, r2, c2 in self._ineq_pairs:
            v1 = val if (r1 == r and c1 == c) else board[r1][c1]
            v2 = val if (r2 == r and c2 == c) else board[r2][c2]
            if v1 and v2 and v1 >= v2:
                return False

        return True

    def check_assignment(self, board, r, c, val):
        """
        Check if assigning val to (r,c) is valid — inlined version of is_valid()
        to avoid extra function call overhead.
        """
        given = self.given_cells.get((r, c))
        if given is not None and val != given:
            return False

        row = board[r]
        for j in range(self.n):
            if j != c and row[j] == val:
                return False

        for i in range(self.n):
            if i != r and board[i][c] == val:
                return False

        for r1, c1, r2, c2 in self._ineq_pairs:
            v1 = val if (r1 == r and c1 == c) else board[r1][c1]
            v2 = val if (r2 == r and c2 == c) else board[r2][c2]
            if v1 and v2 and v1 >= v2:
                return False

        return True

    def get_valid_values(self, board, r, c):
        """Get set of valid values at cell (r,c) with current board."""
        if board[r][c] != 0:
            return {board[r][c]}
        return {v for v in range(1, self.n + 1) if self.is_valid(r, c, v, board)}

    def get_possibilities(self, r, c, board):
        """Get ordered list of possible values at cell (r,c) — ordered alias version."""
        return [v for v in range(1, self.n + 1) if self.is_valid(r, c, v, board)]

    # ------------------------------------------------------------------ #
    #  TRẠNG THÁI BOARD                                                    #
    # ------------------------------------------------------------------ #

    def has_empty_cell(self, board):
        """Return True if board has any empty cells."""
        return any(0 in row for row in board)

    def is_complete_solution(self, board):
        """
        Check if board is a complete and valid solution.

        Returns: (True, None) | (False, reason_str)
        """
        n = self.n

        if self.has_empty_cell(board):
            return False, "incomplete_board"

        # Row uniqueness
        for r in range(n):
            if len(set(board[r])) != n:
                return False, f"row_duplicate(row={r})"

        # Col uniqueness — no intermediate list
        for c in range(n):
            if len({board[r][c] for r in range(n)}) != n:
                return False, f"col_duplicate(col={c})"

        # Inequality constraints
        for r1, c1, r2, c2 in self._ineq_pairs:
            if board[r1][c1] >= board[r2][c2]:
                return False, f"inequality_violated({r1},{c1}<{r2},{c2})"

        # Clue cells
        for (r, c), v in self.given_cells.items():
            if board[r][c] != v:
                return False, f"clue_violated({r},{c}={v})"

        return True, None
    
    def _build_constraint_grids(self):
        """
        Build horizontal/vertical constraint matrices from self.constraints.

        h[r][c] is relation between (r,c) and (r,c+1):
            1  => left < right
        -1  => left > right
            0  => no constraint

        v[r][c] is relation between (r,c) and (r+1,c):
            1  => top < bottom
        -1  => top > bottom
            0  => no constraint
        """
        n = self.n
        h = [[0] * (n - 1) for _ in range(n)]
        v = [[0] * n for _ in range(n - 1)]

        for (r1, c1), (r2, c2) in self.constraints:
            if r1 == r2 and abs(c1 - c2) == 1:
                left_col = min(c1, c2)
                h[r1][left_col] = 1 if c1 < c2 else -1
            elif c1 == c2 and abs(r1 - r2) == 1:
                top_row = min(r1, r2)
                v[top_row][c1] = 1 if r1 < r2 else -1

        return h, v

    def __repr__(self):
        grid = self.board
        n = self.n
        h, v = self._build_constraint_grids()

        width = 4 * n - 3
        border = "+" + "-" * (width + 2) + "+"

        lines = [border]

        for r in range(n):
            row_str = ""
            for c in range(n):
                val = grid[r][c]
                row_str += str(val)

                if c < n - 1:
                    if h[r][c] == 1:
                        row_str += " < "
                    elif h[r][c] == -1:
                        row_str += " > "
                    else:
                        row_str += "   "

            lines.append("| " + row_str + " |")

            if r < n - 1:
                vert_str = ""
                for c in range(n):
                    if v[r][c] == 1:
                        vert_str += "^"
                    elif v[r][c] == -1:
                        vert_str += "v"
                    else:
                        vert_str += " "

                    if c < n - 1:
                        vert_str += "   "

                lines.append("| " + vert_str + " |")

        lines.append(border)
        return "\n".join(lines)
