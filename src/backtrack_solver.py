from AC3 import FutoshikiAC3
import time


class BacktrackSolver:
    def __init__(self, game, use_mrv=True, use_ac3=True):
        """
        Args:
            game    : instance of Futoshiki class
            use_mrv : use MRV to select next cell
            use_ac3 : use incremental AC-3 for forward-checking
        """
        self.game    = game
        self.use_mrv = use_mrv
        self.use_ac3 = use_ac3

        # AC-3 instance created once and reused throughout _search()
        self._ac3 = FutoshikiAC3(game) if use_ac3 else None

    def solve(self, return_stats=False, trace_callback=None):
        """
        Solve using depth-first backtracking.

        Returns:
            solved board or None.
            If return_stats=True --> (solution_or_none, stats_dict).
        """
        solve_start = time.perf_counter()
        trace_step = 0

        def emit(action, board=None, focus_cell=None, message="", metadata=None):
            nonlocal trace_step
            if trace_callback is None:
                return
            trace_step += 1
            trace_callback({
                "action": action,
                "step_index": trace_step,
                "board": board if board is not None else None,
                "focus_cell": focus_cell,
                "message": message,
                "metadata": metadata or {},
            })

        stats = {
            "algorithm":     "backtracking",
            "use_mrv":       self.use_mrv,
            "use_ac3":       self.use_ac3,
            "visited_nodes": 0,
            "backtracks":    0,
            "max_recursion_depth": 0,
        }

        board = [row[:] for row in self.game.board]
        emit("started", board, message="Backtracking started")

        # Initialize full domain once for root
        if self.use_ac3:
            root_domains = self._ac3.initial_domains(board)
            if root_domains is None:
                emit("failed", board, message="Initial AC-3 found contradiction")
                return (None, stats) if return_stats else None
        else:
            root_domains = None

        solution = self._search(board, root_domains, stats, depth=1, emit=emit)
        stats["execution_time"] = time.perf_counter() - solve_start
        if solution is None:
            emit("failed", board, message="Backtracking exhausted without solution")
        else:
            emit("solved", solution, message="Backtracking solved puzzle")
        return (solution, stats) if return_stats else solution

    def _search(self, board, domains, stats, depth, emit):
        stats["visited_nodes"] += 1
        if depth > stats["max_recursion_depth"]:
            stats["max_recursion_depth"] = depth

        emit(
            "node_expanded",
            board,
            message="Explore recursive node",
            metadata={
                "depth": depth,
                "visited_nodes": stats["visited_nodes"],
                "backtracks": stats["backtracks"],
            },
        )

        if not self.game.has_empty_cell(board):
            solved, _ = self.game.is_complete_solution(board)
            if solved:
                return [row[:] for row in board]
            stats["backtracks"] += 1
            return None

        pos = self._select_next_cell(board, domains)
        if pos is None:
            stats["backtracks"] += 1
            emit("backtrack", board, message="No selectable cell", metadata={"depth": depth})
            return None

        r, c = pos

        if domains is not None:
            candidates = sorted(domains.get((r, c), set()))
        else:
            candidates = sorted(self.game.get_valid_values(board, r, c))

        if not candidates:
            stats["backtracks"] += 1
            emit("backtrack", board, focus_cell=(r, c), message="No candidates for selected cell", metadata={"depth": depth})
            return None

        for val in candidates:
            if not self.game.check_assignment(board, r, c, val):
                continue

            board[r][c] = val
            emit(
                "assign",
                board,
                focus_cell=(r, c),
                message="Try assignment",
                metadata={"value": val, "depth": depth},
            )

            # Incremental AC-3: pass parent_domains down to child
            if self.use_ac3:
                child_domains = self._ac3.incremental_domains(domains, r, c, val)
                if child_domains is None:
                    emit(
                        "contradiction",
                        board,
                        focus_cell=(r, c),
                        message="AC-3 contradiction after assignment",
                        metadata={"value": val, "depth": depth},
                    )
                    board[r][c] = 0
                    continue
            else:
                child_domains = None

            found = self._search(board, child_domains, stats, depth + 1, emit)
            if found is not None:
                return found

            board[r][c] = 0
            emit(
                "backtrack",
                board,
                focus_cell=(r, c),
                message="Undo assignment",
                metadata={"value": val, "depth": depth},
            )

        stats["backtracks"] += 1
        emit("backtrack", board, focus_cell=(r, c), message="All candidates exhausted", metadata={"depth": depth})
        return None

    def _select_next_cell(self, board, domains):
        if not self.use_mrv:
            for r in range(self.game.n):
                for c in range(self.game.n):
                    if board[r][c] == 0:
                        return (r, c)
            return None

        best_cell = None
        best_size = self.game.n + 1

        for r in range(self.game.n):
            for c in range(self.game.n):
                if board[r][c] != 0:
                    continue
                if domains is not None:
                    dom_size = len(domains.get((r, c), set()))
                else:
                    dom_size = len(self.game.get_valid_values(board, r, c))

                if dom_size == 0:
                    return (r, c)
                if dom_size < best_size:
                    best_size = dom_size
                    best_cell = (r, c)

        return best_cell
