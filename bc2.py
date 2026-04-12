# backward chaining
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


# --- Unification & Substitution Engine ---

def is_variable(x):
    return isinstance(x, Var)

def unify(x, y, theta):
    if theta is None: return None
    if x == y: return theta
    if is_variable(x): return unify_var(x, y, theta)
    if is_variable(y): return unify_var(y, x, theta)
    
    if isinstance(x, Predicate) and isinstance(y, Predicate):
        if x.name != y.name: return None
        return unify(x.terms, y.terms, theta)
        
    if isinstance(x, list) and isinstance(y, list):
        if len(x) != len(y): return None
        if len(x) == 0: return theta
        return unify(x[1:], y[1:], unify(x[0], y[0], theta))
        
    return None

def unify_var(var, x, theta):
    if var in theta: return unify(theta[var], x, theta)
    if is_variable(x) and x in theta: return unify(var, theta[x], theta)
    new_theta = theta.copy()
    new_theta[var] = x
    return new_theta

def subst(theta, x):
    if is_variable(x):
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


# --- Backward Chaining Algorithms ---

def fol_bc_ask(kb, query):
    yield from fol_bc_or(kb, query, {})

def fol_bc_or(kb, goal, theta):
    for rule in kb:
        rule_std = standardize_variables(rule)
        # Match rule conclusion with the goal
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
        
        # Evaluate NativeMath blocks immediately to trigger early pruning
        if isinstance(first_subst, NativeMath):
            # Verify all terms are grounded (converted to Const)
            if all(isinstance(t, Const) for t in first_subst.terms):
                args = [t.name for t in first_subst.terms]
                if first_subst.func(*args):
                    yield from fol_bc_and(kb, rest, theta)
            else:
                raise RuntimeError(f"NativeMath encountered unbound variables: {first_subst}. Check premise ordering.")
        else:
            for theta_prime in fol_bc_or(kb, first_subst, theta):
                for theta_double_prime in fol_bc_and(kb, rest, theta_prime):
                    yield theta_double_prime


# --- Futoshiki Logic Formulator ---

def solve_futoshiki(size, givens, less_h, less_v):
    kb = []
    
    # 1. Base Facts: Domain values [1...N]
    for i in range(1, size + 1):
        kb.append(Rule([], Predicate("Domain", [Const(i)])))
        
    # 2. Base Facts: Given values map directly
    given_dict = {(r, c): v for (r, c, v) in givens}
    for (r, c, v) in givens:
        kb.append(Rule([], Predicate("Given", [Const(r), Const(c), Const(v)])))

    # 3. Master Construct Rule (Interleaving assignment & constraints for early pruning)
    variables = []
    premises = []
    
    for r in range(1, size + 1):
        for c in range(1, size + 1):
            v_rc = Var(f"v_{r}_{c}")
            variables.append(v_rc)
            
            # Assignment
            if (r, c) in given_dict:
                premises.append(Predicate("Given", [Const(r), Const(c), v_rc]))
            else:
                premises.append(Predicate("Domain", [v_rc]))
            
            # Axiom 3: Row Uniqueness (Check against earlier columns)
            for c_prev in range(1, c):
                v_prev = Var(f"v_{r}_{c_prev}")
                premises.append(NativeMath(lambda x, y: x != y, [v_rc, v_prev]))
            
            # Axiom 4: Column Uniqueness (Check against earlier rows)
            for r_prev in range(1, r):
                v_prev = Var(f"v_{r_prev}_{c}")
                premises.append(NativeMath(lambda x, y: x != y, [v_rc, v_prev]))
            
            # Axioms 6 & 7: Horizontal Inequalities (Check left neighbor if mapped)
            if (r, c - 1) in less_h:
                v_left = Var(f"v_{r}_{c-1}")
                premises.append(NativeMath(lambda left, right: left < right, [v_left, v_rc]))
            
            # Axioms 8 & 9: Vertical Inequalities (Check top neighbor if mapped)
            if (r - 1, c) in less_v:
                v_top = Var(f"v_{r-1}_{c}")
                premises.append(NativeMath(lambda top, bottom: top < bottom, [v_top, v_rc]))

    kb.append(Rule(premises, Predicate("Solve", variables)))
    query = Predicate("Solve", variables)
    
    # Run the engine
    for solution in fol_bc_ask(kb, query):
        yield {v.name: subst(solution, v).name for v in variables}

# --- Execution Example ---
if __name__ == "__main__":
    # 3x3 Grid
    size = 3
    # cell(1,1) = 3
    givens = [(1, 1, 3)] 
    # cell(1,2) < cell(1,3)
    less_h = [(1, 2)] 
    # cell(2,1) < cell(3,1)
    less_v = [(2, 1)] 
    
    print("Finding solutions...")
    solutions = solve_futoshiki(size, givens, less_h, less_v)
    
    for i, sol in enumerate(solutions):
        print(f"\nSolution {i+1}:")
        for r in range(1, size + 1):
            row = [sol[f"v_{r}_{c}"] for c in range(1, size + 1)]
            print(" ", row)