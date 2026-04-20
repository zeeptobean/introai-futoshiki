# backward chaining
from typing import TypeAlias, TypeVar
from collections.abc import Iterator
import time

from myfol import *


def _next_trace_step(trace_state):
    if trace_state is None:
        return 0
    trace_state["step_index"] = trace_state.get("step_index", 0) + 1
    return trace_state["step_index"]


def _emit_trace(trace_callback, trace_state, action, message, metadata=None):
    if trace_callback is None or trace_state is None:
        return
    
    max_events = trace_state.get("max_events", 0)
    if max_events > 0 and trace_state.get("step_index", 0) >= max_events:
        return

    trace_callback(
        {
            "action": action,
            "step_index": _next_trace_step(trace_state),
            "message": message,
            "metadata": metadata or {},
        }
    )

def subst(theta: Theta, x):
    if isinstance(x, Var):
        if x in theta: return subst(theta, theta[x])
        return x
    if isinstance(x, Const): 
        return x
    if isinstance(x, NativeMath):
        return NativeMath(x.func, [subst(theta, t) for t in x.terms])
    if isinstance(x, Predicate):
        return Predicate(x.name, [subst(theta, t) for t in x.terms])
    if isinstance(x, list):
        return [subst(theta, t) for t in x]
    return x

var_counter = 0
def standardize_variables(rule: Rule) -> Rule:
    global var_counter
    var_counter += 1
    suffix = f"_{var_counter}"

    def rename(term):
        if isinstance(term, Var): return Var(str(term.name) + suffix)
        if isinstance(term, Const): return term
        if isinstance(term, NativeMath):
            return NativeMath(term.func, [rename(t) for t in term.terms])
        if isinstance(term, Predicate):
            return Predicate(term.name, [rename(t) for t in term.terms])
        if isinstance(term, list): return [rename(t) for t in term]
        return term

    return Rule(rename(rule.premises), rename(rule.conclusion))

def _decode_cell_var_name(var_name):
    parts = str(var_name).split("_")
    if len(parts) != 3 or parts[0] != "v":
        return None
    try:
        row = int(parts[1]) - 1
        col = int(parts[2]) - 1
    except ValueError:
        return None
    if row < 0 or col < 0:
        return None
    return (row, col)


def _extract_goal_cell(goal):
    if not isinstance(goal, Predicate):
        return None
    if goal.name != "Val" or len(goal.terms) < 2:
        return None

    row_term, col_term = goal.terms[0], goal.terms[1]
    if not isinstance(row_term, Const) or not isinstance(col_term, Const):
        return None

    return (int(row_term.name) - 1, int(col_term.name) - 1)


def _extract_new_cell_bindings(theta_before, theta_after):
    if theta_before is None or theta_after is None:
        return []

    bindings = []
    for var, value_term in theta_after.items():
        if var in theta_before:
            continue
        if not isinstance(var, Var):
            continue

        cell = _decode_cell_var_name(var.name)
        if cell is None:
            continue

        resolved_value = subst(theta_after, value_term)
        if not isinstance(resolved_value, Const):
            continue

        row, col = cell
        bindings.append(
            {
                "var_name": var.name,
                "row": row,
                "col": col,
                "value": int(resolved_value.name),
            }
        )
    return bindings

def fol_bc_or(
    kb: list[Rule],
    goal,
    theta: Theta,
    should_cancel=None,
    trace_callback=None,
    trace_state=None,
    depth=0,
) -> Iterator[Theta]:
    if should_cancel is not None and should_cancel():
        raise RuntimeError("Solve cancelled")

    _emit_trace(
        trace_callback,
        trace_state,
        "progress",
        "BC expanding goal {}".format(goal),
        {
            "phase": "goal_expand",
            "depth": depth,
            "goal": str(goal),
        },
    )

    for rule in kb:
        if should_cancel is not None and should_cancel():
            raise RuntimeError("Solve cancelled")
        # OPTIMIZATION: If it's a pure fact with no premises, assume it has no variables 
        # (True for our Val facts) and skip the expensive standardization.
        if len(rule.premises) == 0:
            rule_std = rule
        else:
            rule_std = standardize_variables(rule)
        theta_prime = unify(rule_std.conclusion, goal, theta)
        if theta_prime is None:
            continue

        _emit_trace(
            trace_callback,
            trace_state,
            "progress",
            "BC matched rule for goal {}".format(goal),
            {
                "phase": "rule_match_success",
                "depth": depth,
                "goal": str(goal),
                "conclusion": str(rule_std.conclusion),
            },
        )

        # Emit assignment candidates for GUI animation.
        new_bindings = _extract_new_cell_bindings(theta, theta_prime)
        for binding in new_bindings:
            _emit_trace(
                trace_callback,
                trace_state,
                "assign",
                "BC try {} at ({}, {})".format(binding["value"], binding["row"] + 1, binding["col"] + 1),
                {
                    "phase": "assign_candidate",
                    "depth": depth,
                    "row": binding["row"],
                    "col": binding["col"],
                    "value": binding["value"],
                    "var_name": binding["var_name"],
                },
            )

        produced_solution = False
        for next_theta in fol_bc_and(
            kb,
            rule_std.premises,
            theta_prime,
            should_cancel=should_cancel,
            trace_callback=trace_callback,
            trace_state=trace_state,
            depth=depth + 1,
        ):
            produced_solution = True
            yield next_theta

        if not produced_solution and new_bindings:
            for binding in reversed(new_bindings):
                _emit_trace(
                    trace_callback,
                    trace_state,
                    "backtrack",
                    "BC backtrack from ({}, {})".format(binding["row"] + 1, binding["col"] + 1),
                    {
                        "phase": "backtrack_assignment",
                        "depth": depth,
                        "row": binding["row"],
                        "col": binding["col"],
                        "value": binding["value"],
                        "var_name": binding["var_name"],
                    },
                )

