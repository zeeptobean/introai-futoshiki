"""MENU tab behaviors for the Futoshiki GUI."""

import os
from typing import List, Optional, Tuple

from gui_api import PuzzleSpec
from gui_api.puzzle_io import load_puzzle_from_file, save_puzzle_to_file

SIZE_OPTIONS = [4, 5, 6, 7, 9]


class MenuTabMixin:
    def _load_selected_input(self) -> None:
        if not self.input_files:
            self.status_text = "No Inputs/input-*.txt found."
            return
        try:
            self.puzzle = load_puzzle_from_file(self.input_files[self.input_index])
            self.display_board = self.puzzle.clone_board()
            self.play_board = self.puzzle.clone_board()
            self.menu_board = self.puzzle.clone_board()
            self.menu_constraints = list(self.puzzle.constraints)
            self.solution_cache = None
            self.solution_cache_signature = None
            self.solution_cache_source = ""
            self.trace_events = []
            self.trace_solver_key = None
            self.trace_cursor = 0
            self.selected_cell = None
            self.undo_stack = []
            self.error_cells = set()
            self.play_completed = False
            self.initial_board = self.puzzle.clone_board()
            self.initial_constraints = list(self.puzzle.constraints)
            self.initial_given_cells = self._compute_given_cells(self.initial_board)
            self.status_text = "Loaded {}. Ready to solve.".format(self.input_files[self.input_index])
        except Exception as exc:
            self.status_text = "Load failed: {}".format(exc)

    def _set_puzzle_size(self, size: int) -> None:
        if size not in SIZE_OPTIONS:
            return
        self.puzzle = PuzzleSpec(size=size, board=[[0] * size for _ in range(size)], constraints=[])
        self.display_board = self.puzzle.clone_board()
        self.play_board = self.puzzle.clone_board()
        self.menu_board = self.puzzle.clone_board()
        self.menu_constraints = []
        self.solution_cache = None
        self.solution_cache_signature = None
        self.solution_cache_source = ""
        self.trace_events = []
        self.trace_solver_key = None
        self.trace_cursor = 0
        self.selected_cell = None
        self.undo_stack = []
        self.error_cells = set()
        self.play_completed = False
        self.initial_board = self.puzzle.clone_board()
        self.initial_constraints = list(self.puzzle.constraints)
        self.initial_given_cells = self._compute_given_cells(self.initial_board)
        self.status_text = "Created new {}x{} board.".format(size, size)

    def _reset_menu_view(self) -> None:
        """Clear MENU editor board and constraints for current size."""
        size = self.puzzle.size
        self.menu_board = [[0] * size for _ in range(size)]
        self.menu_constraints = []
        self.solution_cache = None
        self.solution_cache_signature = None
        self.solution_cache_source = ""
        self.undo_stack = []
        self.error_cells = set()
        self.selected_cell = None
        self.trace_events = []
        self.trace_solver_key = None
        self.trace_cursor = 0
        self.animation_playing = False
        self.animation_focus_cell = None
        self.animation_focus_action = ""
        self.solve_completed = False
        self.solve_no_solution = False
        self.play_completed = False
        self.latest_result = None
        self.pending_request_mode = None
        self.status_text = "MENU reset: cleared board and all constraints."

    def _save_menu_state(self) -> None:
        """Commit MENU editor state to puzzle and sync all tabs without auto-solving."""
        if self.scene != "MENU":
            return

        self.puzzle.board = [row[:] for row in self.menu_board]
        self.puzzle.constraints = list(self.menu_constraints)
        self.display_board = self.puzzle.clone_board()
        self.play_board = self.puzzle.clone_board()

        self.initial_board = self.puzzle.clone_board()
        self.initial_constraints = list(self.puzzle.constraints)
        self.initial_given_cells = self._compute_given_cells(self.initial_board)

        self.solution_cache = None
        self.solution_cache_signature = None
        self.solution_cache_source = ""
        self.trace_events = []
        self.trace_solver_key = None
        self.trace_cursor = 0
        self.undo_stack = []
        self.error_cells = set()
        self.selected_cell = None
        self.animation_playing = False
        self.animation_focus_cell = None
        self.animation_focus_action = ""
        self.solve_completed = False
        self.solve_no_solution = False
        self.play_completed = False
        self.latest_result = None

        self.status_text = "Saved MENU state. Ready to solve."

    def _save_temp_input(self) -> None:
        out_path = os.path.join("Inputs", "temp-gui.txt")
        try:
            if self.scene == "MENU":
                puzzle = PuzzleSpec(
                    size=self.puzzle.size,
                    board=[row[:] for row in self.menu_board],
                    constraints=list(self.menu_constraints),
                )
            else:
                puzzle = self.puzzle

            save_puzzle_to_file(puzzle, out_path, comment="Saved from GUI")
            self.status_text = "Saved {}".format(out_path)
        except Exception as exc:
            self.status_text = "Save failed: {}".format(exc)

    def _cycle_constraint_slot(self, slot: Tuple[str, int, int]) -> None:
        axis, r, c = slot

        if axis == "h":
            a = (r, c)
            b = (r, c + 1)
        else:
            a = (r, c)
            b = (r + 1, c)

        con = list(self.menu_constraints)
        idx_ab = self._constraint_index(con, a, b)
        idx_ba = self._constraint_index(con, b, a)

        if idx_ab is not None:
            con[idx_ab] = (b, a)
            self.status_text = "Constraint switched: ({},{}) < ({},{}).".format(
                b[0] + 1, b[1] + 1, a[0] + 1, a[1] + 1
            )
        elif idx_ba is not None:
            con.pop(idx_ba)
            self.status_text = "Constraint removed."
        else:
            con.append((a, b))
            self.status_text = "Constraint added: ({},{}) < ({},{}).".format(
                a[0] + 1, a[1] + 1, b[0] + 1, b[1] + 1
            )

        self.menu_constraints = con

    @staticmethod
    def _constraint_index(constraints: List[Tuple[Tuple[int, int], Tuple[int, int]]], a, b) -> Optional[int]:
        for i, pair in enumerate(constraints):
            if pair[0] == a and pair[1] == b:
                return i
        return None

    def _constraint_slot_from_pos(
        self,
        pos: Tuple[int, int],
        board_rect,
        n: int,
    ) -> Optional[Tuple[str, int, int]]:
        geom = self._board_geometry(board_rect, n)

        for r in range(n):
            for c in range(n - 1):
                if self._h_slot_rect(geom, r, c).collidepoint(pos):
                    return ("h", r, c)

        for r in range(n - 1):
            for c in range(n):
                if self._v_slot_rect(geom, r, c).collidepoint(pos):
                    return ("v", r, c)

        return None
