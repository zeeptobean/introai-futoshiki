# forward chaining FOL, with optimizations
import time

from myfol import *


def _emit_trace(trace_callback, action, step_index, message, metadata=None, board=None, focus_cell=None):
    if trace_callback is None:
        return
    payload = {
        "action": action,
        "step_index": step_index,
        "message": message,
        "metadata": metadata or {},
    }
    if board is not None:
        payload["board"] = board
    if focus_cell is not None:
        payload["focus_cell"] = focus_cell
    trace_callback(payload)


def _next_step(trace_state):
    trace_state["step_index"] = int(trace_state.get("step_index", 0)) + 1
    return trace_state["step_index"]


def _board_from_kb(kb, N):
    board = [[0 for _ in range(N)] for _ in range(N)]
    for fact in kb.get("Val", set()):
        r = fact.terms[0].name - 1
        c = fact.terms[1].name - 1
        v = fact.terms[2].name
        if 0 <= r < N and 0 <= c < N:
            board[r][c] = v
    return board


def _theta_to_payload(theta):
    payload = {}
    for key, value in theta.items():
        payload[str(key)] = str(value)
    return payload

def substitute(theta, predicate):
    new_terms = []
    for term in predicate.terms:
        if isinstance(term, Var) and term in theta:
            val = theta[term]
            while isinstance(val, Var) and val in theta:
                val = theta[val]
            new_terms.append(val)
        else:
            new_terms.append(term)
    return Predicate(predicate.name, new_terms)

def is_consistent(kb, N):
    """
    Checks the KB for logical contradictions.
    Returns False if the state is invalid, True otherwise.
    """
    vals = kb.get("Val", set())
    not_vals = kb.get("NotVal", set())

    #Check for multiple different values in the same cell
    cell_vals = {}
    for val_fact in vals:
        i, j, v = val_fact.terms[0].name, val_fact.terms[1].name, val_fact.terms[2].name
        if (i, j) in cell_vals and cell_vals[(i, j)] != v:
            return False # Contradiction: Cell has multiple values
        cell_vals[(i, j)] = v

    #Check if a cell has both Val(i,j,v) and NotVal(i,j,v)
    for val_fact in vals:
        if Predicate("NotVal", val_fact.terms) in not_vals:
            return False # Contradiction: Cell is both v and Not v

    #Check for cells that have 0 possible values left
    not_val_counts = {}
    for nv_fact in not_vals:
        i, j = nv_fact.terms[0].name, nv_fact.terms[1].name
        not_val_counts[(i, j)] = not_val_counts.get((i, j), 0) + 1
        
    for count in not_val_counts.values():
        if count >= N:
            return False # Contradiction: All N possibilities eliminated for a cell

    return True

def match_premises(premises, kb, theta, should_cancel=None):
    if should_cancel is not None and should_cancel():
        raise RuntimeError("Solve cancelled")
    if not premises:
        yield theta
        return
    
    first_premise = premises[0]
    rest_premises = premises[1:]
    
    # Intercept Native Math
    if isinstance(first_premise, NativeMath):
        bound_terms = []
        for term in first_premise.terms:
            val = term
            while isinstance(val, Var) and val in theta:
                val = theta[val]
            bound_terms.append(val)
        
        if all(isinstance(t, Const) for t in bound_terms):
            raw_values = [t.name for t in bound_terms]
            if first_premise.func(*raw_values):
                yield from match_premises(rest_premises, kb, theta, should_cancel=should_cancel)
        return 

    # --- OPTIMIZATION: Hash Map Lookup ---
    # Only try to unify with facts that share the exact same predicate name.
    # If looking for a "Val", only loop through known "Val" facts!
    for fact in kb.get(first_premise.name, set()):
        if should_cancel is not None and should_cancel():
            raise RuntimeError("Solve cancelled")
        theta_new = unify(first_premise, fact, theta.copy())
        if theta_new is not None:
            yield from match_premises(rest_premises, kb, theta_new, should_cancel=should_cancel)

