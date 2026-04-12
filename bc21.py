# backward chaining
import time


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
# 2. Unification Engine
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
    elif isinstance(x, list) and isinstance(y, list):
        if len(x) != len(y): return None
        if len(x) == 0: return theta
        return unify(x[1:], y[1:], unify(x[0], y[0], theta))
    else: return None

def unify_var(var, x, theta):
    if var in theta: return unify(theta[var], x, theta)
    elif isinstance(x, Var) and x in theta: return unify(var, theta[x], theta)
    else:
        new_theta = theta.copy()
        new_theta[var] = x
        return new_theta

def subst(theta, x):
    """Deep substitution tailored for Backward Chaining."""
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
def standardize_variables(rule):
    """Prevents variable collisions across recursive goal checks."""
    global var_counter
    var_counter += 1
    suffix = f"_{var_counter}"

    def rename(term):
        if isinstance(term, Var): return Var(term.name + suffix)
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

def fol_bc_ask(kb, query):
    yield from fol_bc_or(kb, query, {})

def fol_bc_or(kb, goal, theta):
    for rule in kb:
        rule_std = standardize_variables(rule)
        theta_prime = unify(rule_std.conclusion, goal, theta)
        if theta_prime is not None:
            for next_theta in fol_bc_and(kb, rule_std.premises, theta_prime):
                yield next_theta

def fol_bc_and(kb, goals, theta):
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
                    yield from fol_bc_and(kb, rest, theta)
            else:
                raise RuntimeError(f"NativeMath encountered unbound variables: {first_subst}")
        else:
            for theta_prime in fol_bc_or(kb, first_subst, theta):
                for theta_double_prime in fol_bc_and(kb, rest, theta_prime):
                    yield theta_double_prime

# ==========================================
# 4. Puzzle File Parsing & Setup
# ==========================================

def load_and_solve_futoshiki(file_name: str):
    """
    Parses a Futoshiki puzzle text file and builds a Backward Chaining Knowledge Base.
    """
    with open(file_name, 'r') as f:
        file_content = f.read()
    lines = [line.strip() for line in file_content.strip().split('\n')]
    data = [line for line in lines if line and not line.startswith('#')]
    
    if not data:
        raise ValueError("Input file is empty or only contains comments/whitespace.")

    size = int(data[0])
    
    kb = []
    givens = {}
    less_h, greater_h = set(), set()
    less_v, greater_v = set(), set()

    # 1. Base Facts: Domain values [1...N]
    for i in range(1, size + 1):
        kb.append(Rule([], Predicate("Domain", [Const(i)])))

    # 2. Parse Grid (Given Clues)
    grid_start = 1
    for i in range(1, size + 1):
        row_vals = [int(x.strip()) for x in data[grid_start + i - 1].split(',')]
        for j, val in enumerate(row_vals, start=1):
            if val > 0:
                givens[(i, j)] = val
                kb.append(Rule([], Predicate("Given", [Const(i), Const(j), Const(val)])))

    # 3. Parse Horizontal Constraints
    horiz_start = grid_start + size
    for i in range(1, size + 1):
        row_vals = [int(x.strip()) for x in data[horiz_start + i - 1].split(',')]
        for j, val in enumerate(row_vals, start=1):
            if val == 1: less_h.add((i, j))
            elif val == -1: greater_h.add((i, j))

    # 4. Parse Vertical Constraints
    vert_start = horiz_start + size
    for i in range(1, size): 
        row_vals = [int(x.strip()) for x in data[vert_start + i - 1].split(',')]
        for j, val in enumerate(row_vals, start=1):
            if val == 1: less_v.add((i, j))
            elif val == -1: greater_v.add((i, j))

    # 5. Build the Master Construct Rule
    variables = []
    premises = []
    
    for r in range(1, size + 1):
        for c in range(1, size + 1):
            v_rc = Var(f"v_{r}_{c}")
            variables.append(v_rc)
            
            # Require Domain bindings based on Given clues
            if (r, c) in givens:
                premises.append(Predicate("Given", [Const(r), Const(c), v_rc]))
            else:
                premises.append(Predicate("Domain", [v_rc]))
            
            # Early pruning: Row Uniqueness 
            for c_prev in range(1, c):
                v_prev = Var(f"v_{r}_{c_prev}")
                premises.append(NativeMath(lambda x, y: x != y, [v_rc, v_prev]))
                
            # Early pruning: Column Uniqueness
            for r_prev in range(1, r):
                v_prev = Var(f"v_{r_prev}_{c}")
                premises.append(NativeMath(lambda x, y: x != y, [v_rc, v_prev]))
            
            # Horizontal Check (left neighbor: r, c-1)
            if (r, c - 1) in less_h:
                v_left = Var(f"v_{r}_{c-1}")
                premises.append(NativeMath(lambda left, right: left < right, [v_left, v_rc]))
            elif (r, c - 1) in greater_h:
                v_left = Var(f"v_{r}_{c-1}")
                premises.append(NativeMath(lambda left, right: left > right, [v_left, v_rc]))
            
            # Vertical Check (top neighbor: r-1, c)
            if (r - 1, c) in less_v:
                v_top = Var(f"v_{r-1}_{c}")
                premises.append(NativeMath(lambda top, bottom: top < bottom, [v_top, v_rc]))
            elif (r - 1, c) in greater_v:
                v_top = Var(f"v_{r-1}_{c}")
                premises.append(NativeMath(lambda top, bottom: top > bottom, [v_top, v_rc]))

    # Create Goal and add Solve rule to KB
    kb.append(Rule(premises, Predicate("Solve", variables)))
    query = Predicate("Solve", variables)
    
    return kb, query, variables, size

# ==========================================
# 5. Execution Runner
# ==========================================

def main():
    time_start = time.perf_counter()
    
    kb, query, variables, size = load_and_solve_futoshiki("input-01.txt")
    
    solutions_found = 0
    for solution in fol_bc_ask(kb, query):
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