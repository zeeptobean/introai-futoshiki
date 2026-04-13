from typing import Callable

class Term: 
    def __init__(self, name: str | int): self.name = name
    def __hash__(self): return hash(self.name)

class Const(Term):
    def __init__(self, name: int):
        super().__init__(name)
    def __eq__(self, other): return isinstance(other, Const) and self.name == other.name
    def __hash__(self): return hash(self.name)
    def __repr__(self): return str(self.name)

class Var(Term):
    def __init__(self, name: str):
        super().__init__(name)
    def __eq__(self, other): return isinstance(other, Var) and self.name == other.name
    def __hash__(self): return hash(self.name)
    def __repr__(self): return f"?{self.name}"

class Predicate:
    def __init__(self, name: str, terms):
        self.name = name
        self.terms = terms
    def __eq__(self, other):
        return isinstance(other, Predicate) and self.name == other.name and self.terms == other.terms
    def __hash__(self):
        return hash((self.name, tuple(self.terms)))
    def __repr__(self):
        return f"{self.name}({', '.join(map(str, self.terms))})"

class NativeMath(Predicate):
    def __init__(self, func: Callable[..., bool], terms):
        super().__init__("NativeMath", terms)
        self.func = func

class Rule:
    def __init__(self, premises, conclusion):
        self.premises = premises       
        self.conclusion = conclusion   
    def __repr__(self):
        return f"{' ^ '.join(map(str, self.premises))} => {self.conclusion}"
    
Theta = dict[Var, object]

def unify(x, y, theta: Theta | None) -> Theta | None:
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

def occur_check(var, x, theta: Theta) -> bool:
    if var == x:
        return True
    elif isinstance(x, Var) and x in theta:
        return occur_check(var, theta[x], theta)
    elif isinstance(x, Predicate):
        return any(occur_check(var, term, theta) for term in x.terms)
    elif isinstance(x, list):
        return any(occur_check(var, element, theta) for element in x)
    return False

def unify_var(var, x, theta: Theta) -> Theta | None:
    if var in theta: return unify(theta[var], x, theta)
    elif isinstance(x, Var) and x in theta: return unify(var, theta[x], theta)
    # elif occur_check(var, x, theta): return None      # inf loop check, turn off for speed
    else:
        new_theta = theta.copy()
        new_theta[var] = x
        return new_theta