def fol_fc(kb, rules, should_cancel=None, trace_callback=None, trace_state=None):
    new_facts_found = True
    iteration = 1
    if trace_state is None:
        trace_state = {"step_index": 0}

    while new_facts_found:
        if should_cancel is not None and should_cancel():
            raise RuntimeError("Solve cancelled")

        _emit_trace(
            trace_callback,
            "progress",
            _next_step(trace_state),
            "FC iteration {} started".format(iteration),
            {
                "phase": "iteration_started",
                "iteration": iteration,
                "facts_total": sum(len(v) for v in kb.values()),
                "val_facts": len(kb.get("Val", set())),
                "not_val_facts": len(kb.get("NotVal", set())),
            },
        )

        new_facts_found = False
        new_val_count = 0
        new_not_val_count = 0

        for rule_idx, rule in enumerate(rules):
            if should_cancel is not None and should_cancel():
                raise RuntimeError("Solve cancelled")
            for theta in match_premises(rule.premises, kb, {}, should_cancel=should_cancel):
                q_prime = substitute(theta, rule.conclusion)
                category = kb.setdefault(q_prime.name, set())
                if q_prime not in category:
                    if q_prime.name == "Val":
                        r = q_prime.terms[0].name
                        c = q_prime.terms[1].name
                        v = q_prime.terms[2].name
                        is_occupied = any(
                            f.terms[0].name == r and f.terms[1].name == c and f.terms[2].name != v
                            for f in kb.get("Val", set())
                        )
                        if is_occupied:
                            category.add(q_prime)
                            return kb

                    category.add(q_prime)
                    new_facts_found = True

                    if q_prime.name == "Val":
                        new_val_count += 1
                        _emit_trace(
                            trace_callback,
                            "assign",
                            _next_step(trace_state),
                            "FC derived Val({}, {}, {})".format(
                                q_prime.terms[0].name,
                                q_prime.terms[1].name,
                                q_prime.terms[2].name,
                            ),
                            {
                                "phase": "derived_val",
                                "iteration": iteration,
                                "rule_index": rule_idx,
                                "row": q_prime.terms[0].name - 1,
                                "col": q_prime.terms[1].name - 1,
                                "value": q_prime.terms[2].name,
                                "fact": str(q_prime),
                                "theta": _theta_to_payload(theta),
                            },
                        )
                    elif q_prime.name == "NotVal":
                        new_not_val_count += 1

        _emit_trace(
            trace_callback,
            "progress",
            _next_step(trace_state),
            "FC iteration {} finished".format(iteration),
            {
                "phase": "iteration_done",
                "iteration": iteration,
                "new_val_facts": new_val_count,
                "new_not_val_facts": new_not_val_count,
                "facts_total": sum(len(v) for v in kb.values()),
                "val_facts": len(kb.get("Val", set())),
                "not_val_facts": len(kb.get("NotVal", set())),
            },
        )
        iteration += 1

    return kb

i, j, k = Var("i"), Var("j"), Var("k")
v, v1, v2 = Var("v"), Var("v1"), Var("v2")
i_next, j_next = Var("i_next"), Var("j_next")

