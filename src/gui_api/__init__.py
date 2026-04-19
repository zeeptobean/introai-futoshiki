"""GUI integration API for Futoshiki solvers."""

from .contracts import PuzzleSpec, SolverConfig, SolverResult, SolverStatus, SolverType
from .trace import TraceAction, TraceEvent, TraceSink
from .adapters import build_adapter
from .worker import SolverWorker

__all__ = [
    "PuzzleSpec",
    "SolverConfig",
    "SolverResult",
    "SolverStatus",
    "SolverType",
    "TraceAction",
    "TraceEvent",
    "TraceSink",
    "build_adapter",
    "SolverWorker",
]
