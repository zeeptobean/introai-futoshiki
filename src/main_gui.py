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
        self.menu_board = self.puzzle.clone_board()
        self.menu_constraints = list(self.puzzle.constraints)
        self.solution_cache: Optional[List[List[int]]] = None
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

        self.selected_algo_idx = 0
        self.algo_dropdown_open = False
        self.input_dropdown_open = False
        self.selected_cell: Optional[Tuple[int, int]] = None

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
        if event.key == pygame.K_TAB:
            idx = SCENES.index(self.scene)
            self.scene = SCENES[(idx + 1) % len(SCENES)]
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
            board = self.puzzle.board

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
            self.error_cells = self._collect_invalid_cells(self.puzzle.board)
            self._update_play_completed_state()

    def _handle_mouse(self, event: pygame.event.Event) -> None:
        pos = event.pos
        w, h = self.screen.get_size()
        layout = self._layout(w, h)

        for i, tab in enumerate(layout["tabs"]):
            if tab.hit(pos):
                self.scene = SCENES[i]
                if self.scene != "SOLVE":
                    self.animation_playing = False
                if self.scene == "PLAY":
                    self._on_play_tab_enter()
                return

        # Dropdown should behave as an overlay: it receives click priority.
        if self.scene != "MENU" and self._handle_algo_dropdown_click(pos, layout):
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
            if self.worker_state == "running":
                self.worker.pause()
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
        elif label == "Solution":
            self._solution_action()

    def _handle_algo_dropdown_click(self, pos: Tuple[int, int], layout: dict) -> bool:
        if self.scene == "MENU":
            return False

        main_rect = layout["algo_dropdown"]["main"]
        option_rects = layout["algo_dropdown"]["options"]

        if main_rect.collidepoint(pos):
            self.algo_dropdown_open = not self.algo_dropdown_open
            if self.algo_dropdown_open:
                self.input_dropdown_open = False
            return True

        if not self.algo_dropdown_open:
            return False

        for i, rect in enumerate(option_rects):
            if rect.collidepoint(pos):
                self.selected_algo_idx = i
                self.algo_dropdown_open = False
                self.input_dropdown_open = False
                self.status_text = "Algorithm selected: {}".format(self.selected_algo_label)
                return True

        self.algo_dropdown_open = False
        return False

    def _handle_input_dropdown_click(self, pos: Tuple[int, int], layout: dict) -> bool:
        if "input_dropdown" not in layout:
            return False

        main_rect = layout["input_dropdown"]["main"]
        option_rects = layout["input_dropdown"]["options"]

        if main_rect.collidepoint(pos):
            self.input_dropdown_open = not self.input_dropdown_open
            if self.input_dropdown_open:
                self.algo_dropdown_open = False
            return True

        if not self.input_dropdown_open:
            return False

        for i, rect in enumerate(option_rects):
            if rect.collidepoint(pos):
                self.input_index = i
                self.input_dropdown_open = False
                self.algo_dropdown_open = False
                self.status_text = "Input selected: {}".format(self.selected_input_label)
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
                    self.solve_no_solution = False
                    if mode == "hint":
                        self._apply_hint_from_cache()
                    elif mode == "solution":
                        self._apply_solution_cache()
                    elif mode == "show_answer":
                        self._apply_solve_answer_from_cache()
                    elif mode == "load_solve":
                        self.status_text = "Loaded puzzle solved in background. Trace ready for SOLVE tab."
                    elif mode == "save_solve":
                        self.status_text = "Saved puzzle solved in background. Trace ready for SOLVE tab."
                    else:
                        self.status_text = "Solved."
                        self.solve_completed = True
                elif result.status == SolverStatus.UNSAT:
                    self.solve_completed = False
                    self.solve_no_solution = True
                    if mode == "hint":
                        self.status_text = "Hint unavailable: puzzle has no solution."
                    elif mode == "solution":
                        self.status_text = "Solution unavailable: puzzle has no solution."
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
                    self.solve_completed = False
                    self.solve_no_solution = False
                    self.status_text = "Solve cancelled."
                else:
                    self.solve_completed = False
                    self.solve_no_solution = False
                    if mode == "hint":
                        self.status_text = "Hint failed: {}".format(result.message)
                    elif mode == "solution":
                        self.status_text = "Solution failed: {}".format(result.message)
                    else:
                        self.status_text = "Solver error: {}".format(result.message)

    def _clone_puzzle(self) -> PuzzleSpec:
        return PuzzleSpec(
            size=self.puzzle.size,
            board=self.puzzle.clone_board(),
            constraints=list(self.puzzle.constraints),
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
        dropdown_options = []

        input_top = panel_rect.top + 20
        if self.scene != "MENU":
            dropdown_main = pygame.Rect(panel_rect.left + 10, panel_rect.top + 20, panel_rect.width - 20, 36)
            for i in range(len(ALGO_OPTIONS)):
                dropdown_options.append(
                    pygame.Rect(dropdown_main.left, dropdown_main.bottom + i * 34, dropdown_main.width, 32)
                )
            input_top = dropdown_main.bottom + 22

        input_main = pygame.Rect(panel_rect.left + 10, input_top, panel_rect.width - 20, 36)
        input_options = []
        for i in range(len(self.input_files)):
            input_options.append(
                pygame.Rect(input_main.left, input_main.bottom + i * 30, input_main.width, 28)
            )

        size_buttons = []
        size_y = input_main.bottom + 20
        size_w = (panel_rect.width - 20 - 4 * 6) // 5
        if self.scene == "MENU":
            for i, size in enumerate(SIZE_OPTIONS):
                bx = panel_rect.left + 10 + i * (size_w + 6)
                size_buttons.append(Button("{}x{}".format(size, size), pygame.Rect(bx, size_y, size_w, 30)))

        y = size_y + 46 if self.scene == "MENU" else dropdown_main.bottom + 24
        if self.scene == "SOLVE":
            button_labels = [
                "Play",
                "Pause",
                "Step",
                "Reset",
                "Show Answer",
            ]
        elif self.scene == "PLAY":
            button_labels = [
                "Undo Move",
                "Hint",
                "Check",
                "Solution",
                "Reset",
            ]
        else:
            button_labels = [
                "Load Selected Input",
                "Save",
                "Save To Inputs/temp-gui.txt",
                "Reset",
            ]

        for label in button_labels:
            btns.append(Button(label, pygame.Rect(panel_rect.left + 10, y, panel_rect.width - 20, 34)))
            y += 40

        speed_slider = None
        if self.scene == "SOLVE":
            track = pygame.Rect(panel_rect.left + 16, y + 8, panel_rect.width - 32, 8)
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
            "algo_dropdown": {
                "main": dropdown_main,
                "options": dropdown_options,
            },
            "input_dropdown": {
                "main": input_main,
                "options": input_options,
            },
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
            render_board = self.puzzle.board
        
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

        title = self.font_ui.render("Control Panel", True, (42, 52, 66))
        self.screen.blit(title, (panel_rect.left + 10, panel_rect.top - 28))

        # Draw main dropdown field first.
        if self.scene != "MENU":
            self._draw_algo_dropdown(layout, overlay_only=False)
        if self.scene == "MENU":
            self._draw_input_dropdown(layout, overlay_only=False)

        if self.scene == "MENU":
            size_title = self.font_small.render("Board Size", True, (57, 66, 80))
            if layout["size_buttons"]:
                self.screen.blit(size_title, (layout["size_buttons"][0].rect.left, layout["size_buttons"][0].rect.top - 18))
            for size_btn in layout["size_buttons"]:
                size_btn.draw(
                    self.screen,
                    self.font_small,
                    active=(size_btn.label == "{}x{}".format(self.puzzle.size, self.puzzle.size)),
                )

        for button in buttons:
            button.draw(self.screen, self.font_small, active=False)

        # Draw dropdown options last to ensure they overlay controls below.
        if self.scene != "MENU":
            self._draw_algo_dropdown(layout, overlay_only=True)
        if self.scene == "MENU":
            self._draw_input_dropdown(layout, overlay_only=True)

        if self.scene == "SOLVE" and layout.get("speed_slider") is not None:
            slider = layout["speed_slider"]
            label = self.font_small.render("Speed {:.2f}x".format(self.animation_speed), True, (52, 60, 74))
            self.screen.blit(label, (slider["track"].left, slider["track"].top - 24))
            pygame.draw.rect(self.screen, (190, 197, 208), slider["track"], border_radius=4)
            pygame.draw.rect(self.screen, (84, 122, 188), slider["thumb"], border_radius=8)
            pygame.draw.rect(self.screen, (62, 98, 156), slider["thumb"], 1, border_radius=8)

        y = panel_rect.bottom - 172
        status_lines = self._wrap_text(
            "Status: {}".format(self.status_text),
            panel_rect.width - 24,
            self.font_small,
        )
        lines = [
            "Scene: {}".format(self.scene),
            "Worker: {}".format(self.worker_state),
            "Algorithm: {}".format(self.selected_algo_label),
            "Solver: {}".format(self.selected_solver.value),
            "Heuristic: {}".format(self.selected_heuristic),
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

        if self.scene == "MENU":
            tip = "Menu tip: click size buttons, then click gap slots between cells to edit constraints."
        elif self.scene == "PLAY":
            tip = "Play tip: use Hint for one cell, Check for violations, Solution to fill the full board."
        else:
            tip = "Solve tip: Play starts solver, Pause/Step control trace, Reset clears current solve view."
        tip_text = self.font_small.render(tip, True, (78, 86, 98))
        self.screen.blit(tip_text, (panel_rect.left + 12, panel_rect.bottom - 24))

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
        if self.scene == "MENU":
            return

        main = layout["algo_dropdown"]["main"]
        options = layout["algo_dropdown"]["options"]

        if not overlay_only:
            pygame.draw.rect(self.screen, (248, 250, 253), main, border_radius=6)
            pygame.draw.rect(self.screen, (138, 146, 158), main, 1, border_radius=6)

            header = self.font_small.render("Algorithm", True, (57, 66, 80))
            self.screen.blit(header, (main.left, main.top - 18))

            value = self.font_small.render(self.selected_algo_label, True, (42, 52, 66))
            self.screen.blit(value, (main.left + 8, main.top + 8))

            triangle = "▲" if self.algo_dropdown_open else "▼"
            arrow = self.font_small.render(triangle, True, (57, 66, 80))
            self.screen.blit(arrow, (main.right - 18, main.top + 8))
            return

        if not self.algo_dropdown_open:
            return

        for i, rect in enumerate(options):
            is_selected = i == self.selected_algo_idx
            bg = (214, 228, 252) if is_selected else (248, 250, 253)
            fg = (34, 43, 59)
            pygame.draw.rect(self.screen, bg, rect, border_radius=4)
            pygame.draw.rect(self.screen, (138, 146, 158), rect, 1, border_radius=4)
            label = self.font_small.render(ALGO_OPTIONS[i]["label"], True, fg)
            self.screen.blit(label, (rect.left + 8, rect.top + 6))

    def _draw_input_dropdown(self, layout: dict, overlay_only: bool) -> None:
        main = layout["input_dropdown"]["main"]
        options = layout["input_dropdown"]["options"]

        if not overlay_only:
            pygame.draw.rect(self.screen, (248, 250, 253), main, border_radius=6)
            pygame.draw.rect(self.screen, (138, 146, 158), main, 1, border_radius=6)

            header = self.font_small.render("Input File", True, (57, 66, 80))
            self.screen.blit(header, (main.left, main.top - 18))

            value = self.font_small.render(self.selected_input_label, True, (42, 52, 66))
            self.screen.blit(value, (main.left + 8, main.top + 8))

            triangle = "▲" if self.input_dropdown_open else "▼"
            arrow = self.font_small.render(triangle, True, (57, 66, 80))
            self.screen.blit(arrow, (main.right - 18, main.top + 8))
            return

        if not self.input_dropdown_open:
            return

        if not options:
            return

        for i, rect in enumerate(options):
            is_selected = i == self.input_index
            bg = (214, 228, 252) if is_selected else (248, 250, 253)
            fg = (34, 43, 59)
            pygame.draw.rect(self.screen, bg, rect, border_radius=4)
            pygame.draw.rect(self.screen, (138, 146, 158), rect, 1, border_radius=4)
            label = self.font_small.render(os.path.basename(self.input_files[i]), True, fg)
            self.screen.blit(label, (rect.left + 8, rect.top + 5))

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