base_rules = [
    # ==========================================
    # 1. Base Clues & Sudoku Rules
    # ==========================================

    # Rule 1: Given clues become actual Values
    Rule(
        premises=[Predicate("Given", [i, j, v])], 
        conclusion=Predicate("Val", [i, j, v])
    ),

    # Rule 2: Row Uniqueness 
    Rule(
        premises=[
            Predicate("Val", [i, j, v]),
            Predicate("Col", [k]), 
            NativeMath(lambda col_j, col_k: col_j != col_k, [j, k])
        ],
        conclusion=Predicate("NotVal", [i, k, v])
    ),

    # Rule 3: Column Uniqueness
    Rule(
        premises=[
            Predicate("Val", [i, j, v]),
            Predicate("Row", [k]), 
            NativeMath(lambda row_i, row_k: row_i != row_k, [i, k])
        ],
        conclusion=Predicate("NotVal", [k, j, v])
    ),

    # Cell uniqueness 
    Rule(
        premises=[
            Predicate("Val", [i, j, v1]),
            Predicate("Num", [v2]),
            NativeMath(lambda val1, val2: val1 != val2, [v1, v2]) 
        ],
        conclusion=Predicate("NotVal", [i, j, v2])
    ),

    # ==========================================
    # 2. Horizontal Constraints (< and >)
    # ==========================================

    # LessH (Forward): If (i,j) < (i,j+1) and we know (i,j) is v1.
    # Eliminate any v2 that is <= v1 for the right cell.
    Rule(
        premises=[
            Predicate("Val", [i, j, v1]),
            Predicate("LessH", [i, j]),
            Predicate("Col", [j_next]),
            NativeMath(lambda c, n_c: c + 1 == n_c, [j, j_next]),
            Predicate("Num", [v2]),
            NativeMath(lambda val1, val2: val2 <= val1, [v1, v2]) 
        ],
        conclusion=Predicate("NotVal", [i, j_next, v2])
    ),

    # LessH (Backward): If (i,j) < (i,j+1) and we know (i,j+1) is v2.
    # Eliminate any v1 that is >= v2 for the left cell.
    Rule(
        premises=[
            Predicate("Val", [i, j_next, v2]),
            Predicate("LessH", [i, j]),
            Predicate("Col", [j]),
            NativeMath(lambda c, n_c: c + 1 == n_c, [j, j_next]),
            Predicate("Num", [v1]),
            NativeMath(lambda val1, val2: val1 >= val2, [v1, v2]) 
        ],
        conclusion=Predicate("NotVal", [i, j, v1])
    ),

    # GreaterH (Forward): If (i,j) > (i,j+1) and we know (i,j) is v1.
    # Eliminate any v2 that is >= v1 for the right cell.
    Rule(
        premises=[
            Predicate("Val", [i, j, v1]),
            Predicate("GreaterH", [i, j]),
            Predicate("Col", [j_next]),
            NativeMath(lambda c, n_c: c + 1 == n_c, [j, j_next]),
            Predicate("Num", [v2]),
            NativeMath(lambda val1, val2: val2 >= val1, [v1, v2]) 
        ],
        conclusion=Predicate("NotVal", [i, j_next, v2])
    ),

    # GreaterH (Backward): If (i,j) > (i,j+1) and we know (i,j+1) is v2.
    # Eliminate any v1 that is <= v2 for the left cell.
    Rule(
        premises=[
            Predicate("Val", [i, j_next, v2]),
            Predicate("GreaterH", [i, j]),
            Predicate("Col", [j]),
            NativeMath(lambda c, n_c: c + 1 == n_c, [j, j_next]),
            Predicate("Num", [v1]),
            NativeMath(lambda val1, val2: val1 <= val2, [v1, v2]) 
        ],
        conclusion=Predicate("NotVal", [i, j, v1])
    ),

    # ==========================================
    # 3. Vertical Constraints (^ and v)
    # ==========================================

    # LessV (Forward): If (i,j) < (i+1,j) and we know the top value is v1.
    # Eliminate any v2 that is <= v1 for the bottom cell.
    Rule(
        premises=[
            Predicate("Val", [i, j, v1]),
            Predicate("LessV", [i, j]),
            Predicate("Row", [i_next]),
            NativeMath(lambda r, n_r: r + 1 == n_r, [i, i_next]),
            Predicate("Num", [v2]),
            NativeMath(lambda val1, val2: val2 <= val1, [v1, v2]) 
        ],
        conclusion=Predicate("NotVal", [i_next, j, v2])
    ),

    # LessV (Backward): If (i,j) < (i+1,j) and we know the bottom value is v2.
    # Eliminate any v1 that is >= v2 for the top cell.
    Rule(
        premises=[
            Predicate("Val", [i_next, j, v2]),
            Predicate("LessV", [i, j]),
            Predicate("Row", [i]),
            NativeMath(lambda r, n_r: r + 1 == n_r, [i, i_next]),
            Predicate("Num", [v1]),
            NativeMath(lambda val1, val2: val1 >= val2, [v1, v2]) 
        ],
        conclusion=Predicate("NotVal", [i, j, v1])
    ),

    # GreaterV (Forward): If (i,j) > (i+1,j) and we know the top value is v1.
    # Eliminate any v2 that is >= v1 for the bottom cell.
    Rule(
        premises=[
            Predicate("Val", [i, j, v1]),
            Predicate("GreaterV", [i, j]),
            Predicate("Row", [i_next]),
            NativeMath(lambda r, n_r: r + 1 == n_r, [i, i_next]),
            Predicate("Num", [v2]),
            NativeMath(lambda val1, val2: val2 >= val1, [v1, v2]) 
        ],
        conclusion=Predicate("NotVal", [i_next, j, v2])
    ),

    # GreaterV (Backward): If (i,j) > (i+1,j) and we know the bottom value is v2.
    # Eliminate any v1 that is <= v2 for the top cell.
    Rule(
        premises=[
            Predicate("Val", [i_next, j, v2]),
            Predicate("GreaterV", [i, j]),
            Predicate("Row", [i]),
            NativeMath(lambda r, n_r: r + 1 == n_r, [i, i_next]),
            Predicate("Num", [v1]),
            NativeMath(lambda val1, val2: val1 <= val2, [v1, v2]) 
        ],
        conclusion=Predicate("NotVal", [i, j, v1])
    )
]

