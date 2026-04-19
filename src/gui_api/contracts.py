"""Shared contracts for GUI <-> solver integration."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

Constraint = Tuple[Tuple[int, int], Tuple[int, int]]


class SolverType(str, Enum):
    ASTAR = "astar"
    BACKTRACK = "backtrack"
    FORWARD_CHAINING = "forward_chaining"
    BACKWARD_CHAINING = "backward_chaining"
    FC_BACKTRACK = "fc_backtrack"
    AUTO = "auto"


class SolverStatus(str, Enum):
    SOLVED = "solved"
    UNSAT = "unsat"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class PuzzleSpec:
    """Puzzle payload used by GUI and solver adapters."""

    size: int
    board: List[List[int]]
    constraints: List[Constraint]

    def validate(self) -> None:
        if self.size <= 0:
            raise ValueError("size must be positive")

        if len(self.board) != self.size:
            raise ValueError("board must have size rows")
        for row in self.board:
            if len(row) != self.size:
                raise ValueError("board must be square")
            for value in row:
                if value < 0 or value > self.size:
                    raise ValueError("board values must be in range [0, size]")

        for pair in self.constraints:
            if len(pair) != 2:
                raise ValueError("constraint must contain two positions")
            (r1, c1), (r2, c2) = pair
            for r, c in ((r1, c1), (r2, c2)):
                if r < 0 or c < 0 or r >= self.size or c >= self.size:
                    raise ValueError("constraint position out of bounds")
            if (r1, c1) == (r2, c2):
                raise ValueError("constraint must connect two different cells")

    def clone_board(self) -> List[List[int]]:
        return [row[:] for row in self.board]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "size": self.size,
            "board": self.clone_board(),
            "constraints": [((r1, c1), (r2, c2)) for (r1, c1), (r2, c2) in self.constraints],
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "PuzzleSpec":
        size = int(payload["size"])
        board = [[int(v) for v in row] for row in payload["board"]]
        constraints = [
            ((int(a[0]), int(a[1])), (int(b[0]), int(b[1])))
            for a, b in payload["constraints"]
        ]
        spec = cls(size=size, board=board, constraints=constraints)
        spec.validate()
        return spec


@dataclass
class SolverConfig:
    """Optional controls for solver execution."""

    solver_type: SolverType
    heuristic: str = "weighted_domain"
    use_mrv: bool = True
    use_ac3: bool = True
    max_solutions: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SolverResult:
    """Unified result contract returned by all adapters."""

    status: SolverStatus
    solved_board: Optional[List[List[int]]]
    stats: Dict[str, Any] = field(default_factory=dict)
    message: str = ""
    trace_meta: Dict[str, Any] = field(default_factory=dict)


def ensure_board_shape(size: int, board: Sequence[Sequence[int]]) -> None:
    if len(board) != size:
        raise ValueError("invalid board row count")
    for row in board:
        if len(row) != size:
            raise ValueError("invalid board column count")
