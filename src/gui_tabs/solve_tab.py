"""SOLVE tab behaviors for the Futoshiki GUI."""

import time
from typing import List, Optional, Tuple

import pygame
from gui_api import SolverStatus

SPEED_MIN = 0.25
SPEED_MAX = 20.0


class SolveTabMixin:
    def _on_solve_play(self) -> None:
        # If worker is busy with a non-SOLVE task, preempt it and restart solve.
        if self.worker_state in ("running", "paused", "step_ack") and self.pending_request_mode != "solve":
            self._restart_solve_on_idle = True
            self.animation_playing = False
            self.worker.stop_current()
            self.status_text = "Stopping background task and starting SOLVE..."
            return

        current_key = self._current_solver_key()

        if self.trace_solver_key != current_key:
            self.status_text = "Algorithm changed. Re-solving with {}.".format(self.selected_algo_label)
            self.trace_events = []
            self.trace_cursor = 0
            self.latest_result = None
            self.solution_cache = None
            self.solution_cache_signature = None
            self.solution_cache_source = ""
            self.solve_completed = False
            self.solve_no_solution = False
            self.pending_request_mode = None
            if self.worker_state in ("running", "paused", "step_ack"):
                self._restart_solve_on_idle = True
                self.worker.stop_current()
            else:
                self._start_solving()
            return

        # Resume worker first when paused/step-ack; this should always continue current run.
        if self.worker_state in ("paused", "step_ack"):
            self.worker.resume()

        has_unplayed_trace = self.trace_cursor < len(self.trace_events)
        is_done_for_current = (
            self.latest_result is not None
            and self.worker_state == "idle"
            and self.latest_result.status in (SolverStatus.SOLVED, SolverStatus.UNSAT)
            and not has_unplayed_trace
        )
        if is_done_for_current:
            self.status_text = "Solve already finished for current algorithm."
            return

        # If no trace exists yet, Play starts solve immediately.
        if self.worker_state == "idle" and not self.trace_events:
            self._start_solving()
            return

        # If there are remaining trace events (or incoming ones), keep animating.
        self.animation_playing = True

    def _start_solving(self) -> None:
        if self.worker_state == "running":
            self.status_text = "Solve is already running."
            return

        self.trace_events = []
        self.trace_solver_key = self._current_solver_key()
        self.trace_cursor = 0
        self.display_board = self.puzzle.clone_board()
        self.latest_result = None
        self.animation_playing = True
        self.animation_focus_cell = None
        self.animation_focus_action = ""
        self.solve_completed = False
        self.solve_no_solution = False
        self.pending_request_mode = "solve"
        self.status_text = "Solving..."
        self.algo_dropdown_open = False
        self.input_dropdown_open = False
        self._last_anim_tick = time.time()

        config = self._build_selected_solver_config()
        self.worker.submit_solve(self._clone_puzzle(), config)

    def _show_answer_action(self) -> None:
        if self.solution_cache is None:
            self.status_text = "Show Answer unavailable: press Play to solve first."
            return

        self._apply_solve_answer_from_cache()

    def _apply_solve_answer_from_cache(self) -> None:
        if self.solution_cache is None:
            return
        self.display_board = [row[:] for row in self.solution_cache]
        self.trace_cursor = len(self.trace_events)
        self.animation_playing = False
        self.animation_focus_cell = None
        self.animation_focus_action = ""
        self.solve_completed = True
        self.solve_no_solution = False
        self.status_text = "Answer displayed in SOLVE view."

    def _reset_solve_view(self) -> None:
        """Reset SOLVE animation view without clearing trace events."""
        self.display_board = self.puzzle.clone_board()
        self.trace_cursor = 0
        self.animation_playing = False
        self.animation_focus_cell = None
        self.animation_focus_action = ""
        self.solve_completed = False
        self.solve_no_solution = False
        self.play_completed = False
        # Keep worker and pending solve untouched; reset only clears animation surface state.
        self._last_anim_tick = time.time()
        self.status_text = "SOLVE view reset. Trace preserved."

    def _update_animation(self) -> None:
        if not self.animation_playing:
            return
        if self.scene != "SOLVE":
            return
        interval = 1.0 / max(0.1, self.animation_speed)
        if time.time() - self._last_anim_tick < interval:
            return
        self._last_anim_tick = time.time()
        self._apply_next_trace_event()

    def _apply_next_trace_event(self) -> None:
        if self.trace_cursor >= len(self.trace_events):
            if self.pending_request_mode == "solve" and self.worker_state == "running":
                return
            self.animation_playing = False
            if self.latest_result is not None:
                if self.latest_result.status == SolverStatus.SOLVED:
                    self.solve_completed = True
                    self.solve_no_solution = False
                elif self.latest_result.status == SolverStatus.UNSAT:
                    self.solve_completed = False
                    self.solve_no_solution = True
            return

        prev_board = [row[:] for row in self.display_board]
        event = self.trace_events[self.trace_cursor]
        self.trace_cursor += 1
        if event.board_snapshot is not None:
            self.display_board = [row[:] for row in event.board_snapshot]

        focus = event.focus_cell
        if focus is None and event.board_snapshot is not None:
            focus = self._infer_focus_cell(prev_board, event.board_snapshot)
        self.animation_focus_cell = focus

        action = getattr(event.action, "value", str(event.action))
        self.animation_focus_action = action

        if event.message:
            self.status_text = event.message

    @staticmethod
    def _infer_focus_cell(before: List[List[int]], after: List[List[int]]) -> Optional[Tuple[int, int]]:
        changed = []
        for r in range(len(after)):
            for c in range(len(after[r])):
                if before[r][c] != after[r][c]:
                    changed.append((r, c))
        if not changed:
            return None
        return changed[0]

    def _set_animation_speed_from_pos(self, x: int, track: pygame.Rect) -> None:
        ratio = (x - track.left) / float(max(1, track.width))
        ratio = max(0.0, min(1.0, ratio))
        self.animation_speed = SPEED_MIN + ratio * (SPEED_MAX - SPEED_MIN)

    def _handle_speed_slider_drag(self, pos: Tuple[int, int]) -> None:
        layout = self._layout(*self.screen.get_size())
        slider = layout.get("speed_slider")
        if slider is None:
            return
        self._set_animation_speed_from_pos(pos[0], slider["track"])
