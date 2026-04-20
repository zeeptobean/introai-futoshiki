from futoshiki import Futoshiki
from astar_solver import AStarSolver
from backtrack_solver import BacktrackSolver
from AC3 import FutoshikiAC3
from futoshiki_fetcher import FutoshikiFetcher
from auto import load_and_solve_futoshiki as auto_solve_futoshiki
from bc3 import bc_solve
from fc31 import fc_solve
from fcbacktrack import fc_mrv_solve
import time
from utils import read_input_file, parse_futoshiki2, print_futoshiki2
import argparse


DEFAULT_HEURISTICS = [
    "weighted_domain",
    "inequality_chains",
    "unforced_cells",
    "unassigned",
]


def normalize_board(board):
    return [list(row) for row in board]


def test_fetch_and_solve(
    size_min=4, size_max=9,
    difficulty_min=0, difficulty_max=3,
    game_id_min=0, game_id_max=9999,
    max_cases=None,
):
    """
    Test fetch + solve for many parameter sets and compare result with answer.
    """
    start_time  = time.perf_counter()
    total       = 0
    fetched     = 0
    solved      = 0
    matched     = 0
    failed_fetch  = 0
    failed_solve  = 0
    mismatched    = 0

    for size in range(size_min, size_max + 1):
        for difficulty in range(difficulty_min, difficulty_max + 1):
            for game_id in range(game_id_min, game_id_max + 1):
                if max_cases is not None and total >= max_cases:
                    print(f"Stopped at max_cases={max_cases}")
                    print(f"Total: {total}, fetched: {fetched}, solved: {solved}, matched: {matched}, "
                          f"fetch_failed: {failed_fetch}, solve_failed: {failed_solve}, mismatched: {mismatched}")
                    return

                total += 1
                puzzle = FutoshikiFetcher.fetch_puzzle(size=size, difficulty=difficulty, game_id=game_id)
                if not puzzle:
                    failed_fetch += 1
                    continue

                fetched     += 1
                n           = puzzle["size"]
                board       = puzzle["board"]
                constraints = puzzle["constraints"]
                answer      = puzzle["answer"]

                game   = Futoshiki(n, normalize_board(board), constraints)
                solver = AStarSolver(game, heuristic="weighted_domain")
                result, stats = solver.solve(return_stats=True)

                if result is None:
                    failed_solve += 1
                    print(f"[NO SOLUTION] size={size}, difficulty={difficulty}, game_id={game_id}")
                    continue

                solved += 1
                if result == answer:
                    matched += 1
                    print(f"[OK] size={size}, difficulty={difficulty}, game_id={game_id}, "
                          f"expanded={stats['expanded_nodes']}")
                else:
                    mismatched += 1
                    print(f"[MISMATCH] size={size}, difficulty={difficulty}, game_id={game_id}")
                    print("Result:")
                    for row in result:
                        print(row)
                    print("Answer:")
                    for row in answer:
                        print(row)

    print("Done")
    print(f"Total: {total}")
    print(f"Fetched: {fetched}")
    print(f"Solved: {solved}")
    print(f"Matched: {matched}")
    print(f"Fetch failed: {failed_fetch}")
    print(f"Solve failed: {failed_solve}")
    print(f"Mismatched: {mismatched}")
    print(f"Execution time: {time.perf_counter() - start_time:.4f} seconds")


