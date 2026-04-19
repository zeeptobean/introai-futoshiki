"""Trace event contracts for visualization and replay."""

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class TraceAction(str, Enum):
    STARTED = "started"
    NODE_EXPANDED = "node_expanded"
    ASSIGN = "assign"
    BACKTRACK = "backtrack"
    CONTRADICTION = "contradiction"
    PROGRESS = "progress"
    SOLVED = "solved"
    FAILED = "failed"
    ERROR = "error"


@dataclass
class TraceEvent:
    """Serializable event for solve animation."""

    action: TraceAction
    algorithm: str
    step_index: int
    board_snapshot: Optional[List[List[int]]] = None
    message: str = ""
    focus_cell: Optional[Tuple[int, int]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class TraceSink:
    """Thread-safe sink to store trace events."""

    def __init__(self, on_event=None) -> None:
        self._lock = threading.Lock()
        self._events: List[TraceEvent] = []
        self._on_event = on_event

    def push(self, event: TraceEvent) -> None:
        with self._lock:
            self._events.append(event)
        if self._on_event is not None:
            self._on_event(event)

    def snapshot(self) -> List[TraceEvent]:
        with self._lock:
            return list(self._events)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()

    @property
    def has_live_listener(self) -> bool:
        return self._on_event is not None


def clone_board(board: Optional[List[List[int]]]) -> Optional[List[List[int]]]:
    if board is None:
        return None
    return [row[:] for row in board]
