"""Pygame GUI shell for Futoshiki with Play/Solve/Menu scenes.

Phase C shell goals:
- render puzzle board and inequalities
- edit board and constraints
- run solver in worker thread and animate trace events
- provide basic hint/check flow for Play mode
"""

import glob
import os
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import pygame

from gui_api import PuzzleSpec, SolverConfig, SolverResult, SolverStatus, SolverType, SolverWorker
from gui_api.puzzle_io import load_puzzle_from_file
from gui_tabs.menu_tab import MenuTabMixin
from gui_tabs.play_tab import PlayTabMixin
from gui_tabs.solve_tab import SolveTabMixin

try:
    from futoshiki import Futoshiki
except ImportError:  # pragma: no cover
    from src.futoshiki import Futoshiki


SCENES = ["PLAY", "SOLVE", "MENU"]
SIZE_OPTIONS = [4, 5, 6, 7, 9]
ALGO_OPTIONS = [
    {"label": "A* weighted_domain", "solver": SolverType.ASTAR, "heuristic": "weighted_domain"},
    {"label": "A* inequality_chains", "solver": SolverType.ASTAR, "heuristic": "inequality_chains"},
    {"label": "A* unforced_cells", "solver": SolverType.ASTAR, "heuristic": "unforced_cells"},
    {"label": "A* unassigned", "solver": SolverType.ASTAR, "heuristic": "unassigned"},
    {"label": "Backtracking (MRV + AC3)", "solver": SolverType.BACKTRACK, "heuristic": None},
    {"label": "Forward chaining (fc31)", "solver": SolverType.FORWARD_CHAINING, "heuristic": None},
    {"label": "Backward chaining (bc3)", "solver": SolverType.BACKWARD_CHAINING, "heuristic": None},
]

SPEED_MIN = 0.25
SPEED_MAX = 20.0
DROPDOWN_MAX_HEIGHT = 220
DROPDOWN_LIST_PADDING = 4
DROPDOWN_SCROLL_STEP = 28


@dataclass
class Button:
    label: str
    rect: pygame.Rect

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, active: bool = False) -> None:
        bg = (67, 107, 184) if active else (219, 223, 228)
        fg = (248, 251, 255) if active else (35, 45, 66)
        pygame.draw.rect(surface, bg, self.rect, border_radius=8)
        pygame.draw.rect(surface, (140, 150, 168), self.rect, 1, border_radius=8)
        text = font.render(self.label, True, fg)
        text_rect = text.get_rect(center=self.rect.center)
        surface.blit(text, text_rect)

    def hit(self, pos: Tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)


