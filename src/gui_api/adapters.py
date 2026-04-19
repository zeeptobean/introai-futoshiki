"""Solver adapters to standardize results for the GUI layer."""

import os
import tempfile
import time
from abc import ABC, abstractmethod
from typing import Callable, Dict, Optional

from .contracts import PuzzleSpec, SolverConfig, SolverResult, SolverStatus, SolverType
from .trace import TraceAction, TraceEvent, TraceSink, clone_board


def _import_csp_symbols():
    """Import CSP modules (Futoshiki, A*, Backtracking) with run-root fallback."""
    try:
        from futoshiki import Futoshiki
        from astar_solver import AStarSolver
        from backtrack_solver import BacktrackSolver
    except ImportError:  # pragma: no cover
        from src.futoshiki import Futoshiki
        from src.astar_solver import AStarSolver
        from src.backtrack_solver import BacktrackSolver

    return {
        "Futoshiki": Futoshiki,
        "AStarSolver": AStarSolver,
        "BacktrackSolver": BacktrackSolver,
    }


def _import_fc_symbols():
    """Import Forward Chaining modules with run-root fallback."""
    try:
        from fc31 import load_futoshiki, fol_fc
        from utils import write_input_file
    except ImportError:  # pragma: no cover
        from src.fc31 import load_futoshiki, fol_fc
        from src.utils import write_input_file

    return {
        "load_futoshiki": load_futoshiki,
        "fol_fc": fol_fc,
        "write_input_file": write_input_file,
    }


def _import_bc_symbols():
    """Import Backward Chaining modules with run-root fallback."""
    try:
        from bc3 import load_and_solve_futoshiki, fol_bc_and, subst
        from utils import write_input_file
    except ImportError:  # pragma: no cover
        from src.bc3 import load_and_solve_futoshiki, fol_bc_and, subst
        from src.utils import write_input_file

    return {
        "load_and_solve_futoshiki": load_and_solve_futoshiki,
        "fol_bc_and": fol_bc_and,
        "subst": subst,
        "write_input_file": write_input_file,
    }

def _import_fc_backtrack_symbols():
    """Import FC+Backtrack modules with run-root fallback."""
    try:
        from fcbacktrack import load_futoshiki, solve_with_backtracking
        from utils import write_input_file
    except ImportError:  # pragma: no cover
        from src.fcbacktrack import load_futoshiki, solve_with_backtracking
        from src.utils import write_input_file

    return {
        "load_futoshiki": load_futoshiki,
        "solve_with_backtracking": solve_with_backtracking,
        "write_input_file": write_input_file,
    }


def _import_auto_symbols():
    """Import AUTO SMT solver symbols with run-root fallback."""
    try:
        from auto import solve_puzzle_spec
    except ImportError:  # pragma: no cover
        from src.auto import solve_puzzle_spec

    return {
        "solve_puzzle_spec": solve_puzzle_spec,
    }


