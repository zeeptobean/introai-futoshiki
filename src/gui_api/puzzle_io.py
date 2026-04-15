"""Import/export helpers between object contract and input files."""

from typing import Any, Dict

from .contracts import PuzzleSpec

try:
    from utils import read_input_file, write_input_file
except ImportError:  # pragma: no cover
    from src.utils import read_input_file, write_input_file


def load_puzzle_from_file(file_path: str) -> PuzzleSpec:
    size, board, constraints = read_input_file(file_path)
    spec = PuzzleSpec(size=size, board=board, constraints=constraints)
    spec.validate()
    return spec


def save_puzzle_to_file(spec: PuzzleSpec, file_path: str, comment: str = "") -> None:
    spec.validate()
    write_input_file(
        filepath=file_path,
        n=spec.size,
        board=spec.board,
        constraints=spec.constraints,
        header_comment=comment or None,
    )


def puzzle_from_object(payload: Dict[str, Any]) -> PuzzleSpec:
    return PuzzleSpec.from_dict(payload)


def puzzle_to_object(spec: PuzzleSpec) -> Dict[str, Any]:
    spec.validate()
    return spec.to_dict()