class FutoshikiGUI(PlayTabMixin, SolveTabMixin, MenuTabMixin):
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((1240, 820), pygame.RESIZABLE)
        pygame.display.set_caption("Futoshiki Solver GUI")
        self.clock = pygame.time.Clock()

        self.font_title = pygame.font.SysFont("segoeui", 34, bold=True)
        self.font_ui = pygame.font.SysFont("segoeui", 22)
        self.font_small = pygame.font.SysFont("segoeui", 18)
        self.font_cell = pygame.font.SysFont("segoeui", 34, bold=True)

        self.scene = "SOLVE"
        self.worker = SolverWorker()
        self.worker.start()

        self.input_files = sorted(glob.glob(os.path.join("Inputs", "input-*.txt")))
        self.input_index = 0

        self.puzzle: PuzzleSpec = self._load_initial_puzzle()
        self.display_board = self.puzzle.clone_board()
        self.play_board = self.puzzle.clone_board()
        self.menu_board = self.puzzle.clone_board()
        self.menu_constraints = list(self.puzzle.constraints)
        self.solution_cache: Optional[List[List[int]]] = None
        self.solution_cache_signature = None
        self.solution_cache_source = ""
        self.initial_board = self.puzzle.clone_board()
        self.initial_constraints = list(self.puzzle.constraints)
        self.initial_given_cells: Set[Tuple[int, int]] = self._compute_given_cells(self.initial_board)
        self.undo_stack: List[Tuple[int, int, int, int]] = []
        self.error_cells: Set[Tuple[int, int]] = set()
        self.pending_request_mode: Optional[str] = None
        self.solve_completed = False
        self.solve_no_solution = False
        self.play_completed = False
        self._restart_solve_on_idle = False
        self._prepare_play_cache_on_idle = False

        self.selected_algo_idx = 0
        self.algo_dropdown_open = False
        self.input_dropdown_open = False
        self.algo_dropdown_scroll = 0
        self.input_dropdown_scroll = 0
        self.selected_cell: Optional[Tuple[int, int]] = None
        self.show_status_panel = False

        self.trace_events = []
        self.trace_solver_key: Optional[Tuple[str, str]] = None
        self.trace_cursor = 0
        self.animation_playing = False
        self.animation_speed = 1.0
        self.speed_slider_dragging = False
        self._last_anim_tick = time.time()
        self.animation_focus_cell: Optional[Tuple[int, int]] = None
        self.animation_focus_action = ""

        self.worker_state = "idle"
        self.status_text = "Ready"
        self.latest_result: Optional[SolverResult] = None

    def _switch_scene(self, new_scene: str) -> None:
        if new_scene not in SCENES or new_scene == self.scene:
            return

        old_scene = self.scene
        if old_scene == "SOLVE" and new_scene != "SOLVE":
            self._on_leave_solve_tab()

        self.scene = new_scene
        if self.scene == "PLAY":
            self._on_play_tab_enter()

    def _on_leave_solve_tab(self) -> None:
        self.animation_playing = False
        self._restart_solve_on_idle = False
        self._prepare_play_cache_on_idle = False

        if self.worker_state in ("running", "paused", "step_ack"):
            self.worker.stop_current()

        self.pending_request_mode = None
        self.trace_events = []
        self.trace_solver_key = None
        self.trace_cursor = 0
        self.display_board = self.puzzle.clone_board()
        self.latest_result = None
        self.solve_completed = False
        self.solve_no_solution = False
        self.animation_focus_cell = None
        self.animation_focus_action = ""

        # Keep PLAY AUTO cache if available; clear only non-AUTO solve cache.
        if self.solution_cache_source != "auto_smt":
            self.solution_cache = None
            self.solution_cache_signature = None
            self.solution_cache_source = ""

    def _load_initial_puzzle(self) -> PuzzleSpec:
        if self.input_files:
            try:
                return load_puzzle_from_file(self.input_files[self.input_index])
            except Exception:
                pass
        return PuzzleSpec(
            size=5,
            board=[[0] * 5 for _ in range(5)],
            constraints=[],
        )

    @property
    def selected_solver(self) -> SolverType:
        return ALGO_OPTIONS[self.selected_algo_idx]["solver"]

    @property
    def selected_heuristic(self) -> str:
        heuristic = ALGO_OPTIONS[self.selected_algo_idx]["heuristic"]
        return heuristic if heuristic is not None else "n/a"

    @property
    def selected_algo_label(self) -> str:
        return ALGO_OPTIONS[self.selected_algo_idx]["label"]

    def _current_solver_key(self) -> Tuple[str, str]:
        heuristic = ALGO_OPTIONS[self.selected_algo_idx]["heuristic"]
        resolved_heuristic = heuristic if heuristic is not None else "weighted_domain"
        return (self.selected_solver.value, resolved_heuristic)

    def _build_selected_solver_config(self) -> SolverConfig:
        heuristic = ALGO_OPTIONS[self.selected_algo_idx]["heuristic"]
        return SolverConfig(
            solver_type=self.selected_solver,
            heuristic=heuristic if heuristic is not None else "weighted_domain",
            use_mrv=True,
            use_ac3=True,
            max_solutions=1,
        )

    @property
    def selected_input_label(self) -> str:
        if not self.input_files:
            return "(no input files)"
        return os.path.basename(self.input_files[self.input_index])

    def run(self) -> None:
        try:
            running = True
            while running:
                running = self._handle_events()
                self._poll_worker_events()
                self._update_animation()
                self._draw()
                pygame.display.flip()
                self.clock.tick(60)
        finally:
            self.worker.shutdown()
            pygame.quit()

    def _handle_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            if event.type == pygame.VIDEORESIZE:
                self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                continue

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                self._handle_keydown(event)

            if event.type == pygame.MOUSEBUTTONDOWN:
                self._handle_mouse(event)

            if event.type == pygame.MOUSEBUTTONUP:
                self.speed_slider_dragging = False

            if event.type == pygame.MOUSEMOTION and self.speed_slider_dragging:
                self._handle_speed_slider_drag(event.pos)

        return True

    def _handle_keydown(self, event: pygame.event.Event) -> None:
        if event.key == pygame.K_i:
            self.show_status_panel = not self.show_status_panel
            self.status_text = "Info panel {}.".format("shown" if self.show_status_panel else "hidden")
            return

        if event.key == pygame.K_TAB:
            idx = SCENES.index(self.scene)
            self._switch_scene(SCENES[(idx + 1) % len(SCENES)])
            return

        if self.scene == "SOLVE":
            return

        if self.selected_cell is None:
            return

        r, c = self.selected_cell
        if event.key in (pygame.K_BACKSPACE, pygame.K_DELETE, pygame.K_0, pygame.K_KP0):
            self._apply_cell_value(r, c, 0)
            return

        key_to_digit = {
            pygame.K_1: 1,
            pygame.K_2: 2,
            pygame.K_3: 3,
            pygame.K_4: 4,
            pygame.K_5: 5,
            pygame.K_6: 6,
            pygame.K_7: 7,
            pygame.K_8: 8,
            pygame.K_9: 9,
            pygame.K_KP1: 1,
            pygame.K_KP2: 2,
            pygame.K_KP3: 3,
            pygame.K_KP4: 4,
            pygame.K_KP5: 5,
            pygame.K_KP6: 6,
            pygame.K_KP7: 7,
            pygame.K_KP8: 8,
            pygame.K_KP9: 9,
        }
        digit = key_to_digit.get(event.key)
        if digit is not None and digit <= self.puzzle.size:
            self._apply_cell_value(r, c, digit)

    def _apply_cell_value(self, r: int, c: int, value: int) -> None:
        if self.scene == "SOLVE":
            self.status_text = "SOLVE is view-only. Use PLAY or MENU to edit cells."
            return

        # Select which board to edit based on scene
        if self.scene == "MENU":
            board = self.menu_board
        elif self.scene == "SOLVE":
            board = self.display_board
        else:  # PLAY
            board = self.play_board

        prev = board[r][c]
        if prev == value:
            return

        # PLAY: block changes to given cells
        if self.scene == "PLAY" and (r, c) in self.initial_given_cells:
            self.status_text = "Cannot modify given cell ({}, {}).".format(r + 1, c + 1)
            return

        self.undo_stack.append((r, c, prev, value))
        board[r][c] = value

        if self.scene == "SOLVE":
            self.animation_playing = False
            self.solve_completed = False
            self.solve_no_solution = False

        # Update error cells for PLAY validation
        if self.scene == "PLAY":
            self.error_cells = self._collect_invalid_cells(self.play_board)
            self._update_play_completed_state()

    def _handle_mouse(self, event: pygame.event.Event) -> None:
        pos = event.pos
        w, h = self.screen.get_size()
        layout = self._layout(w, h)

        if event.button in (4, 5):
            if self._handle_dropdown_wheel(event.button, pos, layout):
                return
            return

        for i, tab in enumerate(layout["tabs"]):
            if tab.hit(pos):
                self._switch_scene(SCENES[i])
                return

        # Dropdown should behave as an overlay: it receives click priority.
        if self.scene == "SOLVE" and self._handle_algo_dropdown_click(pos, layout):
            return

        if self.scene == "MENU" and self._handle_input_dropdown_click(pos, layout):
            return

        if self.scene == "MENU":
            for size_btn in layout["size_buttons"]:
                if size_btn.hit(pos):
                    try:
                        size = int(size_btn.label.split("x", 1)[0])
                        self._set_puzzle_size(size)
                    except ValueError:
                        self.status_text = "Invalid size label: {}".format(size_btn.label)
                    return

        if self.scene == "SOLVE" and "speed_slider" in layout:
            slider = layout["speed_slider"]
            if slider["track"].collidepoint(pos) or slider["thumb"].collidepoint(pos):
                self.speed_slider_dragging = True
                self._set_animation_speed_from_pos(pos[0], slider["track"])
                return

        for button in layout["buttons"]:
            if button.hit(pos):
                self._on_button_click(button.label)
                return

        if self.scene == "MENU":
            slot = self._constraint_slot_from_pos(pos, layout["board_rect"], self.puzzle.size)
            if slot is not None:
                self._cycle_constraint_slot(slot)
                return

        cell = self._cell_from_pos(pos, layout["board_rect"], self.puzzle.size)
        if cell is None:
            self.algo_dropdown_open = False
            self.input_dropdown_open = False
            return

        self.selected_cell = cell

    def _on_button_click(self, label: str) -> None:
        if label == "Play":
            self._on_solve_play()
        elif label == "Pause":
            self.animation_playing = False
        elif label == "Step":
            self.animation_playing = False
            if self.worker_state == "paused":
                self.worker.step()
            self._apply_next_trace_event()
        elif label == "Reset":
            if self.scene == "MENU":
                self._reset_menu_view()
            elif self.scene == "PLAY":
                self._reset_play_view()
            else:
                self._reset_solve_view()
        elif label == "Save":
            self._save_menu_state()
        elif label == "Show Answer":
            if self.scene == "PLAY":
                self._solution_action()
            else:
                self._show_answer_action()
        elif label == "Load Selected Input":
            self._load_selected_input()
        elif label == "Save To Inputs/temp-gui.txt":
            self._save_temp_input()
        elif label == "Undo Move":
            self._undo_move()
        elif label == "Hint":
            self._hint_action()
        elif label == "Check":
            self._check_action()
        elif label == "Toggle Info":
            self.show_status_panel = not self.show_status_panel
            self.status_text = "Info panel {}.".format("shown" if self.show_status_panel else "hidden")

    def _handle_algo_dropdown_click(self, pos: Tuple[int, int], layout: dict) -> bool:
        if self.scene != "SOLVE":
            return False

        main_rect = layout["algo_dropdown"]["main"]
        dropdown = layout["algo_dropdown"]

        if main_rect.collidepoint(pos):
            self.algo_dropdown_open = not self.algo_dropdown_open
            if self.algo_dropdown_open:
                self.input_dropdown_open = False
                self.algo_dropdown_scroll = 0
            return True

        if not self.algo_dropdown_open:
            return False

        if self._handle_dropdown_scrollbar_click(pos, dropdown, "algo"):
            return True

        idx = self._dropdown_item_index_from_pos(pos, dropdown, self.algo_dropdown_scroll)
        if idx is not None and idx < len(ALGO_OPTIONS):
            self.selected_algo_idx = idx
            self.algo_dropdown_open = False
            self.input_dropdown_open = False
            self.status_text = "Algorithm selected: {}".format(self.selected_algo_label)
            return True

        if dropdown["list_rect"].collidepoint(pos):
            return True

        self.algo_dropdown_open = False
        return False

    def _handle_input_dropdown_click(self, pos: Tuple[int, int], layout: dict) -> bool:
        if "input_dropdown" not in layout:
            return False

        main_rect = layout["input_dropdown"]["main"]
        dropdown = layout["input_dropdown"]

        if main_rect.collidepoint(pos):
            self.input_dropdown_open = not self.input_dropdown_open
            if self.input_dropdown_open:
                self.algo_dropdown_open = False
                self.input_dropdown_scroll = 0
            return True

        if not self.input_dropdown_open:
            return False

        if self._handle_dropdown_scrollbar_click(pos, dropdown, "input"):
            return True

        idx = self._dropdown_item_index_from_pos(pos, dropdown, self.input_dropdown_scroll)
        if idx is not None and idx < len(self.input_files):
            self.input_index = idx
            self.input_dropdown_open = False
            self.algo_dropdown_open = False
            self.status_text = "Input selected: {}".format(self.selected_input_label)
            return True

        if dropdown["list_rect"].collidepoint(pos):
            return True

        self.input_dropdown_open = False
        return False

    def _poll_worker_events(self) -> None:
        while True:
            item = self.worker.poll_event(timeout=0.0)
            if item is None:
                break

            if item["type"] == "worker_state":
                self.worker_state = item["state"]
                if self.worker_state == "paused":
                    self.animation_playing = False
                if self.worker_state == "idle" and self._restart_solve_on_idle:
                    self._restart_solve_on_idle = False
                    self._start_solving()
                if self.worker_state == "idle" and self._prepare_play_cache_on_idle:
                    self._prepare_play_cache_on_idle = False
                    self._prepare_play_answer_cache()
                continue

            if item["type"] == "trace":
                self.trace_events.append(item["event"])
                continue

            if item["type"] == "solver_result":
                result = item["result"]
                self.latest_result = result
                mode = self.pending_request_mode
                self.pending_request_mode = None
                if result.status == SolverStatus.SOLVED and result.solved_board is not None:
                    self.solution_cache = [row[:] for row in result.solved_board]
                    self.solution_cache_signature = self._current_puzzle_signature()
                    self.solution_cache_source = result.stats.get("algorithm", "")
                    if mode == "play_auto_cache":
                        self._prepare_play_cache_on_idle = False
                    self.solve_no_solution = False
                    if mode == "hint":
                        self._apply_hint_from_cache()
                    elif mode == "solution":
                        self._apply_solution_cache()
                    elif mode == "show_answer":
                        self._apply_solve_answer_from_cache()
                    elif mode == "play_auto_cache":
                        self.status_text = "PLAY answer cache ready (AUTO)."
                    elif mode == "load_solve":
                        self.status_text = "Loaded puzzle solved in background. Trace ready for SOLVE tab."
                    elif mode == "save_solve":
                        self.status_text = "Saved puzzle solved in background. Trace ready for SOLVE tab."
                    else:
                        self.status_text = "Solved."
                        self.solve_completed = True
                elif result.status == SolverStatus.UNSAT:
                    if mode == "play_auto_cache":
                        self.solution_cache = None
                        self.solution_cache_signature = None
                        self.solution_cache_source = ""
                        self._prepare_play_cache_on_idle = False
                    self.solve_completed = False
                    self.solve_no_solution = True
                    if mode == "hint":
                        self.status_text = "Hint unavailable: puzzle has no solution."
                    elif mode == "solution":
                        self.status_text = "Solution unavailable: puzzle has no solution."
                    elif mode == "play_auto_cache":
                        self.status_text = "PLAY answer unavailable: puzzle has no solution."
                    elif mode == "show_answer":
                        self.display_board = self.puzzle.clone_board()
                        self.trace_cursor = len(self.trace_events)
                        self.animation_playing = False
                        self.animation_focus_cell = None
                        self.animation_focus_action = ""
                        self.status_text = "Show Answer: puzzle has no solution."
                    elif mode == "load_solve":
                        self.status_text = "Loaded puzzle has no solution."
                    elif mode == "save_solve":
                        self.status_text = "Saved puzzle has no solution."
                    else:
                        self.status_text = "No solution found."
                elif result.status == SolverStatus.CANCELLED:
                    if mode == "play_auto_cache":
                        self.solution_cache = None
                        self.solution_cache_signature = None
                        self.solution_cache_source = ""
                        self._prepare_play_cache_on_idle = False
                    self.solve_completed = False
                    self.solve_no_solution = False
                    self.status_text = "Solve cancelled."
                else:
                    if mode == "play_auto_cache":
                        self.solution_cache = None
                        self.solution_cache_signature = None
                        self.solution_cache_source = ""
                        self._prepare_play_cache_on_idle = False
                    self.solve_completed = False
                    self.solve_no_solution = False
                    if mode == "hint":
                        self.status_text = "Hint failed: {}".format(result.message)
                    elif mode == "solution":
                        self.status_text = "Solution failed: {}".format(result.message)
                    elif mode == "play_auto_cache":
                        self.status_text = "PLAY answer prepare failed: {}".format(result.message)
                    else:
                        self.status_text = "Solver error: {}".format(result.message)

    def _clone_puzzle(self) -> PuzzleSpec:
        board = self.play_board if self.scene == "PLAY" else self.puzzle.board
        return PuzzleSpec(
            size=self.puzzle.size,
            board=[row[:] for row in board],
            constraints=list(self.puzzle.constraints),
        )

    def _current_puzzle_signature(self):
        board_key = tuple(tuple(int(v) for v in row) for row in self.puzzle.board)
        constraints_key = tuple(sorted(self.puzzle.constraints))
        return (self.puzzle.size, board_key, constraints_key)

    def _is_solution_cache_valid(self) -> bool:
        if self.solution_cache is None:
            return False
        if self.solution_cache_signature is None:
            return False
        if self.solution_cache_source != "auto_smt":
            return False
        return self.solution_cache_signature == self._current_puzzle_signature()

    def _is_play_cache_preparing(self) -> bool:
        return self._prepare_play_cache_on_idle or self.pending_request_mode == "play_auto_cache"

    def _build_play_auto_config(self) -> SolverConfig:
        return SolverConfig(
            solver_type=SolverType.AUTO,
            heuristic="n/a",
            use_mrv=False,
            use_ac3=False,
            max_solutions=1,
            metadata={"timeout_ms": 20000},
        )

    def _prepare_play_answer_cache(self) -> None:
        if self._is_solution_cache_valid():
            return

        if self.worker_state in ("running", "paused", "step_ack"):
            self._prepare_play_cache_on_idle = True
            self.status_text = "Preparing PLAY answer cache..."
            return

        self._prepare_play_cache_on_idle = False
        self.pending_request_mode = "play_auto_cache"
        self.status_text = "Preparing PLAY answer cache (AUTO)..."
        config = self._build_play_auto_config()
        self.worker.submit_solve(
            PuzzleSpec(
                size=self.puzzle.size,
                board=self.puzzle.clone_board(),
                constraints=list(self.puzzle.constraints),
            ),
            config,
        )

    def _layout(self, w: int, h: int):
        header_h = 72
        side_w = min(360, int(w * 0.32))
        board_rect = pygame.Rect(24, header_h + 16, w - side_w - 48, h - header_h - 40)
        panel_rect = pygame.Rect(board_rect.right + 16, header_h + 16, side_w - 24, h - header_h - 40)

        tab_w = 150
        tabs = [
            Button("PLAY", pygame.Rect(w - 3 * tab_w - 24, 14, tab_w - 10, 44)),
            Button("SOLVE", pygame.Rect(w - 2 * tab_w - 20, 14, tab_w - 10, 44)),
            Button("MENU", pygame.Rect(w - tab_w - 16, 14, tab_w - 10, 44)),
        ]

        btns = []
        dropdown_main = None
        dropdown_data = None

        def build_dropdown(main_rect: pygame.Rect, item_labels: List[str], row_h: int, row_gap: int, kind: str) -> dict:
            list_top = main_rect.bottom + 8
            content_h = len(item_labels) * row_h + max(0, len(item_labels) - 1) * row_gap
            panel_safe_bottom = panel_rect.bottom - 44
            max_h_by_panel = max(0, panel_safe_bottom - list_top)
            visible_h = min(content_h, min(DROPDOWN_MAX_HEIGHT, max_h_by_panel))
            list_rect = pygame.Rect(main_rect.left, list_top, main_rect.width, visible_h)
            return {
                "main": main_rect,
                "items": item_labels,
                "row_h": row_h,
                "row_gap": row_gap,
                "list_rect": list_rect,
                "content_h": content_h,
                "kind": kind,
            }

        input_top = panel_rect.top + 30
        if self.scene == "SOLVE":
            dropdown_main = pygame.Rect(panel_rect.left + 10, panel_rect.top + 30, panel_rect.width - 20, 36)
            dropdown_data = build_dropdown(
                dropdown_main,
                [opt["label"] for opt in ALGO_OPTIONS],
                row_h=32,
                row_gap=2,
                kind="algo",
            )
            input_top = dropdown_main.bottom + 32

        input_main = pygame.Rect(panel_rect.left + 10, input_top, panel_rect.width - 20, 36)
        input_data = build_dropdown(
            input_main,
            [os.path.basename(path) for path in self.input_files],
            row_h=28,
            row_gap=2,
            kind="input",
        )

        size_buttons = []
        size_y = input_main.bottom + 32
        size_w = (panel_rect.width - 20 - 4 * 6) // 5
        if self.scene == "MENU":
            for i, size in enumerate(SIZE_OPTIONS):
                bx = panel_rect.left + 10 + i * (size_w + 6)
                size_buttons.append(Button("{}x{}".format(size, size), pygame.Rect(bx, size_y, size_w, 30)))

        y = size_y + 54 if self.scene == "MENU" else (dropdown_main.bottom + 32 if dropdown_main is not None else panel_rect.top + 32)
        if self.scene == "SOLVE":
            button_labels = [
                "Play",
                "Pause",
                "Step",
                "Reset",
                "Show Answer",
                "Toggle Info",
            ]
        elif self.scene == "PLAY":
            button_labels = [
                "Undo Move",
                "Hint",
                "Show Answer",
                "Reset",
                "Toggle Info",
            ]
        else:
            button_labels = [
                "Load Selected Input",
                "Save",
                "Save To Inputs/temp-gui.txt",
                "Reset",
                "Toggle Info",
            ]

        for label in button_labels:
            btns.append(Button(label, pygame.Rect(panel_rect.left + 10, y, panel_rect.width - 20, 34)))
            y += 40

        speed_slider = None
        if self.scene == "SOLVE":
            track = pygame.Rect(panel_rect.left + 16, y + 34, panel_rect.width - 32, 8)
            value_ratio = (self.animation_speed - SPEED_MIN) / (SPEED_MAX - SPEED_MIN)
            value_ratio = max(0.0, min(1.0, value_ratio))
            thumb_x = int(track.left + value_ratio * track.width)
            thumb = pygame.Rect(thumb_x - 8, track.centery - 8, 16, 16)
            speed_slider = {"track": track, "thumb": thumb}

        return {
            "board_rect": board_rect,
            "panel_rect": panel_rect,
            "tabs": tabs,
            "buttons": btns,
            "algo_dropdown": dropdown_data,
            "input_dropdown": input_data,
            "size_buttons": size_buttons,
            "speed_slider": speed_slider,
            "header_h": header_h,
        }

    def _draw(self) -> None:
        w, h = self.screen.get_size()
        layout = self._layout(w, h)

        self.screen.fill((240, 243, 248))
        pygame.draw.rect(self.screen, (27, 52, 102), (0, 0, w, layout["header_h"]))

        title = self.font_title.render("FUTOSHIKI", True, (241, 245, 252))
        self.screen.blit(title, (24, 16))

        for i, tab in enumerate(layout["tabs"]):
            tab.draw(self.screen, self.font_ui, active=(self.scene == SCENES[i]))

        self._draw_board(layout["board_rect"])
        self._draw_panel(layout)

    def _draw_board(self, board_rect: pygame.Rect) -> None:
        pygame.draw.rect(self.screen, (250, 251, 253), board_rect)
        pygame.draw.rect(self.screen, (130, 138, 150), board_rect, 2)

        geom = self._board_geometry(board_rect, self.puzzle.size)
        
        # Select board based on scene
        if self.scene == "SOLVE":
            render_board = self.display_board
        elif self.scene == "MENU":
            render_board = self.menu_board
        else:  # PLAY
            render_board = self.play_board
        
        board_for_validation = render_board
        invalid_cells = self._collect_invalid_cells(board_for_validation)
        invalid_cells.update(self.error_cells)
        if self.scene == "MENU":
            given_cells = self._compute_given_cells(self.menu_board)
        else:
            given_cells = self._compute_given_cells(self.initial_board)
        solve_visual_complete = (
            self.scene == "SOLVE"
            and self.solve_completed
            and self.worker_state == "idle"
            and self.trace_cursor >= len(self.trace_events)
        )
        solve_visual_unsat = (
            self.scene == "SOLVE"
            and self.solve_no_solution
            and self.worker_state == "idle"
            and self.trace_cursor >= len(self.trace_events)
        )
        play_visual_complete = self.scene == "PLAY" and self.play_completed

        for r in range(self.puzzle.size):
            for c in range(self.puzzle.size):
                cell = self._cell_rect(geom, r, c)
                value = render_board[r][c]

                bg = (255, 255, 255)
                if self.scene == "SOLVE":
                    # Given cells stay gray in all SOLVE states.
                    if (r, c) in given_cells:
                        bg = (175, 185, 200)

                    if solve_visual_complete:
                        if (r, c) not in given_cells and value != 0:
                            bg = (200, 236, 210)
                    elif self.animation_focus_cell == (r, c):
                        bg = (206, 228, 255)
                elif self.scene == "PLAY":
                    # PLAY: invalid cells must be visible even if they are givens.
                    if (r, c) in invalid_cells:
                        bg = (255, 228, 228)
                    elif play_visual_complete:
                        if (r, c) in given_cells:
                            bg = (175, 185, 200)
                        elif value != 0:
                            bg = (200, 236, 210)
                    elif (r, c) in given_cells:
                        bg = (175, 185, 200)
                    elif self.selected_cell == (r, c):
                        bg = (222, 236, 255)
                    elif value != 0:
                        bg = (232, 236, 240)
                elif self.scene == "MENU":
                    # MENU: similar to PLAY but no validation (edit mode)
                    if (r, c) in given_cells:
                        bg = (175, 185, 200)
                    elif self.selected_cell == (r, c):
                        bg = (222, 236, 255)
                    elif value != 0:
                        bg = (232, 236, 240)
                else:
                    if self.selected_cell == (r, c):
                        bg = (222, 236, 255)
                    elif (r, c) in invalid_cells:
                        bg = (255, 228, 228)
                    elif value != 0:
                        bg = (232, 236, 240)

                pygame.draw.rect(self.screen, bg, cell)
                pygame.draw.rect(self.screen, (176, 184, 194), cell, 1)

                if value:
                    text = self.font_cell.render(str(value), True, (60, 67, 80))
                    self.screen.blit(text, text.get_rect(center=cell.center))

        self._draw_constraint_slots(geom)
        self._draw_constraints(geom)

        if solve_visual_complete:
            banner = pygame.Rect(board_rect.left + 16, board_rect.top + 16, 220, 40)
            pygame.draw.rect(self.screen, (59, 137, 84), banner, border_radius=8)
            pygame.draw.rect(self.screen, (44, 109, 66), banner, 1, border_radius=8)
            text = self.font_small.render("Solved", True, (242, 252, 245))
            self.screen.blit(text, text.get_rect(center=banner.center))
        elif solve_visual_unsat:
            banner = pygame.Rect(board_rect.left + 16, board_rect.top + 16, 260, 40)
            pygame.draw.rect(self.screen, (173, 66, 66), banner, border_radius=8)
            pygame.draw.rect(self.screen, (130, 48, 48), banner, 1, border_radius=8)
            text = self.font_small.render("No solution", True, (255, 245, 245))
            self.screen.blit(text, text.get_rect(center=banner.center))
        elif play_visual_complete:
            banner = pygame.Rect(board_rect.left + 16, board_rect.top + 16, 220, 40)
            pygame.draw.rect(self.screen, (59, 137, 84), banner, border_radius=8)
            pygame.draw.rect(self.screen, (44, 109, 66), banner, 1, border_radius=8)
            text = self.font_small.render("Solved", True, (242, 252, 245))
            self.screen.blit(text, text.get_rect(center=banner.center))

    def _given_cells(self) -> Set[Tuple[int, int]]:
        return self._compute_given_cells(self.initial_board)

    @staticmethod
    def _compute_given_cells(board: List[List[int]]) -> Set[Tuple[int, int]]:
        given: Set[Tuple[int, int]] = set()
        for r in range(len(board)):
            for c in range(len(board[r])):
                if board[r][c] != 0:
                    given.add((r, c))
        return given

    def _draw_constraint_slots(self, geom: dict) -> None:
        slot_bg = (238, 241, 246)
        slot_border = (196, 202, 212)
        n = self.puzzle.size

        if self.scene != "MENU":
            return

        for r in range(n):
            for c in range(n - 1):
                rect = self._h_slot_rect(geom, r, c)
                pygame.draw.rect(self.screen, slot_bg, rect, border_radius=4)
                pygame.draw.rect(self.screen, slot_border, rect, 1, border_radius=4)

        for r in range(n - 1):
            for c in range(n):
                rect = self._v_slot_rect(geom, r, c)
                pygame.draw.rect(self.screen, slot_bg, rect, border_radius=4)
                pygame.draw.rect(self.screen, slot_border, rect, 1, border_radius=4)

    def _draw_constraints(self, geom: dict) -> None:
        constraints = self.menu_constraints if self.scene == "MENU" else self.puzzle.constraints
        for (r1, c1), (r2, c2) in constraints:
            if r1 == r2 and abs(c1 - c2) == 1:
                left = min(c1, c2)
                rect = self._h_slot_rect(geom, r1, left)
                symbol = "<" if c1 < c2 else ">"
                text = self.font_ui.render(symbol, True, (82, 90, 101))
                self.screen.blit(text, text.get_rect(center=rect.center))
            elif c1 == c2 and abs(r1 - r2) == 1:
                top = min(r1, r2)
                rect = self._v_slot_rect(geom, top, c1)
                symbol = "^" if r1 < r2 else "v"
                text = self.font_ui.render(symbol, True, (82, 90, 101))
                self.screen.blit(text, text.get_rect(center=rect.center))

    def _draw_panel(self, layout: dict) -> None:
        panel_rect = layout["panel_rect"]
        buttons = layout["buttons"]

        pygame.draw.rect(self.screen, (233, 236, 240), panel_rect)
        pygame.draw.rect(self.screen, (173, 179, 188), panel_rect, 1)

        # title = self.font_ui.render("Control Panel", True, (42, 52, 66))
        title = self.font_ui.render("", True, (42, 52, 66))
        self.screen.blit(title, (panel_rect.left + 10, panel_rect.top - 28))

        # Draw main dropdown field first.
        if self.scene == "SOLVE":
            self._draw_algo_dropdown(layout, overlay_only=False)
        if self.scene == "MENU":
            self._draw_input_dropdown(layout, overlay_only=False)

        if self.scene == "MENU":
            size_title = self.font_small.render("Board Size", True, (57, 66, 80))
            if layout["size_buttons"]:
                self.screen.blit(size_title, (layout["size_buttons"][0].rect.left, layout["size_buttons"][0].rect.top - 24))
            for size_btn in layout["size_buttons"]:
                size_btn.draw(
                    self.screen,
                    self.font_small,
                    active=(size_btn.label == "{}x{}".format(self.puzzle.size, self.puzzle.size)),
                )

        for button in buttons:
            button.draw(self.screen, self.font_small, active=False)

        if self.scene == "SOLVE" and layout.get("speed_slider") is not None:
            slider = layout["speed_slider"]
            label = self.font_small.render("Speed {:.2f}x".format(self.animation_speed), True, (52, 60, 74))
            self.screen.blit(label, (slider["track"].left, slider["track"].top - 30))
            pygame.draw.rect(self.screen, (190, 197, 208), slider["track"], border_radius=4)
            pygame.draw.rect(self.screen, (84, 122, 188), slider["thumb"], border_radius=8)
            pygame.draw.rect(self.screen, (62, 98, 156), slider["thumb"], 1, border_radius=8)

        y = panel_rect.bottom - 240
        if self.show_status_panel:
            status_lines = self._wrap_text(
                "Status: {}".format(self.status_text),
                panel_rect.width - 24,
                self.font_small,
            )
            if self.scene == "PLAY":
                algorithm_line = "AUTO (PLAY)"
                solver_line = "auto_smt"
                heuristic_line = "n/a"
            else:
                algorithm_line = self.selected_algo_label
                solver_line = self.selected_solver.value
                heuristic_line = self.selected_heuristic

            lines = [
                "Scene: {}".format(self.scene),
                "Worker: {}".format(self.worker_state),
                "Algorithm: {}".format(algorithm_line),
                "Solver: {}".format(solver_line),
                "Heuristic: {}".format(heuristic_line),
                "Animation: {:.2f}x".format(self.animation_speed),
                "Trace: {}/{}".format(self.trace_cursor, len(self.trace_events)),
            ]
            if self.latest_result is not None:
                lines.append("Result: {}".format(self.latest_result.status.value))
            lines.extend(status_lines)
            for line in lines:
                text = self.font_small.render(line, True, (52, 60, 74))
                self.screen.blit(text, (panel_rect.left + 12, y))
                y += 22
        else:
            text = self.font_small.render("", True, (52, 60, 74))
            self.screen.blit(text, (panel_rect.left + 12, y))

        # Draw dropdown overlays last so they are not covered by status/tips.
        if self.scene == "SOLVE":
            self._draw_algo_dropdown(layout, overlay_only=True)
        if self.scene == "MENU":
            self._draw_input_dropdown(layout, overlay_only=True)

    def _collect_invalid_cells(self, board: List[List[int]]) -> set:
        return self._cells_from_issues(self._analyze_board_issues(board))

    @staticmethod
    def _wrap_text(text: str, max_width: int, font: pygame.font.Font) -> List[str]:
        words = text.split()
        if not words:
            return [""]

        lines: List[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = current + " " + word
            if font.size(candidate)[0] <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def _analyze_board_issues(self, board: List[List[int]]) -> List[Dict]:
        issues: List[Dict] = []
        n = self.puzzle.size

        for r in range(n):
            value_to_cols: Dict[int, List[int]] = defaultdict(list)
            for c in range(n):
                v = board[r][c]
                if v != 0:
                    value_to_cols[v].append(c)
            for value, cols in value_to_cols.items():
                if len(cols) > 1:
                    cells = {(r, c) for c in cols}
                    issues.append({
                        "message": "row {} has duplicate value {}".format(r + 1, value),
                        "cells": cells,
                    })

        for c in range(n):
            value_to_rows: Dict[int, List[int]] = defaultdict(list)
            for r in range(n):
                v = board[r][c]
                if v != 0:
                    value_to_rows[v].append(r)
            for value, rows in value_to_rows.items():
                if len(rows) > 1:
                    cells = {(r, c) for r in rows}
                    issues.append({
                        "message": "column {} has duplicate value {}".format(c + 1, value),
                        "cells": cells,
                    })

        for (r1, c1), (r2, c2) in self.puzzle.constraints:
            v1 = board[r1][c1]
            v2 = board[r2][c2]
            if v1 != 0 and v2 != 0 and v1 >= v2:
                issues.append({
                    "message": "inequality violated at ({},{})<({},{})".format(
                        r1 + 1, c1 + 1, r2 + 1, c2 + 1
                    ),
                    "cells": {(r1, c1), (r2, c2)},
                })

        return issues

    @staticmethod
    def _cells_from_issues(issues: List[Dict]) -> Set[Tuple[int, int]]:
        cells: Set[Tuple[int, int]] = set()
        for issue in issues:
            cells.update(issue.get("cells", set()))
        return cells

    def _draw_algo_dropdown(self, layout: dict, overlay_only: bool) -> None:
        if self.scene != "SOLVE":
            return

        dropdown = layout.get("algo_dropdown")
        if dropdown is None:
            return
        main = dropdown["main"]

        if not overlay_only:
            pygame.draw.rect(self.screen, (248, 250, 253), main, border_radius=6)
            pygame.draw.rect(self.screen, (138, 146, 158), main, 1, border_radius=6)

            header = self.font_small.render("Algorithm", True, (57, 66, 80))
            self.screen.blit(header, (main.left, main.top - 24))

            value = self.font_small.render(self.selected_algo_label, True, (42, 52, 66))
            self.screen.blit(value, (main.left + 8, main.top + 8))

            triangle = "▲" if self.algo_dropdown_open else "▼"
            arrow = self.font_small.render(triangle, True, (57, 66, 80))
            self.screen.blit(arrow, (main.right - 18, main.top + 8))
            return

        if not self.algo_dropdown_open:
            return

        self.algo_dropdown_scroll = self._clamp_dropdown_scroll(self.algo_dropdown_scroll, dropdown)
        self._draw_dropdown_overlay(dropdown, self.algo_dropdown_scroll, self.selected_algo_idx)

    def _draw_input_dropdown(self, layout: dict, overlay_only: bool) -> None:
        dropdown = layout.get("input_dropdown")
        if dropdown is None:
            return
        main = dropdown["main"]

        if not overlay_only:
            pygame.draw.rect(self.screen, (248, 250, 253), main, border_radius=6)
            pygame.draw.rect(self.screen, (138, 146, 158), main, 1, border_radius=6)

            header = self.font_small.render("Input File", True, (57, 66, 80))
            self.screen.blit(header, (main.left, main.top - 24))

            value = self.font_small.render(self.selected_input_label, True, (42, 52, 66))
            self.screen.blit(value, (main.left + 8, main.top + 8))

            triangle = "▲" if self.input_dropdown_open else "▼"
            arrow = self.font_small.render(triangle, True, (57, 66, 80))
            self.screen.blit(arrow, (main.right - 18, main.top + 8))
            return

        if not self.input_dropdown_open:
            return

        if not dropdown["items"]:
            return

        self.input_dropdown_scroll = self._clamp_dropdown_scroll(self.input_dropdown_scroll, dropdown)
        self._draw_dropdown_overlay(dropdown, self.input_dropdown_scroll, self.input_index)

    @staticmethod
    def _dropdown_inner_rect(dropdown: dict) -> pygame.Rect:
        inner = dropdown["list_rect"].inflate(-2 * DROPDOWN_LIST_PADDING, -2 * DROPDOWN_LIST_PADDING)
        if inner.width < 1:
            inner.width = 1
        if inner.height < 1:
            inner.height = 1
        return inner

    def _dropdown_max_scroll(self, dropdown: dict) -> int:
        inner_h = self._dropdown_inner_rect(dropdown).height
        return max(0, dropdown["content_h"] - inner_h)

    def _clamp_dropdown_scroll(self, value: int, dropdown: dict) -> int:
        return max(0, min(self._dropdown_max_scroll(dropdown), int(value)))

    def _dropdown_needs_scrollbar(self, dropdown: dict) -> bool:
        return self._dropdown_max_scroll(dropdown) > 0

    def _dropdown_scrollbar_rects(self, dropdown: dict) -> Tuple[pygame.Rect, pygame.Rect]:
        list_rect = dropdown["list_rect"]
        track = pygame.Rect(list_rect.right - 12, list_rect.top + 6, 8, max(1, list_rect.height - 12))

        max_scroll = self._dropdown_max_scroll(dropdown)
        if max_scroll <= 0:
            thumb = pygame.Rect(track.left, track.top, track.width, track.height)
            return track, thumb

        inner_h = self._dropdown_inner_rect(dropdown).height
        thumb_h = max(22, int(track.height * (inner_h / float(max(1, dropdown["content_h"])))))
        thumb_h = min(track.height, thumb_h)

        if track.height == thumb_h:
            thumb_top = track.top
        else:
            ratio = float(self.algo_dropdown_scroll if dropdown.get("kind") == "algo" else self.input_dropdown_scroll) / float(max_scroll)
            thumb_top = track.top + int(ratio * (track.height - thumb_h))

        thumb = pygame.Rect(track.left, thumb_top, track.width, thumb_h)
        return track, thumb

    def _draw_dropdown_overlay(self, dropdown: dict, scroll_value: int, selected_idx: int) -> None:
        list_rect = dropdown["list_rect"]
        if list_rect.height <= 0:
            return

        items = dropdown["items"]
        row_h = dropdown["row_h"]
        row_gap = dropdown["row_gap"]

        pygame.draw.rect(self.screen, (246, 249, 253), list_rect, border_radius=6)
        pygame.draw.rect(self.screen, (138, 146, 158), list_rect, 1, border_radius=6)

        needs_scrollbar = self._dropdown_needs_scrollbar(dropdown)
        inner = self._dropdown_inner_rect(dropdown)
        if needs_scrollbar:
            inner.width = max(1, inner.width - 12)

        prev_clip = self.screen.get_clip()
        self.screen.set_clip(inner)

        step = row_h + row_gap
        for i, label_text in enumerate(items):
            item_top = inner.top - scroll_value + i * step
            row_rect = pygame.Rect(inner.left, item_top, inner.width, row_h)
            if row_rect.bottom < inner.top or row_rect.top > inner.bottom:
                continue

            is_selected = i == selected_idx
            bg = (214, 228, 252) if is_selected else (248, 250, 253)
            fg = (34, 43, 59)
            pygame.draw.rect(self.screen, bg, row_rect, border_radius=4)
            pygame.draw.rect(self.screen, (138, 146, 158), row_rect, 1, border_radius=4)
            label = self.font_small.render(label_text, True, fg)
            self.screen.blit(label, (row_rect.left + 8, row_rect.top + 5))

        self.screen.set_clip(prev_clip)

        if needs_scrollbar:
            track, thumb = self._dropdown_scrollbar_rects(dropdown)
            pygame.draw.rect(self.screen, (224, 229, 236), track, border_radius=5)
            pygame.draw.rect(self.screen, (183, 191, 203), track, 1, border_radius=5)
            pygame.draw.rect(self.screen, (137, 149, 168), thumb, border_radius=5)

    def _dropdown_item_index_from_pos(self, pos: Tuple[int, int], dropdown: dict, scroll_value: int) -> Optional[int]:
        list_rect = dropdown["list_rect"]
        if list_rect.height <= 0:
            return None

        inner = self._dropdown_inner_rect(dropdown)
        if self._dropdown_needs_scrollbar(dropdown):
            inner.width = max(1, inner.width - 12)

        if not inner.collidepoint(pos):
            return None

        row_h = dropdown["row_h"]
        row_gap = dropdown["row_gap"]
        step = row_h + row_gap
        rel = pos[1] - inner.top + scroll_value
        if rel < 0:
            return None

        idx = int(rel // step)
        if idx < 0 or idx >= len(dropdown["items"]):
            return None

        if (rel % step) >= row_h:
            return None

        return idx

    def _handle_dropdown_scrollbar_click(self, pos: Tuple[int, int], dropdown: dict, kind: str) -> bool:
        if not self._dropdown_needs_scrollbar(dropdown):
            return False

        track, _thumb = self._dropdown_scrollbar_rects(dropdown)
        if not track.collidepoint(pos):
            return False

        max_scroll = self._dropdown_max_scroll(dropdown)
        if max_scroll <= 0:
            return True

        ratio = (pos[1] - track.top) / float(max(1, track.height))
        ratio = max(0.0, min(1.0, ratio))
        new_scroll = int(ratio * max_scroll)

        if kind == "algo":
            self.algo_dropdown_scroll = self._clamp_dropdown_scroll(new_scroll, dropdown)
        else:
            self.input_dropdown_scroll = self._clamp_dropdown_scroll(new_scroll, dropdown)
        return True

    def _handle_dropdown_wheel(self, button: int, pos: Tuple[int, int], layout: dict) -> bool:
        delta = -DROPDOWN_SCROLL_STEP if button == 4 else DROPDOWN_SCROLL_STEP

        if self.algo_dropdown_open and self.scene == "SOLVE":
            dropdown = layout.get("algo_dropdown")
            if dropdown is not None and dropdown["list_rect"].collidepoint(pos):
                self.algo_dropdown_scroll = self._clamp_dropdown_scroll(self.algo_dropdown_scroll + delta, dropdown)
                return True

        if self.input_dropdown_open and self.scene == "MENU":
            dropdown = layout.get("input_dropdown")
            if dropdown is not None and dropdown["list_rect"].collidepoint(pos):
                self.input_dropdown_scroll = self._clamp_dropdown_scroll(self.input_dropdown_scroll + delta, dropdown)
                return True

        return False

    @staticmethod
    def _board_geometry(board_rect: pygame.Rect, n: int) -> dict:
        gap_ratio = 0.42
        unit = n + (n - 1) * gap_ratio
        avail_w = board_rect.width - 30
        avail_h = board_rect.height - 30
        cell_size = max(24, int(min(avail_w / unit, avail_h / unit)))
        gap = max(8, int(cell_size * gap_ratio))

        grid_w = n * cell_size + (n - 1) * gap
        grid_h = n * cell_size + (n - 1) * gap
        start_x = board_rect.left + (board_rect.width - grid_w) // 2
        start_y = board_rect.top + (board_rect.height - grid_h) // 2

        return {
            "start_x": start_x,
            "start_y": start_y,
            "cell": cell_size,
            "gap": gap,
            "n": n,
        }

    @staticmethod
    def _cell_rect(geom: dict, r: int, c: int) -> pygame.Rect:
        step = geom["cell"] + geom["gap"]
        x = geom["start_x"] + c * step
        y = geom["start_y"] + r * step
        return pygame.Rect(x, y, geom["cell"], geom["cell"])

    @staticmethod
    def _h_slot_rect(geom: dict, r: int, c: int) -> pygame.Rect:
        step = geom["cell"] + geom["gap"]
        x = geom["start_x"] + c * step + geom["cell"]
        y = geom["start_y"] + r * step
        return pygame.Rect(x, y, geom["gap"], geom["cell"])

    @staticmethod
    def _v_slot_rect(geom: dict, r: int, c: int) -> pygame.Rect:
        step = geom["cell"] + geom["gap"]
        x = geom["start_x"] + c * step
        y = geom["start_y"] + r * step + geom["cell"]
        return pygame.Rect(x, y, geom["cell"], geom["gap"])

    def _cell_from_pos(self, pos: Tuple[int, int], board_rect: pygame.Rect, n: int) -> Optional[Tuple[int, int]]:
        geom = self._board_geometry(board_rect, n)
        for r in range(n):
            for c in range(n):
                if self._cell_rect(geom, r, c).collidepoint(pos):
                    return (r, c)
        return None

def main() -> None:
    app = FutoshikiGUI()
    app.run()


if __name__ == "__main__":
    main()