class BaseSolverAdapter(ABC):
    def __init__(self, solver_type: SolverType):
        self.solver_type = solver_type

    @abstractmethod
    def solve(
        self,
        puzzle: PuzzleSpec,
        config: SolverConfig,
        trace_sink: Optional[TraceSink] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> SolverResult:
        raise NotImplementedError

    def _emit(
        self,
        trace_sink: Optional[TraceSink],
        action: TraceAction,
        step_index: int,
        board,
        message: str,
        metadata: Optional[Dict] = None,
    ) -> None:
        if trace_sink is None:
            return
        trace_sink.push(
            TraceEvent(
                action=action,
                algorithm=self.solver_type.value,
                step_index=step_index,
                board_snapshot=clone_board(board),
                message=message,
                metadata=metadata or {},
            )
        )

    def _emit_solver_payload(self, trace_sink: Optional[TraceSink], payload: Dict) -> None:
        if trace_sink is None:
            return
        action_name = payload.get("action", TraceAction.PROGRESS.value)
        try:
            action = TraceAction(action_name)
        except ValueError:
            action = TraceAction.PROGRESS
        trace_sink.push(
            TraceEvent(
                action=action,
                algorithm=self.solver_type.value,
                step_index=int(payload.get("step_index", 0)),
                board_snapshot=clone_board(payload.get("board")),
                message=payload.get("message", ""),
                focus_cell=self._resolve_focus_cell(payload),
                metadata=payload.get("metadata", {}),
            )
        )

    def _emit_progressive_fill(
        self,
        trace_sink: Optional[TraceSink],
        start_step: int,
        start_board,
        target_board,
    ) -> int:
        if trace_sink is None:
            return start_step

        step = start_step
        working = clone_board(start_board)
        if working is None:
            return step

        n = len(working)
        for r in range(n):
            for c in range(n):
                new_val = target_board[r][c]
                if new_val == 0 or working[r][c] == new_val:
                    continue
                working[r][c] = new_val
                step += 1
                self._emit(
                    trace_sink,
                    TraceAction.ASSIGN,
                    step,
                    working,
                    "Assign {} at ({}, {})".format(new_val, r + 1, c + 1),
                    {"value": new_val},
                )
        return step
    
    @staticmethod
    def _resolve_focus_cell(payload: Dict):
        focus = payload.get("focus_cell")
        if isinstance(focus, (tuple, list)) and len(focus) == 2:
            r, c = focus[0], focus[1]
            if isinstance(r, int) and isinstance(c, int):
                return (r, c)

        metadata = payload.get("metadata", {}) or {}
        row = metadata.get("row")
        col = metadata.get("col")
        if isinstance(row, int) and isinstance(col, int):
            return (row, col)

        return None

class FCBacktrackAdapter(BaseSolverAdapter):
    def __init__(self):
        super().__init__(SolverType.FC_BACKTRACK)

    def solve(
        self,
        puzzle: PuzzleSpec,
        config: SolverConfig,
        trace_sink: Optional[TraceSink] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> SolverResult:
        symbols = _import_fc_backtrack_symbols()
        load_futoshiki = symbols["load_futoshiki"]
        solve_with_backtracking = symbols["solve_with_backtracking"]

        puzzle.validate()
        step = 0
        self._emit(trace_sink, TraceAction.STARTED, step, puzzle.board, "FC+Backtrack started")
        trace_step = 0
        emitted_assign_count = 0
        working_board = puzzle.clone_board()

        def on_fc_trace(payload):
            nonlocal trace_step, emitted_assign_count
            if trace_sink is None: return

            trace_step = max(trace_step, int(payload.get("step_index", trace_step + 1)))
            payload_with_board = dict(payload)
            payload_with_board["step_index"] = trace_step

            if payload_with_board.get("action") == TraceAction.ASSIGN.value:
                metadata = payload_with_board.get("metadata", {})
                row, col, value = metadata.get("row"), metadata.get("col"), metadata.get("value")
                if isinstance(row, int) and isinstance(col, int) and isinstance(value, int):
                    if 0 <= row < len(working_board) and 0 <= col < len(working_board[row]):
                        working_board[row][col] = value
                        payload_with_board["board"] = clone_board(working_board)
                        payload_with_board["focus_cell"] = (row, col)
                        emitted_assign_count += 1
            else:
                payload_with_board.setdefault("board", clone_board(working_board))

            self._emit_solver_payload(trace_sink, payload_with_board)

        start = time.perf_counter()
        with _temporary_input_file(puzzle, symbols["write_input_file"]) as file_path:
            n, kb, rules = load_futoshiki(file_path)
            kb_final = solve_with_backtracking(kb, rules, n, trace_callback=on_fc_trace, should_cancel=should_cancel)

        elapsed = time.perf_counter() - start
        
        if kb_final is None:
            stats = {"algorithm": "fc_backtrack", "execution_time": elapsed}
            self._emit(trace_sink, TraceAction.FAILED, trace_step + 1, working_board, "FC+Backtrack found no solution", stats)
            return SolverResult(status=SolverStatus.UNSAT, solved_board=None, stats=stats)

        solved_board = [[0 for _ in range(n)] for _ in range(n)]
        for pred in kb_final.get("Val", set()):
            solved_board[pred.terms[0].name - 1][pred.terms[1].name - 1] = pred.terms[2].name

        stats = {
            "algorithm": "fc_backtrack",
            "facts_total": sum(len(v) for v in kb_final.values()),
            "val_facts": len(kb_final.get("Val", set())),
            "execution_time": elapsed,
        }

        zero_count = sum(1 for row in solved_board for cell in row if cell == 0)
        stats = {
            "algorithm": "fc_backtrack",
            "facts_total": sum(len(v) for v in kb_final.values()),
            "val_facts": len(kb_final.get("Val", set())),
            "not_val_facts": len(kb_final.get("NotVal", set())),
            "execution_time": elapsed,
            "trace_assign_events": emitted_assign_count,
        }

        if zero_count > 0:
            self._emit(
                trace_sink,
                TraceAction.FAILED,
                trace_step + 1,
                solved_board,
                "FC+Backtrack ended with partial assignment",
                stats,
            )
            return SolverResult(
                status=SolverStatus.UNSAT,
                solved_board=solved_board,
                stats=stats,
                message="No complete assignment derived",
            )
        else:
            self._emit(
                trace_sink,
                TraceAction.SOLVED,
                trace_step + 1,
                solved_board,
                "FC+Backtrack solved puzzle",
                stats,
            )
            return SolverResult(
                status=SolverStatus.SOLVED,
                solved_board=solved_board,
                stats=stats,
                message="Solved",
            )

class AStarAdapter(BaseSolverAdapter):
    def __init__(self):
        super().__init__(SolverType.ASTAR)

    def solve(
        self,
        puzzle: PuzzleSpec,
        config: SolverConfig,
        trace_sink: Optional[TraceSink] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> SolverResult:
        symbols = _import_csp_symbols()
        Futoshiki = symbols["Futoshiki"]
        AStarSolver = symbols["AStarSolver"]

        puzzle.validate()

        game = Futoshiki(puzzle.size, puzzle.clone_board(), list(puzzle.constraints))
        solver = AStarSolver(game, heuristic=config.heuristic, use_mrv=config.use_mrv)

        def on_solver_trace(payload):
            self._emit_solver_payload(trace_sink, payload)

        start = time.perf_counter()
        board, stats = solver.solve(return_stats=True, trace_callback=on_solver_trace)
        elapsed = time.perf_counter() - start

        stats["adapter_elapsed"] = elapsed
        if board is None:
            return SolverResult(
                status=SolverStatus.UNSAT,
                solved_board=None,
                stats=stats,
                message="No solution found",
            )

        return SolverResult(
            status=SolverStatus.SOLVED,
            solved_board=board,
            stats=stats,
            message="Solved",
        )


class BacktrackAdapter(BaseSolverAdapter):
    def __init__(self):
        super().__init__(SolverType.BACKTRACK)

    def solve(
        self,
        puzzle: PuzzleSpec,
        config: SolverConfig,
        trace_sink: Optional[TraceSink] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> SolverResult:
        symbols = _import_csp_symbols()
        Futoshiki = symbols["Futoshiki"]
        BacktrackSolver = symbols["BacktrackSolver"]

        puzzle.validate()

        game = Futoshiki(puzzle.size, puzzle.clone_board(), list(puzzle.constraints))
        solver = BacktrackSolver(game, use_mrv=config.use_mrv, use_ac3=config.use_ac3)

        def on_solver_trace(payload):
            self._emit_solver_payload(trace_sink, payload)

        start = time.perf_counter()
        board, stats = solver.solve(return_stats=True, trace_callback=on_solver_trace)
        elapsed = time.perf_counter() - start

        stats["adapter_elapsed"] = elapsed
        if board is None:
            return SolverResult(
                status=SolverStatus.UNSAT,
                solved_board=None,
                stats=stats,
                message="No solution found",
            )

        return SolverResult(
            status=SolverStatus.SOLVED,
            solved_board=board,
            stats=stats,
            message="Solved",
        )


class ForwardChainingAdapter(BaseSolverAdapter):
    def __init__(self):
        super().__init__(SolverType.FORWARD_CHAINING)

    def solve(
        self,
        puzzle: PuzzleSpec,
        config: SolverConfig,
        trace_sink: Optional[TraceSink] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> SolverResult:
        symbols = _import_fc_symbols()
        load_futoshiki = symbols["load_futoshiki"]
        fol_fc = symbols["fol_fc"]

        puzzle.validate()
        step = 0
        self._emit(trace_sink, TraceAction.STARTED, step, puzzle.board, "Forward chaining started")
        trace_step = 0
        emitted_assign_count = 0
        working_board = puzzle.clone_board()

        def on_fc_trace(payload):
            nonlocal trace_step
            nonlocal emitted_assign_count
            if trace_sink is None:
                return

            trace_step = max(trace_step, int(payload.get("step_index", trace_step + 1)))
            payload_with_board = dict(payload)
            payload_with_board["step_index"] = trace_step

            if payload_with_board.get("action") == TraceAction.ASSIGN.value:
                metadata = payload_with_board.get("metadata", {})
                row = metadata.get("row")
                col = metadata.get("col")
                value = metadata.get("value")
                if isinstance(row, int) and isinstance(col, int) and isinstance(value, int):
                    if 0 <= row < len(working_board) and 0 <= col < len(working_board[row]):
                        working_board[row][col] = value
                        payload_with_board["board"] = clone_board(working_board)
                        payload_with_board["focus_cell"] = (row, col)
                        emitted_assign_count += 1
            else:
                payload_with_board.setdefault("board", clone_board(working_board))

            self._emit_solver_payload(trace_sink, payload_with_board)

        trace_state = {
            "step_index": 0,
            "emit_scan_events": bool((config.metadata or {}).get("fc_emit_scan_events", True)),
        }

        start = time.perf_counter()
        with _temporary_input_file(puzzle, symbols["write_input_file"]) as file_path:
            n, kb, rules = load_futoshiki(file_path)
            kb_final = fol_fc(
                kb,
                rules,
                should_cancel=should_cancel,
                trace_callback=on_fc_trace,
                trace_state=trace_state,
            )

        solved_board = [[0 for _ in range(n)] for _ in range(n)]
        for pred in kb_final.get("Val", set()):
            row = pred.terms[0].name - 1
            col = pred.terms[1].name - 1
            val = pred.terms[2].name
            solved_board[row][col] = val

        elapsed = time.perf_counter() - start
        zero_count = sum(1 for row in solved_board for cell in row if cell == 0)
        stats = {
            "algorithm": "forward_chaining",
            "facts_total": sum(len(values) for values in kb_final.values()),
            "val_facts": len(kb_final.get("Val", set())),
            "not_val_facts": len(kb_final.get("NotVal", set())),
            "execution_time": elapsed,
            "trace_assign_events": emitted_assign_count,
        }

        step = max(step, trace_step)
        if emitted_assign_count == 0:
            step = self._emit_progressive_fill(trace_sink, step, puzzle.board, solved_board)

        if zero_count > 0:
            step += 1
            self._emit(trace_sink, TraceAction.FAILED, step, solved_board, "Forward chaining ended with partial assignment", stats)
            return SolverResult(
                status=SolverStatus.UNSAT,
                solved_board=solved_board,
                stats=stats,
                message="No complete assignment derived",
            )

        step += 1
        self._emit(trace_sink, TraceAction.SOLVED, step, solved_board, "Forward chaining solved puzzle", stats)
        return SolverResult(
            status=SolverStatus.SOLVED,
            solved_board=solved_board,
            stats=stats,
            message="Solved",
        )


class BackwardChainingAdapter(BaseSolverAdapter):
    def __init__(self):
        super().__init__(SolverType.BACKWARD_CHAINING)

    def solve(
        self,
        puzzle: PuzzleSpec,
        config: SolverConfig,
        trace_sink: Optional[TraceSink] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> SolverResult:
        symbols = _import_bc_symbols()
        load_and_solve_futoshiki = symbols["load_and_solve_futoshiki"]
        fol_bc_and = symbols["fol_bc_and"]
        subst = symbols["subst"]

        puzzle.validate()
        step = 0
        self._emit(trace_sink, TraceAction.STARTED, step, puzzle.board, "Backward chaining started")
        trace_step = 0

        def on_bc_trace(payload):
            nonlocal trace_step
            if trace_sink is None:
                return
            trace_step = max(trace_step, int(payload.get("step_index", trace_step + 1)))
            payload_with_step = dict(payload)
            payload_with_step["step_index"] = trace_step
            self._emit_solver_payload(trace_sink, payload_with_step)

        trace_state = {"step_index": 0}

        start = time.perf_counter()
        with _temporary_input_file(puzzle, symbols["write_input_file"]) as file_path:
            kb, query_goals, variables, size = load_and_solve_futoshiki(file_path)

            solved_board = None
            solution_count = 0
            for theta in fol_bc_and(
                kb,
                query_goals,
                {},
                should_cancel=should_cancel,
                trace_callback=on_bc_trace,
                trace_state=trace_state,
            ):
                solution_count += 1
                grid = [[0 for _ in range(size)] for _ in range(size)]
                for var in variables:
                    parts = var.name.split("_")
                    row = int(parts[1]) - 1
                    col = int(parts[2]) - 1
                    grid[row][col] = subst(theta, var).name
                solved_board = grid
                if solution_count >= max(1, config.max_solutions):
                    break

        elapsed = time.perf_counter() - start
        stats = {
            "algorithm": "backward_chaining",
            "solutions_examined": solution_count,
            "execution_time": elapsed,
        }

        step = max(step, trace_step)

        if solved_board is not None:
            step = self._emit_progressive_fill(trace_sink, step, puzzle.board, solved_board)

        if solved_board is None:
            step += 1
            self._emit(trace_sink, TraceAction.FAILED, step, puzzle.board, "Backward chaining found no solution", stats)
            return SolverResult(
                status=SolverStatus.UNSAT,
                solved_board=None,
                stats=stats,
                message="No solution found",
            )

        step += 1
        self._emit(trace_sink, TraceAction.SOLVED, step, solved_board, "Backward chaining solved puzzle", stats)
        return SolverResult(
            status=SolverStatus.SOLVED,
            solved_board=solved_board,
            stats=stats,
            message="Solved",
        )


class AutoAdapter(BaseSolverAdapter):
    def __init__(self):
        super().__init__(SolverType.AUTO)

    def solve(
        self,
        puzzle: PuzzleSpec,
        config: SolverConfig,
        trace_sink: Optional[TraceSink] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> SolverResult:
        symbols = _import_auto_symbols()
        solve_puzzle_spec = symbols["solve_puzzle_spec"]

        puzzle.validate()
        step = 0
        self._emit(trace_sink, TraceAction.STARTED, step, puzzle.board, "AUTO (SMT) started")

        if should_cancel is not None and should_cancel():
            raise RuntimeError("Solve cancelled")

        timeout_ms = config.metadata.get("timeout_ms") if config.metadata else None

        start = time.perf_counter()
        solved_board = solve_puzzle_spec(
            puzzle.size,
            puzzle.board,
            puzzle.constraints,
            timeout_ms=timeout_ms,
        )
        elapsed = time.perf_counter() - start

        stats = {
            "algorithm": "auto_smt",
            "execution_time": elapsed,
        }
        if timeout_ms is not None:
            stats["timeout_ms"] = timeout_ms

        if solved_board is None:
            step += 1
            self._emit(trace_sink, TraceAction.FAILED, step, puzzle.board, "AUTO (SMT) found no solution", stats)
            return SolverResult(
                status=SolverStatus.UNSAT,
                solved_board=None,
                stats=stats,
                message="No solution found",
            )

        step += 1
        self._emit(trace_sink, TraceAction.SOLVED, step, solved_board, "AUTO (SMT) solved puzzle", stats)
        return SolverResult(
            status=SolverStatus.SOLVED,
            solved_board=solved_board,
            stats=stats,
            message="Solved",
        )


class _temporary_input_file:
    """Context manager to pass PuzzleSpec to file-based solvers."""

    def __init__(self, puzzle: PuzzleSpec, write_input_file_fn):
        self._puzzle = puzzle
        self._write_input_file = write_input_file_fn
        self._path = ""

    def __enter__(self):
        with tempfile.NamedTemporaryFile(prefix="futoshiki_gui_", suffix=".txt", delete=False) as tmp:
            self._path = tmp.name
        self._write_input_file(self._path, self._puzzle.size, self._puzzle.board, self._puzzle.constraints)
        return self._path

    def __exit__(self, exc_type, exc, tb):
        if self._path and os.path.exists(self._path):
            os.remove(self._path)


def build_adapter(solver_type: SolverType) -> BaseSolverAdapter:
    if solver_type == SolverType.ASTAR:
        return AStarAdapter()
    if solver_type == SolverType.BACKTRACK:
        return BacktrackAdapter()
    if solver_type == SolverType.FORWARD_CHAINING:
        return ForwardChainingAdapter()
    if solver_type == SolverType.BACKWARD_CHAINING:
        return BackwardChainingAdapter()
    if solver_type == SolverType.FC_BACKTRACK:
        return FCBacktrackAdapter()
    if solver_type == SolverType.AUTO:
        return AutoAdapter()
    raise ValueError("Unsupported solver type: {}".format(solver_type))