def run_backtrack(use_mrv=True, use_ac3=True, USE_ONLINE=True, file_path=None, online_puzzle_size=7):
    """Run a single backtracking example."""

    if USE_ONLINE:
        puzzle = FutoshikiFetcher.fetch_puzzle(size=online_puzzle_size, difficulty=2, game_id=6767)
        if puzzle:
            n           = puzzle["size"]
            board       = puzzle["board"]
            constraints = puzzle["constraints"]
            answer      = puzzle["answer"]
        else:
            print("Error fetching puzzle")
            return
    else:
        if file_path:
            n, board, constraints = read_input_file(file_path)
            print("Loaded puzzle from file:", file_path)
            answer = auto_solve_futoshiki(file_path)
        else:
            raise ValueError("File path must be provided when USE_ONLINE is False")

    print("Input Board:")
    game   = Futoshiki(n, board, constraints)
    print(game)
    solver = BacktrackSolver(game, use_mrv=use_mrv, use_ac3=use_ac3)
    result, stats = solver.solve(return_stats=True)

    result_board = Futoshiki(n, result, constraints) if result else None
    answer_board = Futoshiki(n, answer, constraints) if answer else None

    if result_board is not None:
        print("\nSolution found")
        print(result_board)
    else:
        print("No solution found")

    if USE_ONLINE:
        print("\nExpected answer (online):")
    else:
        print("\nExpected answer (from z3 solver):")
    if answer is not None:
        print(answer_board)

        if result is not None and result == answer:
            print("✅ Result matches expected answer!\n")
        else:
            print("❌ Result does NOT match expected answer.\n")
    else:
        print("Unsatisfiable board")

    print("[Backtracking] Stats:")
    print("  visited_nodes:", stats["visited_nodes"])
    print("  backtracks:",    stats["backtracks"])
    print("  max_recursion_depth:", stats["max_recursion_depth"])
    print("  use_mrv:",       stats["use_mrv"])
    print("  use_ac3:",       stats["use_ac3"])
    print("  execution_time: {:.4f}s".format(stats["execution_time"]))
    print("-" * 40)


def run_astar(heuristic="inequality_chains", USE_ONLINE=True, file_path=None, online_puzzle_size=7):

    if USE_ONLINE:
        puzzle = FutoshikiFetcher.fetch_puzzle(size=online_puzzle_size, difficulty=2, game_id=6767)
        if puzzle:
            n           = puzzle["size"]
            board       = puzzle["board"]
            constraints = puzzle["constraints"]
            answer      = puzzle["answer"]
        else:
            print("Error fetching puzzle")
            return
    else:
        if file_path:
            n, board, constraints = read_input_file(file_path)
            print("Loaded puzzle from file:", file_path)
            answer = auto_solve_futoshiki(file_path)
        else:
            raise ValueError("File path must be provided when USE_ONLINE is False")



    print("Input Board:")
    game   = Futoshiki(n, board, constraints)
    print(game)
    solver = AStarSolver(game, heuristic=heuristic, use_mrv=True)
    result, stats = solver.solve(return_stats=True)

    result_board = Futoshiki(n, result, constraints) if result else None
    answer_board = Futoshiki(n, answer, constraints) if answer else None

    if result_board is not None:
        print("\nSolution found")
        print(result_board)
    else:
        print("No solution found")

    if USE_ONLINE:
        print("\nExpected answer (online):")
    else:
        print("\nExpected answer (from z3 solver):")
    if answer is not None:
        print(answer_board)

        if result is not None and result == answer:
            print("✅ Result matches expected answer!\n")
        else:
            print("❌ Result does NOT match expected answer.\n")
    else:
        print("Unsatisfiable board")

    print("\nSearch stats:")
    print("Heuristic:",       stats["heuristic"])
    print("Expanded nodes:",  stats["expanded_nodes"])
    print("Generated nodes:", stats["generated_nodes"])
    print("Max queue size:",  stats["max_queue_size"])
    print("Execution time: {:.4f}s".format(stats["execution_time"]))
    print("Memory usage (peak): {} bytes".format(stats["memory_usage"]))

    print("-" * 40)