def fol_bc_and(
    kb: list[Rule],
    goals: list[Predicate],
    theta: Theta | None,
    should_cancel=None,
    trace_callback=None,
    trace_state=None,
    depth=0,
) -> Iterator[Theta]:
    if should_cancel is not None and should_cancel():
        raise RuntimeError("Solve cancelled")
    if theta is None:
        _emit_trace(
            trace_callback,
            trace_state,
            "progress",
            "BC branch ended due to empty substitution.",
            {"phase": "branch_end", "depth": depth, "reason": "theta_none"},
        )
        return
    elif len(goals) == 0:
        yield theta
    else:
        first, rest = goals[0], goals[1:]
        first_subst = subst(theta, first)

        _emit_trace(
            trace_callback,
            trace_state,
            "progress",
            "BC evaluating goal {}".format(first_subst),
            {
                "phase": "goal_evaluate",
                "depth": depth,
                "goal": str(first_subst),
                "remaining_goals": len(rest),
            },
        )

        emit_cell_expand = True
        if trace_state is not None:
            emit_cell_expand = bool(trace_state.get("emit_cell_expand_events", False))

        if emit_cell_expand:
            cell = _extract_goal_cell(first_subst)
            if cell is not None:
                row, col = cell
                _emit_trace(
                    trace_callback,
                    trace_state,
                    "node_expanded",
                    "BC explore cell ({}, {})".format(row + 1, col + 1),
                    {
                        "phase": "cell_expand",
                        "depth": depth,
                        "row": row,
                        "col": col,
                        "goal": str(first_subst),
                        "remaining_goals": len(rest),
                    },
                )
        
        # Intercept and immediately evaluate NativeMath variables once grounded
        if isinstance(first_subst, NativeMath):
            if all(isinstance(t, Const) for t in first_subst.terms):
                args = [t.name for t in first_subst.terms]
                passed = first_subst.func(*args)
                _emit_trace(
                    trace_callback,
                    trace_state,
                    "progress",
                    "BC NativeMath {}.".format("passed" if passed else "failed"),
                    {
                        "phase": "native_math",
                        "depth": depth,
                        "result": passed,
                        "args": args,
                    },
                )
                if passed:
                    yield from fol_bc_and(
                        kb,
                        rest,
                        theta,
                        should_cancel=should_cancel,
                        trace_callback=trace_callback,
                        trace_state=trace_state,
                        depth=depth + 1,
                    )
                else:
                    _emit_trace(
                        trace_callback,
                        trace_state,
                        "progress",
                        "BC backtrack after NativeMath failure.",
                        {"phase": "backtrack_summary", "depth": depth, "reason": "native_math_failed"},
                    )
            else:
                _emit_trace(
                    trace_callback,
                    trace_state,
                    "progress",
                    "BC NativeMath has unbound variables.",
                    {"phase": "native_math_unbound", "depth": depth, "goal": str(first_subst)},
                )
                raise RuntimeError(f"NativeMath encountered unbound variables: {first_subst}")
        else:
            found_next = False
            for theta_prime in fol_bc_or(
                kb,
                first_subst,
                theta,
                should_cancel=should_cancel,
                trace_callback=trace_callback,
                trace_state=trace_state,
                depth=depth + 1,
            ):
                for theta_double_prime in fol_bc_and(
                    kb,
                    rest,
                    theta_prime,
                    should_cancel=should_cancel,
                    trace_callback=trace_callback,
                    trace_state=trace_state,
                    depth=depth + 1,
                ):
                    found_next = True
                    yield theta_double_prime

            if not found_next:
                _emit_trace(
                    trace_callback,
                    trace_state,
                    "progress",
                    "BC backtrack: no rule could satisfy goal {}".format(first_subst),
                    {
                        "phase": "backtrack_summary",
                        "depth": depth,
                        "goal": str(first_subst),
                    },
                )

