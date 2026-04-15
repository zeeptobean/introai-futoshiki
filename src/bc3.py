# backward chaining
from typing import TypeAlias, TypeVar
from collections.abc import Iterator
import time

try:
    from myfol import *
except ImportError:  # pragma: no cover
    from src.myfol import *

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

# ==========================================
# 3. Backward Chaining Algorithm
# ==========================================

def fol_bc_or(kb: list[Rule], goal, theta: Theta, should_cancel=None) -> Iterator[Theta]:
    if should_cancel is not None and should_cancel():
        raise RuntimeError("Solve cancelled")
    for rule in kb:
        if should_cancel is not None and should_cancel():
            raise RuntimeError("Solve cancelled")
        rule_std = standardize_variables(rule)
        theta_prime = unify(rule_std.conclusion, goal, theta)
        if theta_prime is not None:
            for next_theta in fol_bc_and(kb, rule_std.premises, theta_prime, should_cancel=should_cancel):
                yield next_theta

def fol_bc_and(kb: list[Rule], goals: list[Predicate], theta: Theta | None, should_cancel=None) -> Iterator[Theta]:
    if should_cancel is not None and should_cancel():
        raise RuntimeError("Solve cancelled")
    if theta is None: return
    elif len(goals) == 0: yield theta
    else:
        first, rest = goals[0], goals[1:]
        first_subst = subst(theta, first)
        
        # Intercept and immediately evaluate NativeMath variables once grounded
        if isinstance(first_subst, NativeMath):
            if all(isinstance(t, Const) for t in first_subst.terms):
                args = [t.name for t in first_subst.terms]
                if first_subst.func(*args):
                    yield from fol_bc_and(kb, rest, theta, should_cancel=should_cancel)
            else:
                raise RuntimeError(f"NativeMath encountered unbound variables: {first_subst}")
        else:
            for theta_prime in fol_bc_or(kb, first_subst, theta, should_cancel=should_cancel):
                for theta_double_prime in fol_bc_and(kb, rest, theta_prime, should_cancel=should_cancel):
                    yield theta_double_prime

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

    # define Val(i, j, v) for the Interpreter
    for r in range(1, size + 1):
        for c in range(1, size + 1):
            if (r, c) in givens:
                # If given, Val is an absolute fact.
                kb.append(Rule([], Predicate("Val", [Const(r), Const(c), Const(givens[(r, c)])])))
            else:
                # If blank, Val draws from the Domain.
                # Rule: Domain(v) => Val(r, c, v)
                kb.append(Rule([Predicate("Domain", [Var("v")])], Predicate("Val", [Const(r), Const(c), Var("v")])))


    # construct SLD query goals for each cell and constraints
    query_goals = []
    variables = []
    
    for r in range(1, size + 1):
        for c in range(1, size + 1):
            v_rc = Var(f"v_{r}_{c}")
            variables.append(v_rc)
            
            # 1. Query Val(i, j, ?) for each cell
            query_goals.append(Predicate("Val", [Const(r), Const(c), v_rc]))
            
            # Row Uniqueness 
            for c_prev in range(1, c):
                v_prev = Var(f"v_{r}_{c_prev}")
                query_goals.append(NativeMath(lambda x, y: x != y, [v_rc, v_prev]))
                
            # Column Uniqueness
            for r_prev in range(1, r):
                v_prev = Var(f"v_{r_prev}_{c}")
                query_goals.append(NativeMath(lambda x, y: x != y, [v_rc, v_prev]))
            
            # Horizontal Check (left neighbor: r, c-1)
            if (r, c - 1) in less_h:
                v_left = Var(f"v_{r}_{c-1}")
                query_goals.append(NativeMath(lambda left, right: left < right, [v_left, v_rc]))
            elif (r, c - 1) in greater_h:
                v_left = Var(f"v_{r}_{c-1}")
                query_goals.append(NativeMath(lambda left, right: left > right, [v_left, v_rc]))
            
            # Vertical Check (top neighbor: r-1, c)
            if (r - 1, c) in less_v:
                v_top = Var(f"v_{r-1}_{c}")
                query_goals.append(NativeMath(lambda top, bottom: top < bottom, [v_top, v_rc]))
            elif (r - 1, c) in greater_v:
                v_top = Var(f"v_{r-1}_{c}")
                query_goals.append(NativeMath(lambda top, bottom: top > bottom, [v_top, v_rc]))

    return kb, query_goals, variables, size

def main():
    time_start = time.perf_counter()
    
    kb, query_goals, variables, size = load_and_solve_futoshiki("input-01.txt")
    
    solutions_found = 0
    for solution in fol_bc_and(kb, query_goals, {}):
        solutions_found += 1
        print(f"\nSolution {solutions_found}:")
        
        # Structure the flat output back into a grid map
        grid = {}
        for v in variables:
            grid[v.name] = subst(solution, v).name
            
        for r in range(1, size + 1):
            row = [grid[f"v_{r}_{c}"] for c in range(1, size + 1)]
            print("  " + " ".join(map(str, row)))
            
        break # Removes this line to generate ALL possible solutions.

    time_running = time.perf_counter() - time_start
    print(f"\nTotal time taken: {time_running:.4f} seconds")

if __name__ == "__main__":
    main()