def get_degree(r, c, kb):
    """Calculates how many inequality constraints involve cell (r, c)"""
    degree = 0
    for fact in kb.get("LessH", set()):
        if (fact.terms[0].name == r and fact.terms[1].name == c) or \
           (fact.terms[0].name == r and fact.terms[1].name == c - 1): degree += 1
    for fact in kb.get("GreaterH", set()):
        if (fact.terms[0].name == r and fact.terms[1].name == c) or \
           (fact.terms[0].name == r and fact.terms[1].name == c - 1): degree += 1
    for fact in kb.get("LessV", set()):
        if (fact.terms[0].name == r and fact.terms[1].name == c) or \
           (fact.terms[0].name == r - 1 and fact.terms[1].name == c): degree += 1
    for fact in kb.get("GreaterV", set()):
        if (fact.terms[0].name == r and fact.terms[1].name == c) or \
           (fact.terms[0].name == r - 1 and fact.terms[1].name == c): degree += 1
    return degree

def solve_with_backtracking(kb, rules, N, depth=0, trace_callback=None, should_cancel=None, trace_state=None):
    """
    Recursively solves the puzzle using Forward Chaining + Backtracking.
    """
    if should_cancel is not None and should_cancel():
        raise RuntimeError("Solve cancelled")
    if trace_state is None:
        trace_state = {"step_index": 0}

    # Propagate constraints using Forward Chaining
    kb = fol_fc(kb, rules, should_cancel=should_cancel, trace_callback=trace_callback, trace_state=trace_state)

    # Check if the newly propagated KB is valid
    if not is_consistent(kb, N):
        _emit_trace(
            trace_callback,
            "progress",
            _next_step(trace_state),
            "Backtrack: contradiction at depth {}".format(depth),
            {"phase": "dead_end", "depth": depth},
            board=_board_from_kb(kb, N),
        )
        return None

    # Check if solved (all N*N cells have a value)
    vals = kb.get("Val", set())
    if len(vals) == N * N:
        _emit_trace(
            trace_callback,
            "progress",
            _next_step(trace_state),
            "Solved at depth {}".format(depth),
            {"phase": "solved_node", "depth": depth},
            board=_board_from_kb(kb, N),
        )
        return kb

    # MRV Heuristic: Find unassigned cell with smallest domain
    assigned_cells = {(f.terms[0].name, f.terms[1].name) for f in vals}
    not_vals = kb.get("NotVal", set())

    # OPTIMIZATION: Pre-group NotVal facts for O(1) lookups
    eliminated_by_cell = {}
    for nv in not_vals:
        r_nv, c_nv, v_nv = nv.terms[0].name, nv.terms[1].name, nv.terms[2].name
        eliminated_by_cell.setdefault((r_nv, c_nv), set()).add(v_nv)
    
    best_cell = None
    best_domain = []
    best_domain_size = N + 1
    best_degree = -1

    for r in range(1, N + 1):
        for c in range(1, N + 1):
            if (r, c) not in assigned_cells:
                # Calculate remaining possible values for this cell
                eliminated = eliminated_by_cell.get((r, c), set())
                domain = [v for v in range(1, N + 1) if v not in eliminated]

                if len(domain) == 0:
                    _emit_trace(
                        trace_callback,
                        "progress",
                        _next_step(trace_state),
                        "Backtrack: empty domain at ({}, {})".format(r, c),
                        {"phase": "dead_end", "depth": depth, "row": r - 1, "col": c - 1},
                        board=_board_from_kb(kb, N),
                        focus_cell=(r - 1, c - 1),
                    )
                    return None 

                if len(domain) < best_domain_size:
                    best_domain_size = len(domain)
                    best_cell = (r, c)
                    best_domain = domain
                elif len(domain) == best_domain_size:
                    cell_degree = get_degree(r, c, kb)
                    if cell_degree > best_degree:
                        best_cell = (r, c)
                        best_domain = domain
                        best_degree = cell_degree

    if not best_cell:
        return None

    r, c = best_cell
    _emit_trace(
        trace_callback,
        "progress",
        _next_step(trace_state),
        "Select cell ({}, {}) with domain {}".format(r, c, best_domain),
        {
            "phase": "select_cell",
            "depth": depth,
            "row": r - 1,
            "col": c - 1,
            "domain": list(best_domain),
            "domain_size": len(best_domain),
        },
        board=_board_from_kb(kb, N),
        focus_cell=(r - 1, c - 1),
    )
    for v in best_domain:
        new_kb = {k: set(v_set) for k, v_set in kb.items()}
        
        # Inject our guess as a new Given/Val fact
        add_fact(new_kb, Predicate("Val", [Const(r), Const(c), Const(v)]))

        _emit_trace(
            trace_callback,
            "assign",
            _next_step(trace_state),
            "Try {} at ({}, {})".format(v, r, c),
            {
                "phase": "try_value",
                "depth": depth,
                "row": r - 1,
                "col": c - 1,
                "value": v,
            },
            board=_board_from_kb(new_kb, N),
            focus_cell=(r - 1, c - 1),
        )
        
        result_kb = solve_with_backtracking(new_kb, rules, N, depth + 1, trace_callback=trace_callback, should_cancel=should_cancel, trace_state=trace_state)
        if result_kb is not None:
            _emit_trace(
                trace_callback,
                "progress",
                _next_step(trace_state),
                "Backtrack from {} at ({}, {})".format(v, r, c),
                {
                    "phase": "backtrack",
                    "depth": depth,
                    "row": r - 1,
                    "col": c - 1,
                    "value": v,
                },
                board=_board_from_kb(kb, N),
                focus_cell=(r - 1, c - 1),
            )
            return result_kb

    return None

