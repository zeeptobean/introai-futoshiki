from collections import deque


class FutoshikiAC3:
    def __init__(self, game):
        """
        Store only game and pre-compute static indices.
        Domain is NOT initialized here — passed in when used.

        Args:
            game : instance of Futoshiki
        """
        self.game = game
        self.n    = game.n

        self._neighbors = game._neighbor_index

        self._ineq_set = frozenset(
            (p1, p2) for (p1, p2) in game.constraints
        )

    # ------------------------------------------------------------------ #
    #  KHỞI TẠO DOMAIN ĐẦY ĐỦ — chỉ gọi 1 lần cho state gốc            #
    # ------------------------------------------------------------------ #

    def initial_domains(self, board):
        """
        Initialize domains for all N² cells from the board,
        then run full AC-3.

        Called only once at the beginning of solve.
        All child states use incremental_domains().

        Returns:
            dict {(r,c): set} — domains after AC-3, or None if contradiction
        """
        domains = {
            (r, c): self.game.get_valid_values(board, r, c)
            for r in range(self.n)
            for c in range(self.n)
        }
        queue = deque()
        for r in range(self.n):
            for c in range(self.n):
                for nb in self._neighbors[(r, c)]:
                    queue.append(((r, c), nb))

        consistent = self._run_ac3(domains, queue)
        return domains if consistent else None

    # ------------------------------------------------------------------ #
    #  INCREMENTAL — propagate từ ô vừa gán, không reinit               #
    # ------------------------------------------------------------------ #

    def incremental_domains(self, parent_domains, r, c, val):
        """
        Compute domains for child state after assigning (r,c) = val,
        starting from parent_domains.

        Args:
            parent_domains : dict {(r,c): set} — domains of parent state
            r, c           : assigned cell
            val            : assigned value

        Returns:
            dict {(r,c): set} — new domains, or None if contradiction
        """
        domains = {cell: s.copy() for cell, s in parent_domains.items()}

        domains[(r, c)] = {val}

        queue = deque((nb, (r, c)) for nb in self._neighbors[(r, c)])

        consistent = self._run_ac3(domains, queue)
        return domains if consistent else None

    # ------------------------------------------------------------------ #
    #  VÒNG LẶP AC-3                                                      #
    # ------------------------------------------------------------------ #

    def _run_ac3(self, domains, queue):
        """
        Common AC-3 loop, accepts any queue.

        Returns:
            True  — consistent (no empty domain)
            False — contradiction (empty domain exists)
        """
        while queue:
            Xi, Xj = queue.popleft()

            if self._revise(domains, Xi, Xj):
                if not domains[Xi]:
                    return False  # Contradiction — domain Xi is empty

                # Domain Xi shrunk → neighbors of Xi need re-examination
                for Xk in self._neighbors[Xi]:
                    if Xk != Xj:
                        queue.append((Xk, Xi))

        return True

    # ------------------------------------------------------------------ #
    #  REVISE TRỰC TIẾP                                                  #
    # ------------------------------------------------------------------ #

    def _revise(self, domains, Xi, Xj):
        """
        Remove from domain[Xi] values that have no support from domain[Xj].

        Check constraint type between (Xi, Xj) directly:
          - Uniqueness (same row or col):  x != y
          - Inequality Xi < Xj:            x < y
          - Inequality Xj < Xi (Xi > Xj):  x > y

        Returns:
            True  if domain[Xi] was pruned
            False if unchanged
        """
        ri, ci = Xi
        rj, cj = Xj

        is_unique        = (ri == rj or ci == cj)
        is_Xi_lt_Xj     = (Xi, Xj) in self._ineq_set   # board[Xi] < board[Xj]
        is_Xi_gt_Xj     = (Xj, Xi) in self._ineq_set   # board[Xj] < board[Xi]

        dom_Xj  = domains[Xj]
        to_remove = set()

        for x in domains[Xi]:
            has_support = False
            for y in dom_Xj:
                if is_unique and x == y:
                    continue
                if is_Xi_lt_Xj and x >= y:
                    continue
                if is_Xi_gt_Xj and x <= y:
                    continue
                has_support = True
                break

            if not has_support:
                to_remove.add(x)

        if not to_remove:
            return False

        domains[Xi] -= to_remove
        return True

    # ------------------------------------------------------------------ #
    #  STATIC HELPER — API thống nhất cho A* và Backtracking             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def solve_state(game, ac3, parent_domains, r, c, val):
        """
        Incremental AC-3 for one child state.

        Args:
            game           : Futoshiki instance (only used if ac3 is None)
            ac3            : FutoshikiAC3 instance already created
            parent_domains : domains of parent state
            r, c           : assigned cell
            val            : assigned value

        Returns:
            dict {(r,c): set} or None if contradiction
        """
        return ac3.incremental_domains(parent_domains, r, c, val)