def run_chaining(input_file: str, algo: str):
    if algo == "bc":
        brand = "backward chaining"
    elif algo == "fc":
        brand = "forward chaining"
    elif algo == "fc_mrv":
        brand = "hybrid forward chaining + MRV"
    else:
        raise ValueError("Invalid chaining algorithm choice")
    
    print(f"Running {brand} FOL solver on {input_file}...")
    print("Input board:")
    grid, horiz_constraints, vert_constraints = parse_futoshiki2(input_file)
    print_futoshiki2(grid, horiz_constraints, vert_constraints)

    if algo == "bc":
        solution, time_taken = bc_solve(input_file)
    elif algo == "fc":
        solution, time_taken = fc_solve(input_file)
    elif algo == "fc_mrv":
        solution, time_taken = fc_mrv_solve(input_file)
        
    answer = auto_solve_futoshiki(input_file)
    if solution is not None:
        print("Solution found:")
        print_futoshiki2(solution, horiz_constraints, vert_constraints)
    else:
        print("No solution found")
    print(f"Time taken: {time_taken:.4f} seconds\n")
    print("Expected answer (from z3 solver):")
    if answer is not None:
        print_futoshiki2(answer, horiz_constraints, vert_constraints)

        if solution is not None and solution == answer:
            print("✅ Result matches expected answer!")
        else:
            print("❌ Result does NOT match expected answer.")
    else:
        print("Unsatisfiable board")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Futoshiki solver",
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument(
        "--algorithm", "-a", 
        choices=['as_unassigned', 'as_inequality_chains', 'as_unforced_cells', 'as_weighted_domain', 'backtrack', 'backtrack_mrv', 'fc', 'bc', 'fc_mrv'], 
        required=True,
        help="""The algorithm to run. Choices are:
        - as_unassigned: A* with unassigned variable heuristic
        - as_inequality_chains: A* with inequality chains heuristic
        - as_unforced_cells: A* with unforced cells heuristic
        - as_weighted_domain: A* with weighted domain heuristic
        - backtrack: Backtracking naive
        - backtrack_mrv: Backtracking with MRV + AC3
        - fc: Forward chaining FOL
        - bc: Backward chaining FOL
        - fc_mrv: Hybrid forward chaining + MRV
        """
    )

    parser.add_argument(
        "--online",
        action="store_true",
        help="Fetch puzzle online and ignore filename"
    )

    parser.add_argument(
        "--size",
        type=int,
        default=7,
        help="Board size for online puzzles (default: 9)"
    )

    parser.add_argument(
        "filename", 
        nargs="?",
        help="The file containing the Futoshiki puzzle input (ignored when --online is set)"
    )

    args = parser.parse_args()

    # Validation
    if not args.online and not args.filename:
        parser.error("filename is required unless --online is set")

    if args.online and args.algorithm in ("fc", "bc", "fc_mrv"):
        parser.error("--online is not supported for fc, bc, or fc_mrv algorithms")

    use_online: bool = args.online
    input_file = args.filename      # does not need to set none if online as run_astar and run_backtrack handle it 

    match args.algorithm:
        case "as_unassigned":
            run_astar(heuristic="unassigned", USE_ONLINE=use_online, file_path=input_file, online_puzzle_size=args.size)
        case "as_inequality_chains":
            run_astar(heuristic="inequality_chains", USE_ONLINE=use_online, file_path=input_file, online_puzzle_size=args.size)
        case "as_unforced_cells":
            run_astar(heuristic="unforced_cells", USE_ONLINE=use_online, file_path=input_file, online_puzzle_size=args.size)
        case "as_weighted_domain":
            run_astar(heuristic="weighted_domain", USE_ONLINE=use_online, file_path=input_file, online_puzzle_size=args.size)
        case "backtrack":
            run_backtrack(use_mrv=False, use_ac3=False, USE_ONLINE=use_online, file_path=input_file, online_puzzle_size=args.size)
        case "backtrack_mrv":
            run_backtrack(use_mrv=True, use_ac3=True, USE_ONLINE=use_online, file_path=input_file, online_puzzle_size=args.size)
        case "fc":
            run_chaining(input_file, algo="fc")
        case "bc":
            run_chaining(input_file, algo="bc")
        case "fc_mrv":
            run_chaining(input_file, algo="fc_mrv")
        case _:
            print("Unknown algorithm choice")