# forward chaining FOL, with optimizations
import time

from myfol import *


def _emit_trace(trace_callback, action, step_index, message, metadata=None):
    if trace_callback is None:
        return
    trace_callback(
        {
            "action": action,
            "step_index": step_index,
            "message": message,
            "metadata": metadata or {},
        }
    )


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

# ==========================================
# 3. Forward Chaining Engine
# ==========================================

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

def fol_fc(kb, rules, should_cancel=None, trace_callback=None):
    # print("\n--- Starting Forward Chaining ---")
    new_facts_found = True
    iteration = 1
    step_index = 0
    
    while new_facts_found:
        if should_cancel is not None and should_cancel():
            raise RuntimeError("Solve cancelled")

        step_index += 1
        _emit_trace(
            trace_callback,
            "progress",
            step_index,
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
        # print(f"Iteration {iteration} running...")
        
        for rule_idx, rule in enumerate(rules):
            if should_cancel is not None and should_cancel():
                raise RuntimeError("Solve cancelled")
            for theta in match_premises(rule.premises, kb, {}, should_cancel=should_cancel):
                q_prime = substitute(theta, rule.conclusion)
                
                # --- OPTIMIZATION: Dictionary Insertion ---
                category = kb.setdefault(q_prime.name, set())
                if q_prime not in category:
                    category.add(q_prime)
                    new_facts_found = True

                    if q_prime.name == "Val":
                        new_val_count += 1
                        step_index += 1
                        _emit_trace(
                            trace_callback,
                            "assign",
                            step_index,
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

        step_index += 1
        _emit_trace(
            trace_callback,
            "progress",
            step_index,
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
    
    # print("--- Forward Chaining Exhausted ---")
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
    # 5. Hidden Single (HEAVIEST rule, goes last to benefit from prior pruning)
    rules = [
        base_rules[0],                   # Given -> Val
        *generate_boundary_rules(N),     # Absolute Boundaries
        base_rules[1],                   # Row Uniqueness
        base_rules[2],                   # Col Uniqueness
        *base_rules[3:],                 # Horizontal & Vertical Inequalities
        generate_hidden_single_rule(N)   # Hidden Single
    ]

    return N, kb, rules
    
def mainfunc2():
    n, kb, rules = load_futoshiki("Inputs/input-10.txt")
    print(f"Loaded Futoshiki puzzle of size {n}x{n} with {sum(len(v) for v in kb.values())} initial facts.")
    time_start = time.perf_counter()
    final_kb = fol_fc(kb, rules)
    time_running = time.perf_counter() - time_start
    val_facts = final_kb.get("Val", set())
    not_val_facts = final_kb.get("NotVal", set())

    print("\n--- Summary of Deduced Values ---")
    vals = sorted(list(val_facts), key=lambda x: (x.terms[0].name, x.terms[1].name))
    for val in vals:
        print(f"Cell ({val.terms[0]}, {val.terms[1]}) = {val.terms[2]}")

    print(f"\nTotal time taken: {time_running:.4f} seconds")
    # print("\n--- Summary of Eliminated Possibilities ---")
    # print(f"Total eliminated choices: {len(not_val_facts)}")


if __name__ == "__main__":
    mainfunc2()
    