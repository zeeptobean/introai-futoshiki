"""PLAY tab behaviors for the Futoshiki GUI."""


class PlayTabMixin:
    def _hint_action(self) -> None:
        if self.solution_cache is None:
            if self.pending_request_mode == "play_auto_cache":
                self.status_text = "Hint unavailable: PLAY answer cache is still preparing."
            else:
                self.status_text = "Hint unavailable: open PLAY to prepare answer cache first."
            return
        self._apply_hint_from_cache()

    def _apply_hint_from_cache(self) -> None:
        if self.solution_cache is None:
            return
        target = self.selected_cell
        if target is None:
            for r in range(self.puzzle.size):
                for c in range(self.puzzle.size):
                    if self.play_board[r][c] != self.solution_cache[r][c]:
                        target = (r, c)
                        break
                if target is not None:
                    break

        if target is None:
            self.status_text = "Hint: board already matches solved state."
            return

        r, c = target
        self.selected_cell = target
        hint_val = self.solution_cache[r][c]
        self._apply_cell_value(r, c, hint_val)
        self.status_text = "Hint filled ({}, {}) = {}".format(r + 1, c + 1, hint_val)

    def _solution_action(self) -> None:
        if self.solution_cache is None:
            if self.pending_request_mode == "play_auto_cache":
                self.status_text = "Show Answer unavailable: PLAY answer cache is still preparing."
            else:
                self.status_text = "Show Answer unavailable: open PLAY to prepare answer cache first."
            return

        self._apply_solution_cache()

    def _on_play_tab_enter(self) -> None:
        self._prepare_play_answer_cache()

    def _apply_solution_cache(self) -> None:
        if self.solution_cache is None:
            return
        self.play_board = [row[:] for row in self.solution_cache]
        self.undo_stack = []
        self.error_cells = set()
        self._update_play_completed_state()
        self.status_text = "Solution applied to board."

    def _check_action(self) -> None:
        issues = self._analyze_board_issues(self.play_board)
        self.error_cells = self._cells_from_issues(issues)

        has_empty = any(0 in row for row in self.play_board)
        if not issues and not has_empty:
            self.play_completed = True
            self.status_text = "Check: correct solution."
        elif not issues and has_empty:
            self.play_completed = False
            self.status_text = "Check: board is valid so far but incomplete."
        else:
            self.play_completed = False
            self.status_text = "Check: {}".format(issues[0]["message"])

    def _undo_move(self) -> None:
        if not self.undo_stack:
            self.status_text = "Undo: nothing to revert."
            return

        r, c, prev, _ = self.undo_stack.pop()

        # Undo on correct board based on scene
        if self.scene == "MENU":
            self.menu_board[r][c] = prev
        elif self.scene == "SOLVE":
            self.display_board[r][c] = prev
        else:  # PLAY
            self.play_board[r][c] = prev

        if self.scene == "PLAY":
            self.error_cells = self._collect_invalid_cells(self.play_board)
            self._update_play_completed_state()
        self.status_text = "Undo: reverted cell ({}, {}).".format(r + 1, c + 1)

    def _reset_play_view(self) -> None:
        """Reset PLAY display board to initial without affecting puzzle state."""
        self.play_board = [row[:] for row in self.initial_board]
        self.undo_stack = []
        self.error_cells = set()
        self.selected_cell = None
        self.play_completed = False
        self.status_text = "PLAY display reset to initial board."

    def _update_play_completed_state(self) -> None:
        issues = self._analyze_board_issues(self.play_board)
        has_empty = any(0 in row for row in self.play_board)
        self.play_completed = (not issues) and (not has_empty)
        if self.play_completed:
            self.status_text = "Play solved."
