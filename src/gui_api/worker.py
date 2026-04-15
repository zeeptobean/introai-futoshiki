"""Background solver worker for GUI thread separation."""

import queue
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .adapters import build_adapter
from .contracts import PuzzleSpec, SolverConfig, SolverResult, SolverStatus
from .trace import TraceAction, TraceEvent, TraceSink


class WorkerCommand(str, Enum):
    SOLVE = "solve"
    STOP = "stop"
    PAUSE = "pause"
    RESUME = "resume"
    STEP = "step"


@dataclass
class SolveRequest:
    puzzle: PuzzleSpec
    config: SolverConfig


class SolverWorker:
    """Run solver requests in a background thread and emit events."""

    def __init__(self):
        self._command_queue: "queue.Queue[tuple]" = queue.Queue()
        self._event_queue: "queue.Queue[object]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()
        self._paused = threading.Event()
        self._paused.clear()
        self._running_lock = threading.Lock()
        self._is_running = False
        self._trace_flow_lock = threading.Condition()
        self._step_budget = 0
        self._cancel_requested = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._loop, name="solver-worker", daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        self._stop_flag.set()
        self._command_queue.put((WorkerCommand.STOP, None))
        if self._thread:
            self._thread.join(timeout=1.0)

    def submit_solve(self, puzzle: PuzzleSpec, config: SolverConfig) -> None:
        self._command_queue.put((WorkerCommand.SOLVE, SolveRequest(puzzle=puzzle, config=config)))

    def pause(self) -> None:
        with self._trace_flow_lock:
            self._paused.set()
            self._step_budget = 0
            self._trace_flow_lock.notify_all()
        self._event_queue.put({"type": "worker_state", "state": "paused"})

    def resume(self) -> None:
        with self._trace_flow_lock:
            self._paused.clear()
            self._step_budget = 0
            self._trace_flow_lock.notify_all()
        self._event_queue.put({"type": "worker_state", "state": "running"})

    def step(self) -> None:
        with self._trace_flow_lock:
            # Step is meaningful only while paused; allow exactly one trace event.
            self._paused.set()
            self._step_budget = 1
            self._trace_flow_lock.notify_all()
        self._event_queue.put({"type": "worker_state", "state": "step_ack"})

    def stop_current(self) -> None:
        with self._trace_flow_lock:
            self._cancel_requested = True
            self._paused.clear()
            self._step_budget = 0
            self._trace_flow_lock.notify_all()
        self._event_queue.put({"type": "worker_state", "state": "stop_requested"})

    def poll_event(self, timeout: float = 0.0):
        try:
            return self._event_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _loop(self) -> None:
        while not self._stop_flag.is_set():
            try:
                cmd, payload = self._command_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if cmd == WorkerCommand.SOLVE and payload is not None:
                self._handle_solve(payload)
            elif cmd == WorkerCommand.PAUSE:
                with self._trace_flow_lock:
                    self._paused.set()
                    self._step_budget = 0
                    self._trace_flow_lock.notify_all()
                self._event_queue.put({"type": "worker_state", "state": "paused"})
            elif cmd == WorkerCommand.RESUME:
                with self._trace_flow_lock:
                    self._paused.clear()
                    self._step_budget = 0
                    self._trace_flow_lock.notify_all()
                self._event_queue.put({"type": "worker_state", "state": "running"})
            elif cmd == WorkerCommand.STEP:
                with self._trace_flow_lock:
                    # Step is meaningful only while paused; allow exactly one trace event.
                    self._paused.set()
                    self._step_budget = 1
                    self._trace_flow_lock.notify_all()
                self._event_queue.put({"type": "worker_state", "state": "step_ack"})
            elif cmd == WorkerCommand.STOP:
                if self._stop_flag.is_set():
                    break
                with self._trace_flow_lock:
                    self._cancel_requested = True
                    self._paused.clear()
                    self._step_budget = 0
                    self._trace_flow_lock.notify_all()
                self._event_queue.put({"type": "worker_state", "state": "stop_requested"})

    def _handle_solve(self, request: SolveRequest) -> None:
        with self._running_lock:
            self._is_running = True
        with self._trace_flow_lock:
            self._cancel_requested = False
            self._step_budget = 0
            self._paused.clear()

        trace_sink = TraceSink(on_event=self._emit_trace_event)
        self._event_queue.put({"type": "worker_state", "state": "running"})

        try:
            adapter = build_adapter(request.config.solver_type)
            result = adapter.solve(
                request.puzzle,
                request.config,
                trace_sink=trace_sink,
                should_cancel=self._should_cancel,
            )
            self._flush_trace(trace_sink)
            self._event_queue.put({"type": "solver_result", "result": result})
        except RuntimeError as exc:  # pragma: no cover
            if str(exc) == "Solve cancelled":
                self._event_queue.put(
                    {
                        "type": "solver_result",
                        "result": SolverResult(
                            status=SolverStatus.CANCELLED,
                            solved_board=None,
                            message="Solve cancelled",
                            stats={"algorithm": request.config.solver_type.value},
                        ),
                    }
                )
            else:
                error_event = TraceEvent(
                    action=TraceAction.ERROR,
                    algorithm=request.config.solver_type.value,
                    step_index=-1,
                    board_snapshot=request.puzzle.clone_board(),
                    message=str(exc),
                )
                trace_sink.push(error_event)
                self._flush_trace(trace_sink)
                self._event_queue.put(
                    {
                        "type": "solver_result",
                        "result": SolverResult(
                            status=SolverStatus.ERROR,
                            solved_board=None,
                            message=str(exc),
                            stats={"algorithm": request.config.solver_type.value},
                        ),
                    }
                )
        except Exception as exc:  # pragma: no cover
            error_event = TraceEvent(
                action=TraceAction.ERROR,
                algorithm=request.config.solver_type.value,
                step_index=-1,
                board_snapshot=request.puzzle.clone_board(),
                message=str(exc),
            )
            trace_sink.push(error_event)
            self._flush_trace(trace_sink)
            self._event_queue.put(
                {
                    "type": "solver_result",
                    "result": SolverResult(
                        status=SolverStatus.ERROR,
                        solved_board=None,
                        message=str(exc),
                        stats={"algorithm": request.config.solver_type.value},
                    ),
                }
            )
        finally:
            with self._running_lock:
                self._is_running = False
            with self._trace_flow_lock:
                self._paused.clear()
                self._step_budget = 0
                self._cancel_requested = False
                self._trace_flow_lock.notify_all()
            self._event_queue.put({"type": "worker_state", "state": "idle"})

    def _emit_trace_event(self, event: TraceEvent) -> None:
        with self._trace_flow_lock:
            while self._paused.is_set() and self._step_budget == 0 and not self._cancel_requested:
                self._trace_flow_lock.wait(timeout=0.1)

            if self._cancel_requested:
                raise RuntimeError("Solve cancelled")

            if self._paused.is_set() and self._step_budget > 0:
                self._step_budget -= 1

        self._event_queue.put({"type": "trace", "event": event})

    def _should_cancel(self) -> bool:
        with self._trace_flow_lock:
            return self._cancel_requested

    def _flush_trace(self, trace_sink: TraceSink) -> None:
        if trace_sink.has_live_listener:
            return
        events = trace_sink.snapshot()
        for event in events:
            self._event_queue.put({"type": "trace", "event": event})