def add_fact(kb, fact):
    """Helper to safely add a fact to the dictionary-based KB."""
    kb.setdefault(fact.name, set()).add(fact)

def generate_boundary_rules(grid_size):
    """
    If A < B, A cannot be the maximum number, and B cannot be 1.
    These rules do NOT require a known Val() to fire!
    """
    i, j = Var("i"), Var("j")
    i_next, j_next = Var("i_next"), Var("j_next")
    N = Const(grid_size)
    ONE = Const(1)

    return [
        # LessH (Left < Right)
        Rule([Predicate("LessH", [i, j])], Predicate("NotVal", [i, j, N])),
        Rule([
            Predicate("LessH", [i, j]), 
            Predicate("Col", [j_next]), 
            NativeMath(lambda c, nc: c + 1 == nc, [j, j_next])
        ], Predicate("NotVal", [i, j_next, ONE])),
        
        # GreaterH (Left > Right)
        Rule([Predicate("GreaterH", [i, j])], Predicate("NotVal", [i, j, ONE])),
        Rule([
            Predicate("GreaterH", [i, j]), 
            Predicate("Col", [j_next]), 
            NativeMath(lambda c, nc: c + 1 == nc, [j, j_next])
        ], Predicate("NotVal", [i, j_next, N])),

        # LessV (Top < Bottom)
        Rule([Predicate("LessV", [i, j])], Predicate("NotVal", [i, j, N])),
        Rule([
            Predicate("LessV", [i, j]), 
            Predicate("Row", [i_next]), 
            NativeMath(lambda r, nr: r + 1 == nr, [i, i_next])
        ], Predicate("NotVal", [i_next, j, ONE])),

        # GreaterV (Top > Bottom)
        Rule([Predicate("GreaterV", [i, j])], Predicate("NotVal", [i, j, ONE])),
        Rule([
            Predicate("GreaterV", [i, j]), 
            Predicate("Row", [i_next]), 
            NativeMath(lambda r, nr: r + 1 == nr, [i, i_next])
        ], Predicate("NotVal", [i_next, j, N]))
    ]

def generate_hidden_single_rule(grid_size):
    """
    If a cell has N-1 distinct NotVal facts, it must be the Nth number.
    """
    i = Var("i")
    j = Var("j")
    target_v = Var("v") # The number we are trying to deduce
    
    # 1. Generate N-1 distinct variable objects (e.g., v_0, v_1, v_2)
    other_vars = [Var(f"v_{x}") for x in range(grid_size - 1)]
    
    # 2. Start building the premises
    premises = [Predicate("Row", [i]), Predicate("Col", [j])]
    
    # 3. Bind all variables to valid Numbers
    for var in other_vars:
        premises.append(Predicate("Num", [var]))
    premises.append(Predicate("Num", [target_v]))
    
    # 4. Native Math: Ensure all N variables are completely unique.
    # We use Python's *args to allow the lambda to accept any number of arguments,
    # then check if the length of the Set equals the grid size.
    all_vars = other_vars + [target_v]
    premises.append(
        NativeMath(lambda *args: len(set(args)) == grid_size, all_vars)
    )
    
    # 5. Require that the N-1 other variables are known to be "NotVal"
    for var in other_vars:
        premises.append(Predicate("NotVal", [i, j, var]))
        
    # 6. Return the constructed Rule
    return Rule(premises=premises, conclusion=Predicate("Val", [i, j, target_v]))

