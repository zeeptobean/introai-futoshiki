import heapq
import time
import tracemalloc
from AC3 import FutoshikiAC3


# ====================================================================== #
#  SEARCH STATE                                                           #
# ====================================================================== #

class SearchState:
    """
    Encapsulates all information for a node in A*.

    Attributes:
        board_tuple : tuple[tuple[int]] — immutable board state (key for best_g)
        domains     : dict {(r,c): set} — domains after AC-3, passed to child
        g           : int   — number of assigned cells
        h           : float — heuristic estimate
        f           : float — g + h
        tie_id      : int   — tiebreaker for heapq
    """

    __slots__ = ("board_tuple", "domains", "g", "h", "f", "tie_id")

    def __init__(self, board_tuple, domains, g, h, tie_id=0):
        self.board_tuple = board_tuple
        self.domains     = domains
        self.g           = g
        self.h           = h
        self.f           = g + h
        self.tie_id      = tie_id

    def __lt__(self, other):
        if self.f != other.f:
            return self.f < other.f
        if self.h != other.h:
            return self.h < other.h
        return self.tie_id < other.tie_id

    def __eq__(self, other):
        return self.board_tuple == other.board_tuple

    def __repr__(self):
        return f"SearchState(g={self.g}, h={self.h:.3f}, f={self.f:.3f})"


# ====================================================================== #
#  A* SOLVER                                                              #
# ====================================================================== #

