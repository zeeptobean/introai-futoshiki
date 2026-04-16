import argparse
import csv
import glob
import logging
import os
import re
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Callable, List, Optional, Tuple

# Make both imports styles work:
# - fc31 uses "from myfol import *" (needs ./src on sys.path)
# - bc3 uses "from src.myfol import *" (needs repo root on sys.path)
ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
for p in (str(ROOT_DIR), str(SRC_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from src.auto import load_and_solve_futoshiki
from src.fc31 import fol_fc, load_futoshiki as load_fc_futoshiki
from src.bc3 import fol_bc_and, load_and_solve_futoshiki as load_bc_futoshiki, subst


def _input_sort_key(path: str) -> int:
    name = os.path.basename(path)
    m = re.search(r"input-(\d+)\.txt$", name)
    return int(m.group(1)) if m else 10**9


def _configure_logger(log_path: str) -> logging.Logger:
    logger = logging.getLogger("bench_chaining")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    return logger


def _flush_logger(logger: logging.Logger) -> None:
    for handler in logger.handlers:
        handler.flush()


def _log_info(logger: logging.Logger, msg: str, *args) -> None:
    logger.info(msg, *args)
    _flush_logger(logger)


def _extract_fc_board(final_kb, n: int) -> Optional[List[List[int]]]:
    """
    Return full NxN board if FC produced exactly one Val for every cell.
    Return None if incomplete or contradictory.
    """
    val_facts = final_kb.get("Val", set())
    cell_to_values = {}

    for fact in val_facts:
        r = fact.terms[0].name - 1  # 1-based -> 0-based
        c = fact.terms[1].name - 1
        v = fact.terms[2].name
        cell_to_values.setdefault((r, c), set()).add(v)

    if len(cell_to_values) != n * n:
        return None

    board = [[0 for _ in range(n)] for _ in range(n)]
    for r in range(n):
        for c in range(n):
            vals = cell_to_values.get((r, c))
            if not vals or len(vals) != 1:
                return None
            board[r][c] = next(iter(vals))

    return board


def _extract_bc_board(solution_theta, variables, size: int) -> Optional[List[List[int]]]:
    """
    Reconstruct board from BC substitution using variable names v_r_c.
    """
    if solution_theta is None:
        return None

    board = [[0 for _ in range(size)] for _ in range(size)]
    for var in variables:
        name = str(var.name)  # expected: v_1_1, v_1_2, ...
        parts = name.split("_")
        if len(parts) != 3 or parts[0] != "v":
            continue

        r = int(parts[1]) - 1
        c = int(parts[2]) - 1
        value_term = subst(solution_theta, var)
        value = getattr(value_term, "name", None)
        if value is None:
            return None
        board[r][c] = int(value)

    # Must be fully assigned
    for row in board:
        if any(v == 0 for v in row):
            return None
    return board


def _run_fc_once(input_path: str) -> Tuple[Optional[List[List[int]]], float, float]:
    """
    Run FC only (no Z3 time included).
    Returns: (fc_board_or_none, elapsed_seconds, peak_memory_mb)
    """
    n, kb, rules = load_fc_futoshiki(input_path)

    tracemalloc.start()
    t0 = time.perf_counter()
    try:
        final_kb = fol_fc(kb, rules)
    finally:
        elapsed = time.perf_counter() - t0
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

    peak_kb = peak_bytes / (1024.0)
    fc_board = _extract_fc_board(final_kb, n)
    return fc_board, elapsed, peak_kb


def _run_bc_once(input_path: str) -> Tuple[Optional[List[List[int]]], float, float]:
    """
    Run BC only (no Z3 time included).
    Returns: (bc_board_or_none, elapsed_seconds, peak_memory_mb)
    """
    kb, query_goals, variables, size = load_bc_futoshiki(input_path)

    tracemalloc.start()
    t0 = time.perf_counter()
    try:
        solution_theta = None
        for candidate in fol_bc_and(kb, query_goals, {}):
            solution_theta = candidate
            break
    finally:
        elapsed = time.perf_counter() - t0
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

    peak_kb = peak_bytes / (1024.0)
    bc_board = _extract_bc_board(solution_theta, variables, size)
    return bc_board, elapsed, peak_kb


def _run_and_record(
    algo_name: str,
    input_path: str,
    logger: logging.Logger,
    runner: Callable[[str], Tuple[Optional[List[List[int]]], float, float]],
) -> List[str]:
    filename = os.path.basename(input_path)
    _log_info(logger, "run_start | algo=%s | input=%s", algo_name, filename)

    try:
        board, sec, mem_kb = runner(input_path)
        run_ok = True
        err = ""
    except Exception as exc:
        board, sec, mem_kb = None, 0.0, 0.0
        run_ok = False
        err = repr(exc)

    # Invoke Z3 checker for this run
    try:
        z3_board = load_and_solve_futoshiki(input_path)
        is_correct = run_ok and (board is not None) and (z3_board is not None) and (board == z3_board)
    except Exception as exc:
        is_correct = False
        if err:
            err += " | "
        err += "z3=" + repr(exc)

    _log_info(
        logger,
        "run_end | algo=%s | input=%s | time=%.6f | memory_mb=%.6f | iscorrect=%s | error=%s",
        algo_name,
        filename,
        sec,
        mem_kb,
        str(is_correct).lower(),
        err if err else "none",
    )

    return [
        algo_name,
        filename,
        "{:.6f}".format(mem_kb),
        "{:.6f}".format(sec),
        "true" if is_correct else "false",
    ]


def benchmark_all(inputs_dir: str, logger: logging.Logger) -> List[List[str]]:
    paths = glob.glob(os.path.join(inputs_dir, "input-*.txt"))
    paths.sort(key=_input_sort_key)

    rows: List[List[str]] = []
    for path in paths:
        rows.append(_run_and_record("forward_chaining_fc31", path, logger, _run_fc_once))
        rows.append(_run_and_record("backward_chaining_bc3", path, logger, _run_bc_once))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs-dir", default="Inputs")
    parser.add_argument("--out", default="")
    parser.add_argument("--log-file", default="bench-chaining.log")
    args = parser.parse_args()

    logger = _configure_logger(args.log_file)
    _log_info(logger, "benchmark_start | inputs_dir=%s", args.inputs_dir)

    header = ["algo", "inputfilename", "memory", "time", "iscorrect"]
    rows = benchmark_all(args.inputs_dir, logger)

    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)
    else:
        writer = csv.writer(sys.stdout)
        writer.writerow(header)
        writer.writerows(rows)

    _log_info(logger, "benchmark_end | rows=%d", len(rows))


if __name__ == "__main__":
    main()