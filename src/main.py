from futoshiki import Futoshiki
from astar_solver import AStarSolver
from backtrack_solver import BacktrackSolver
from AC3 import FutoshikiAC3
from futoshiki_fetcher import FutoshikiFetcher
import time
from utils import read_input_file


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


def run_single_backtracking_example(use_mrv=True, use_ac3=True, USE_ONLINE=True, file_path=None):
    """Run a single backtracking example."""
    start_time = time.perf_counter()

    if USE_ONLINE:
        puzzle = FutoshikiFetcher.fetch_puzzle(size=9, difficulty=3, game_id=6767)
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
        else:
            n    = 4
            board = [
                [0, 0, 0, 0],
                [0, 0, 0, 0],
                [0, 0, 0, 0],
                [0, 0, 0, 4],
            ]
            constraints = [((3, 3), (3, 2))]
            answer = []

    print("[Backtracking] Input Board:")
    for row in board:
        print(row)

    game   = Futoshiki(n, normalize_board(board), constraints)
    solver = BacktrackSolver(game, use_mrv=use_mrv, use_ac3=use_ac3)
    result, stats = solver.solve(return_stats=True)

    if result is None:
        print("[Backtracking] No solution found")
    else:
        print("[Backtracking] Result:")
        for row in result:
            print(row)
        if USE_ONLINE and answer:
            print("\nExpected Answer:")
            for row in answer:
                print(row)
            if result == answer:
                print("\n✅ Result matches expected answer!")
            else:
                print("\n❌ Result does NOT match expected answer.")

    print("[Backtracking] Stats:")
    print("  visited_nodes:", stats["visited_nodes"])
    print("  backtracks:",    stats["backtracks"])
    print("  max_recursion_depth:", stats["max_recursion_depth"])
    print("  use_mrv:",       stats["use_mrv"])
    print("  use_ac3:",       stats["use_ac3"])
    print("  execution_time: {:.4f}s".format(stats["execution_time"]))
    print("-" * 40)


def run_single_example(heuristic="inequality_chains", USE_ONLINE=True, file_path=None):

    if USE_ONLINE:
        puzzle = FutoshikiFetcher.fetch_puzzle(size=9, difficulty=2, game_id=6767)
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
        else:
            n    = 4
            board = [
                [0, 0, 0, 0],
                [0, 0, 0, 0],
                [0, 0, 0, 0],
                [0, 0, 0, 4],
            ]
            constraints = [((3, 3), (3, 2))]
            answer = []
        


    print("Input Board:")
    for row in board:
        print(row)

    game   = Futoshiki(n, normalize_board(board), constraints)
    solver = AStarSolver(game, heuristic=heuristic, use_mrv=False)
    result, stats = solver.solve(return_stats=True)

    if result:
        print("A* Result:")
        for row in result:
            print(row)
        print("\nExpected Answer:")
        if USE_ONLINE and answer:
            for row in answer:
                print(row)
            if result == answer:
                print("\n✅ Result matches expected answer!")
            else:
                print("\n❌ Result does NOT match expected answer.")
    else:
        print("No solution found")

    print("\nSearch stats:")
    print("Heuristic:",       stats["heuristic"])
    print("Expanded nodes:",  stats["expanded_nodes"])
    print("Generated nodes:", stats["generated_nodes"])
    print("Max queue size:",  stats["max_queue_size"])
    print("Execution time: {:.4f}s".format(stats["execution_time"]))
    print("Memory usage (peak): {} bytes".format(stats["memory_usage"]))

    print("-" * 40)


if __name__ == "__main__":
    # Compare heuristics quickly (enable when needed)
    # compare_heuristics(max_cases=10)

    # Run test if you want to scan many cases
    # test_fetch_and_solve(max_cases=20)

    # Run one single example by default
    run_single_example("unassigned", USE_ONLINE=True, file_path="Inputs/input-20.txt")
    # run_single_example("unassigned", USE_ONLINE=False, file_path="Inputs/input-20.txt")
    # run_single_example("inequality_chains")
    # run_single_example("unforced_cells")
    # run_single_example("weighted_domain")

    run_single_backtracking_example(use_mrv=True, use_ac3=True, USE_ONLINE=True, file_path="Inputs/input-01.txt")
    # run_single_backtracking_example(use_mrv=False, use_ac3=False)
