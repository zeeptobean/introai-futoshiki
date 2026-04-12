# forward chaining FOL
class Term: pass

class Const(Term):
    def __init__(self, name): self.name = name
    def __eq__(self, other): return isinstance(other, Const) and self.name == other.name
    def __hash__(self): return hash(self.name)
    def __repr__(self): return str(self.name)

class Var(Term):
    def __init__(self, name): self.name = name
    def __eq__(self, other): return isinstance(other, Var) and self.name == other.name
    def __hash__(self): return hash(self.name)
    def __repr__(self): return f"?{self.name}"

class Predicate:
    def __init__(self, name, terms):
        self.name = name
        self.terms = terms
    def __eq__(self, other):
        return isinstance(other, Predicate) and self.name == other.name and self.terms == other.terms
    def __hash__(self):
        return hash((self.name, tuple(self.terms)))
    def __repr__(self):
        return f"{self.name}({', '.join(map(str, self.terms))})"

class NativeMath(Predicate):
    def __init__(self, func, terms):
        super().__init__("NativeMath", terms)
        self.func = func

class Rule:
    def __init__(self, premises, conclusion):
        self.premises = premises       
        self.conclusion = conclusion   
    def __repr__(self):
        return f"{' ^ '.join(map(str, self.premises))} => {self.conclusion}"

# ==========================================
# 2. The UNIFY Algorithm
# ==========================================

def unify(x, y, theta):
    if theta is None: return None
    elif x == y: return theta
    elif isinstance(x, Var): return unify_var(x, y, theta)
    elif isinstance(y, Var): return unify_var(y, x, theta)
    elif isinstance(x, Predicate) and isinstance(y, Predicate):
        if x.name != y.name or len(x.terms) != len(y.terms): return None
        for i in range(len(x.terms)):
            theta = unify(x.terms[i], y.terms[i], theta)
        return theta
    else: return None

def unify_var(var, x, theta):
    if var in theta: return unify(theta[var], x, theta)
    elif x in theta: return unify(var, theta[x], theta)
    else:
        new_theta = theta.copy()
        new_theta[var] = x
        return new_theta

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

def match_premises(premises, kb, theta):
    if not premises:
        yield theta
        return
    
    first_premise = premises[0]
    rest_premises = premises[1:]
    
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
                yield from match_premises(rest_premises, kb, theta)
        return 

    for fact in list(kb):
        theta_new = unify(first_premise, fact, theta.copy())
        if theta_new is not None:
            yield from match_premises(rest_premises, kb, theta_new)

def fol_fc(kb, rules):
    # print("\n--- Starting Forward Chaining ---")
    new_facts_found = True
    iteration = 1
    
    while new_facts_found:
        new_facts_found = False
        print(f"Iteration {iteration} running...")
        
        for rule in rules:
            for theta in match_premises(rule.premises, kb, {}):
                q_prime = substitute(theta, rule.conclusion)
                
                if q_prime not in kb:
                    kb.add(q_prime)
                    new_facts_found = True
        iteration += 1
    
    # print("--- Forward Chaining Exhausted ---")
    return kb

# ==========================================
# 4. Futoshiki Ruleset (3x3 Native-Optimized)
# ==========================================

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
    kb = set()

    for n in range(1, N + 1):
        kb.add(Predicate("Row", [Const(n)]))
        kb.add(Predicate("Col", [Const(n)]))
        kb.add(Predicate("Num", [Const(n)]))
    
    # --- 2. Parse Grid (Given Clues) ---
    grid_start = 1
    for i in range(1, N + 1):
        # Read comma-separated integers
        row_vals = [int(x.strip()) for x in data[grid_start + i - 1].split(',')]
        for j, val in enumerate(row_vals, start=1):
            if val > 0:
                kb.add(Predicate("Given", [Const(i), Const(j), Const(val)]))

    # --- 3. Parse Horizontal Constraints (< and >) ---
    horiz_start = grid_start + N
    for i in range(1, N + 1):
        row_vals = [int(x.strip()) for x in data[horiz_start + i - 1].split(',')]
        for j, val in enumerate(row_vals, start=1):
            if val == 1:
                kb.add(Predicate("LessH", [Const(i), Const(j)]))
            elif val == -1:
                kb.add(Predicate("GreaterH", [Const(i), Const(j)]))

    # --- 4. Parse Vertical Constraints (^ and v) ---
    vert_start = horiz_start + N
    for i in range(1, N): # Note: There are only N-1 rows of vertical constraints
        row_vals = [int(x.strip()) for x in data[vert_start + i - 1].split(',')]
        for j, val in enumerate(row_vals, start=1):
            if val == 1:
                kb.add(Predicate("LessV", [Const(i), Const(j)]))
            elif val == -1:
                kb.add(Predicate("GreaterV", [Const(i), Const(j)]))

    rules = [*base_rules, *generate_boundary_rules(N), generate_hidden_single_rule(N)]

    return N, kb, rules

def mainfunc1():
    # Base Setup: Domains
    grid_size = 4
    kb = set()
    for n in range(1, grid_size + 1):
        kb.add(Predicate("Row", [Const(n)]))
        kb.add(Predicate("Col", [Const(n)]))
        kb.add(Predicate("Num", [Const(n)]))

    # Puzzle Clues (The Cascade Triggers)
    kb.add(Predicate("Given", [Const(1), Const(1), Const(4)]))
    kb.add(Predicate("Given", [Const(2), Const(2), Const(3)]))
    kb.add(Predicate("Given", [Const(3), Const(4), Const(2)]))
    kb.add(Predicate("Given", [Const(4), Const(2), Const(2)]))
    
    # Constraints 
    kb.add(Predicate("LessH", [Const(2), Const(2)])) # (2,2) < (2,3)
    kb.add(Predicate("LessH", [Const(4), Const(2)])) # (4,2) < (4,3)

    rules = [*base_rules, generate_hidden_single_rule(grid_size)]

    # Run Engine
    final_kb = fol_fc(kb, rules)
    
    # Print Deductions
    print("\n--- Summary of Deduced Values ---")
    vals = sorted([f for f in final_kb if f.name == "Val"], key=lambda x: (x.terms[0].name, x.terms[1].name))
    for val in vals:
        print(f"Cell ({val.terms[0]}, {val.terms[1]}) = {val.terms[2]}")
        
    print("\n--- Summary of Eliminated Possibilities ---")
    not_vals = [f for f in final_kb if f.name == "NotVal"]
    print(f"Total eliminated choices: {len(not_vals)}")
    
def mainfunc2():
    n, kb, rules = load_futoshiki("puzzle2.txt")
    final_kb = fol_fc(kb, rules)
    vals = sorted([f for f in final_kb if f.name == "Val"], key=lambda x: (x.terms[0].name, x.terms[1].name))
    for val in vals:
        print(f"Cell ({val.terms[0]}, {val.terms[1]}) = {val.terms[2]}")

    print("\n--- Summary of Eliminated Possibilities ---")
    not_vals = [f for f in final_kb if f.name == "NotVal"]
    print(f"Total eliminated choices: {len(not_vals)}")


if __name__ == "__main__":
    mainfunc2()
    