def load_and_solve_futoshiki(file_name: str) -> tuple[list[Rule], list[Predicate], list[Var], int]:
    with open(file_name, 'r') as f:
        file_content = f.read()
    lines = [line.strip() for line in file_content.strip().split('\n')]
    data = [line for line in lines if line and not line.startswith('#')]
    
    size = int(data[0])
    kb = []
    givens = {}
    less_h, greater_h, less_v, greater_v = set(), set(), set(), set()

    grid_start = 1
    for i in range(1, size + 1):
        row_vals = [int(x.strip()) for x in data[grid_start + i - 1].split(',')]
        for j, val in enumerate(row_vals, start=1):
            if val > 0: givens[(i, j)] = val

    horiz_start = grid_start + size
    for i in range(1, size + 1):
        row_vals = [int(x.strip()) for x in data[horiz_start + i - 1].split(',')]
        for j, val in enumerate(row_vals, start=1):
            if val == 1: less_h.add((i, j))
            elif val == -1: greater_h.add((i, j))

    vert_start = horiz_start + size
    for i in range(1, size): 
        row_vals = [int(x.strip()) for x in data[vert_start + i - 1].split(',')]
        for j, val in enumerate(row_vals, start=1):
            if val == 1: less_v.add((i, j))
            elif val == -1: greater_v.add((i, j))

    # base Facts: domain values [1...N]
    for i in range(1, size + 1):
        kb.append(Rule([], Predicate("Domain", [Const(i)])))

    # Keep track of givens per row and column
    given_rows = {i: set() for i in range(1, size + 1)}
    given_cols = {i: set() for i in range(1, size + 1)}
    for (r, c), val in givens.items():
        given_rows[r].add(val)
        given_cols[c].add(val)

    # define Val(i, j, v) purely as base facts
    for r in range(1, size + 1):
        for c in range(1, size + 1):
            if (r, c) in givens:
                # Given fact
                kb.append(Rule([], Predicate("Val", [Const(r), Const(c), Const(givens[(r, c)])])))
            else:
                for val in range(1, size + 1):
                    # OPTIMIZATION: Only add the fact if it doesn't immediately violate a given row/col
                    if val not in given_rows[r] and val not in given_cols[c]:
                        kb.append(Rule([], Predicate("Val", [Const(r), Const(c), Const(val)])))


    # construct SLD query goals with reordering
    query_goals = []
    variables = []
    
    for r in range(size, 0, -1):
        for c in range(size, 0, -1):
            v_rc = Var(f"v_{r}_{c}")
            variables.append(v_rc)
            
            # 1. Query Val
            query_goals.append(Predicate("Val", [Const(r), Const(c), v_rc]))
            
            # Row Uniqueness (checking against columns > c)
            for c_prev in range(c + 1, size + 1):
                v_prev = Var(f"v_{r}_{c_prev}")
                query_goals.append(NativeMath(lambda x, y: x != y, [v_rc, v_prev]))
                
            # Column Uniqueness (checking against rows > r)
            for r_prev in range(r + 1, size + 1):
                v_prev = Var(f"v_{r_prev}_{c}")
                query_goals.append(NativeMath(lambda x, y: x != y, [v_rc, v_prev]))
            
            # Horizontal Check (right neighbor: r, c+1 is already bound in this reverse loop)
            if (r, c) in less_h: # v_r_c < v_r_c+1
                v_right = Var(f"v_{r}_{c+1}")
                query_goals.append(NativeMath(lambda left, right: left < right, [v_rc, v_right]))
            elif (r, c) in greater_h: # v_r_c > v_r_c+1
                v_right = Var(f"v_{r}_{c+1}")
                query_goals.append(NativeMath(lambda left, right: left > right, [v_rc, v_right]))
                
            # Vertical Check (bottom neighbor: r+1, c is already bound in this reverse loop)
            if (r, c) in less_v: # v_r_c < v_r+1_c
                v_bottom = Var(f"v_{r+1}_{c}")
                query_goals.append(NativeMath(lambda top, bottom: top < bottom, [v_rc, v_bottom]))
            elif (r, c) in greater_v: # v_r_c > v_r+1_c
                v_bottom = Var(f"v_{r+1}_{c}")
                query_goals.append(NativeMath(lambda top, bottom: top > bottom, [v_rc, v_bottom]))

    return kb, query_goals, variables, size

def bc_solve(input_file: str) -> tuple[list[list[int]] | None, float]:
    time_start = time.perf_counter()
    kb, query_goals, variables, size = load_and_solve_futoshiki(input_file)
    
    solution = None
    for theta in fol_bc_and(kb, query_goals, {}):
        solution = theta
        break

    time_taken = time.perf_counter() - time_start

    if solution is not None:
        grid = [[0 for _ in range(size)] for _ in range(size)]
        for v in variables:
            cell_info = _decode_cell_var_name(v.name)
            if cell_info is not None:
                row, col = cell_info
                resolved_value = subst(solution, v)
                if isinstance(resolved_value, Const):
                    grid[row][col] = int(resolved_value.name)
        return grid, time_taken
    else:
        return None, time_taken
    