def load_futoshiki(file_name: str):
    """
    Parses a Futoshiki puzzle string/file and generates the initial FOL Knowledge Base.
    Returns the grid_size (N) and the populated kb set.
    """
    # 1. Clean the input (remove comments and empty lines)
    with open(file_name, 'r') as f:
        file_content = f.read()
    lines = [line.strip() for line in file_content.strip().split('\n')]
    data = [line for line in lines if line and not line.startswith('#')]
    
    if not data:
        raise ValueError("Input file is empty or only contains comments/whitespace.")

    # The first line is the grid size N
    N = int(data[0])
    kb = {}

    for n in range(1, N + 1):
        add_fact(kb, Predicate("Row", [Const(n)]))
        add_fact(kb, Predicate("Col", [Const(n)]))
        add_fact(kb, Predicate("Num", [Const(n)]))
    
    # --- 2. Parse Grid (Given Clues) ---
    grid_start = 1
    for i in range(1, N + 1):
        # Read comma-separated integers
        row_vals = [int(x.strip()) for x in data[grid_start + i - 1].split(',')]
        for j, val in enumerate(row_vals, start=1):
            if val > 0:
                add_fact(kb, Predicate("Given", [Const(i), Const(j), Const(val)]))
    
    # --- 3. Parse Horizontal Constraints (< and >) ---
    horiz_start = grid_start + N
    for i in range(1, N + 1):
        row_vals = [int(x.strip()) for x in data[horiz_start + i - 1].split(',')]
        for j, val in enumerate(row_vals, start=1):
            if val == 1:
                add_fact(kb, Predicate("LessH", [Const(i), Const(j)]))
            elif val == -1:
                add_fact(kb, Predicate("GreaterH", [Const(i), Const(j)]))

    # --- 4. Parse Vertical Constraints (^ and v) ---
    vert_start = horiz_start + N
    for i in range(1, N): # Note: There are only N-1 rows of vertical constraints
        row_vals = [int(x.strip()) for x in data[vert_start + i - 1].split(',')]
        for j, val in enumerate(row_vals, start=1):
            if val == 1:
                add_fact(kb, Predicate("LessV", [Const(i), Const(j)]))
            elif val == -1:
                add_fact(kb, Predicate("GreaterV", [Const(i), Const(j)]))

    # --- OPTIMIZATION: Rule Ordering ---
    # 1. Given Clues (Instant deduction)
    # 2. Boundaries (Instant edge trimming, no deep bindings required)
    # 3. Sudoku Uniqueness
    # 4. Inequalities 
    # Hidden single is not needed as we are doing backtracking
    rules = [
        base_rules[0],                   # Given -> Val
        *generate_boundary_rules(N),     # Absolute Boundaries
        base_rules[1],                   # Row Uniqueness
        base_rules[2],                   # Col Uniqueness
        *base_rules[3:],                 # Horizontal & Vertical Inequalities
        # generate_hidden_single_rule(N)   # Hidden Single
    ]

    return N, kb, rules
    
def mainfunc2():
    n, kb, rules = load_futoshiki("Inputs/input-12.txt")
    print(f"Loaded Futoshiki puzzle of size {n}x{n} with {sum(len(v) for v in kb.values())} initial facts.")
    
    time_start = time.perf_counter()
    
    # Use the new backtracking solver instead of just fol_fc
    final_kb = solve_with_backtracking(kb, rules, n)
    
    time_running = time.perf_counter() - time_start

    if final_kb is None:
        print("\nNo solution exists or contradiction reached.")
    else:
        print("\n--- Summary of Deduced Values ---")
        val_facts = final_kb.get("Val", set())
        vals = sorted(list(val_facts), key=lambda x: (x.terms[0].name, x.terms[1].name))
        
        # Print Grid Formatted
        grid = [[0]*n for _ in range(n)]
        for val in vals:
            r, c, v = val.terms[0].name, val.terms[1].name, val.terms[2].name
            grid[r-1][c-1] = v
            
        for row in grid:
            print(" ".join(str(x) for x in row))

    print(f"\nTotal time taken: {time_running:.4f} seconds")

if __name__ == "__main__":
    mainfunc2()


if __name__ == "__main__":
    mainfunc2()
    