class AStarSolver:
    def __init__(self, game, heuristic="unassigned", use_mrv=True):
        """
        Args:
            game       : instance of Futoshiki class
            heuristic  : "unassigned" | "inequality_chains" |
                            "unforced_cells" | "weighted_domain"
            use_mrv    : use MRV to select next cell
        """
        self.game           = game
        self.n              = game.n
        self.heuristic_name = heuristic
        self.use_mrv        = use_mrv

        # AC-3 instance created once and reused throughout solve()
        self._ac3 = FutoshikiAC3(game)

        # Degree of each cell = number of inequality constraints involved (for MRV tiebreak)
        self.degree = {}
        for (p1, p2) in game.constraints:
            self.degree[p1] = self.degree.get(p1, 0) + 1
            self.degree[p2] = self.degree.get(p2, 0) + 1

    # ------------------------------------------------------------------ #
    #  SOLVE                                                               #
    # ------------------------------------------------------------------ #

    def solve(self, return_stats=False):
        """
        Solve Futoshiki using A* with f(n) = g(n) + h(n).
        """
        solve_start = time.perf_counter()
        tracemalloc.start()
        start_board = self.game.board

        # Initialize full domain once for root state
        start_domains = self._ac3.initial_domains(start_board)
        if start_domains is None:
            stats = self._build_stats(0, 0, 1)
            stats.update(self._runtime_stats(solve_start))
            return (None, stats) if return_stats else None

        start_tuple = tuple(tuple(row) for row in start_board)
        start_h     = self._heuristic(start_tuple, start_domains)
        if start_h == float("inf"):
            stats = self._build_stats(0, 0, 1)
            stats.update(self._runtime_stats(solve_start))
            return (None, stats) if return_stats else None

        tie_id      = 0
        start_state = SearchState(start_tuple, start_domains, g=0, h=start_h, tie_id=0)
        pq          = [start_state]
        best_g      = {start_tuple: 0}

        expanded    = 0
        generated   = 1
        max_queue   = 1

        while pq:
            state  = heapq.heappop(pq)
            expanded += 1

            curr_board = [list(row) for row in state.board_tuple]

            empty_pos = self._find_next_cell(state.board_tuple, state.domains)
            if empty_pos is None:
                is_solved, _ = self.game.is_complete_solution(curr_board)
                if is_solved:
                    stats = self._build_stats(expanded, generated, max_queue)
                    stats.update(self._runtime_stats(solve_start))
                    return (curr_board, stats) if return_stats else curr_board
                continue

            r, c   = empty_pos
            new_g  = state.g + 1

            for val in sorted(state.domains[(r, c)]):
                curr_board[r][c] = val
                new_tuple = tuple(tuple(row) for row in curr_board)
                curr_board[r][c] = 0

                old_g = best_g.get(new_tuple)
                if old_g is not None and new_g >= old_g:
                    continue

                new_domains = self._ac3.incremental_domains(state.domains, r, c, val)
                if new_domains is None:
                    continue

                new_h = self._heuristic(new_tuple, new_domains)
                if new_h != float("inf"):
                    best_g[new_tuple] = new_g
                    tie_id += 1
                    new_state = SearchState(new_tuple, new_domains, new_g, new_h, tie_id)
                    heapq.heappush(pq, new_state)
                    generated += 1
                    if len(pq) > max_queue:
                        max_queue = len(pq)

        stats = self._build_stats(expanded, generated, max_queue)
        stats.update(self._runtime_stats(solve_start))
        return (None, stats) if return_stats else None

    # ------------------------------------------------------------------ #
    #  CHỌN Ô TIẾP THEO (MRV)                                            #
    # ------------------------------------------------------------------ #

    def _find_next_cell(self, board_tuple, domains):
        """
        Receive board_tuple directly — no need to convert to list.
        MRV: select empty cell with smallest |domain|, tiebreak by degree.
        """
        if not self.use_mrv:
            for r, row in enumerate(board_tuple):
                for c, v in enumerate(row):
                    if v == 0:
                        return (r, c)
            return None

        n          = self.n
        min_remain = n + 1
        best_cell  = None

        for r, row in enumerate(board_tuple):
            for c, v in enumerate(row):
                if v != 0:
                    continue
                dom_size = len(domains[(r, c)])
                if dom_size == 0:
                    return None
                if dom_size < min_remain or (
                    dom_size == min_remain
                    and self.degree.get((r, c), 0) > self.degree.get(best_cell, 0)
                ):
                    min_remain = dom_size
                    best_cell  = (r, c)

        return best_cell

    # ------------------------------------------------------------------ #
    #  HEURISTICS                                                          #
    # ------------------------------------------------------------------ #

    def _heuristic(self, board_tuple, domains):
        funcs = {
            "unassigned":        self._h_unassigned,
            "inequality_chains": self._h_inequality_chains,
            "unforced_cells":    self._h_unforced_cells,
            "weighted_domain":   self._h_weighted_domain,
        }
        fn = funcs.get(self.heuristic_name)
        if fn is None:
            raise ValueError(f"Unknown heuristic: {self.heuristic_name}")
        return fn(board_tuple, domains)

    def _h_unassigned(self, board_tuple, domains):
        """
        h1 — Number of remaining empty cells.
        """
        count = 0
        for r, row in enumerate(board_tuple):
            for c, v in enumerate(row):
                if v != 0:
                    continue
                if not domains[(r, c)]:
                    return float("inf")
                count += 1
        return count

    def _h_inequality_chains(self, board_tuple, domains):
        """
        h2 — Number of empty cells in at least one unsatisfied inequality constraint.
        """
        # Check empty domains first (fast)
        for r, row in enumerate(board_tuple):
            for c, v in enumerate(row):
                if v == 0 and not domains[(r, c)]:
                    return float("inf")

        involved = set()
        for r1, c1, r2, c2 in self.game._ineq_pairs:
            v1 = board_tuple[r1][c1]
            v2 = board_tuple[r2][c2]
            if v1 and v2 and v1 >= v2:
                return float("inf")
            if not v1:
                involved.add((r1, c1))
            if not v2:
                involved.add((r2, c2))

        return len(involved)

    def _h_unforced_cells(self, board_tuple, domains):
        """
        h3 — Number of empty cells with |domain| > 1.
        """
        h = 0
        for r, row in enumerate(board_tuple):
            for c, v in enumerate(row):
                if v != 0:
                    continue
                dom = domains[(r, c)]
                if not dom:
                    return float("inf")
                if len(dom) > 1:
                    h += 1
        return h

    def _h_weighted_domain(self, board_tuple, domains):
        """
        h4 — Sum of (|domain|-1)/N for empty cells.
        """
        n = self.n
        h = 0.0
        for r, row in enumerate(board_tuple):
            for c, v in enumerate(row):
                if v != 0:
                    continue
                dom = domains[(r, c)]
                if not dom:
                    return float("inf")
                h += (len(dom) - 1) / n
        return h

    # ------------------------------------------------------------------ #
    #  STATS                                                               #
    # ------------------------------------------------------------------ #

    def _build_stats(self, expanded, generated, max_queue):
        return {
            "heuristic":       self.heuristic_name,
            "expanded_nodes":  expanded,
            "generated_nodes": generated,
            "max_queue_size":  max_queue,
        }

    def _runtime_stats(self, solve_start):
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return {
            "execution_time": time.perf_counter() - solve_start,
            "memory_usage": peak,
        }
