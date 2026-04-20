# IntroAI course project: Futoshiki

A Python project for solving Futoshiki puzzles using multiple AI approaches:

- A* search with several heuristics
- Backtracking (with optional MRV + AC-3)
- Forward and backward chaining (FOL-based)
- CNF + SAT solving
- Interactive Pygame GUI

Main implementation is in [src](src).

## Members
#### Group name: Lorem_Ipsum
- 24127003 - Vũ Trần Minh Hiếu
- 24127240 - Hoàng Đức Thịnh
- 24127270 - Trần Viết Bảo
- 24127326 - Đoàn Quốc Bảo

## Features

- Multiple solver strategies in one codebase
- Online puzzle fetching from futoshiki.com for selected algorithms
- Local file-based puzzle solving
- Optional GUI with play and solve modes
- Built-in sample inputs in [Inputs](Inputs) and expected outputs in [Outputs](Outputs)

## Project Structure

- [src/main.py](src/main.py): Main CLI entry point for A*, backtracking, and chaining solvers
- [src/main_gui.py](src/main_gui.py): Pygame GUI app
- [src/cnf.py](src/cnf.py): CNF/SAT-based solver CLI
- [src/astar_solver.py](src/astar_solver.py): A* implementation
- [src/backtrack_solver.py](src/backtrack_solver.py): Backtracking implementation
- [src/futoshiki_fetcher.py](src/futoshiki_fetcher.py): Online puzzle fetch utility
- [src/utils.py](src/utils.py): Input parsing and format utilities
- [Inputs](Inputs): Sample puzzle files
- [Outputs](Outputs): Output files

## Requirements

- Python 3.13 (from [pyproject.toml](pyproject.toml) and [.python-version](.python-version))
- Internet access only if you use online fetching mode

## Setup

### Option 1: pip

1. Create a virtual environment.

PowerShell (Windows):

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

For other platform follow platform's instruction

2. Install dependencies.

```powershell
pip install -r requirements.txt
```

### Option 2: uv

```powershell
uv sync
```

Run commands with uv run (examples are shown in the next sections).

## Run Instructions

Run commands from the repository root so relative paths like Inputs/input-01.txt resolve correctly.

### 1. Main CLI Solver

Script: [src/main.py](src/main.py)

General form:

```powershell
python src/main.py --algorithm ALGO [--online --size N] [filename]
```

Examples:

- A* (weighted domain) on local file

```powershell
python src/main.py --algorithm as_weighted_domain Inputs/input-01.txt
```

- A* (inequality chains) on local file

```powershell
python src/main.py --algorithm as_inequality_chains Inputs/input-02.txt
```

- Backtracking + MRV + AC3 on local file

```powershell
python src/main.py --algorithm backtrack_mrv Inputs/input-03.txt
```

- A* online puzzle (size 7)

```powershell
python src/main.py --algorithm as_weighted_domain --online --size 7
```

- Forward chaining (local only)

```powershell
python src/main.py --algorithm fc Inputs/input-04.txt
```

Available algorithms:

- `as_unassigned`
- `as_inequality_chains`
- `as_unforced_cells`
- `as_weighted_domain`
- `backtrack`
- `backtrack_mrv`
- `fc`
- `bc`
- `fc_mrv`

Notes:

- For `fc`, `bc`, and `fc_mrv` you must provide a local filename.
- `--online` is not supported for `fc`, `bc`, or `fc_mrv`.

### 2. GUI App

Script: [src/main_gui.py](src/main_gui.py)

```powershell
python src/main_gui.py
```

The GUI loads puzzle files from [Inputs](Inputs) and supports multiple solver modes through the UI.

### 3. CNF + SAT Solver

Script: [src/cnf.py](src/cnf.py)

```powershell
python src/cnf.py Inputs/input-01.txt
```

Verbose mode with readable clause preview:

```powershell
python src/cnf.py Inputs/input-01.txt --verbose --limit 30
```

Print all clauses:

```powershell
python src/cnf.py Inputs/input-01.txt --verbose --all
```

## Input File Format

Utilities are implemented in [src/utils.py](src/utils.py).

Each input file contains:

1. N (board size)
2. N lines of board values (0 means empty)
3. N lines of horizontal constraints (N-1 values per row)
4. N-1 lines of vertical constraints (N values per row)

Constraint encoding:

- 1 means left or top cell is less than right or bottom cell
- -1 means left or top cell is greater than right or bottom cell
- 0 means no inequality constraint

Example file: [Inputs/input-01.txt](Inputs/input-01.txt)

## Troubleshooting

- Online fetch fails:
	Check internet connection and retry with a different size, or run local input files instead.

## Quick Start

1. Install dependencies.
2. Run:

```powershell
python src/main.py --algorithm as_weighted_domain Inputs/input-01.txt
```

3. For GUI:

```powershell
python src/main_gui.py
```

## AI acknowledgement
Gemini 3.1 Pro and GPT-5.3-Codex is used in this project