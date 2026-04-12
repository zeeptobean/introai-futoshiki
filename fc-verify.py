from typing import Iterator

SentenceArity2 = tuple[str, str, str]
SentenceArity3 = tuple[str, str, str, str]
Sentence = tuple
Substitution = dict[str, str | Sentence]

NATIVE_PREDICATES = {
    'Less': lambda v1, v2: int(v1) < int(v2),
    'NotEqual': lambda x, y: x != y
}

def is_variable(x) -> bool:
    return isinstance(x, str) and x.startswith('?')

def is_compound(x) -> bool:
    return isinstance(x, tuple)

def unify(x, y, theta: Substitution) -> Substitution | None:
    new_theta = theta.copy()
    if _unify_recursive(x, y, new_theta):
        return new_theta
    return None

def _unify_var(var: str, x, theta: Substitution) -> bool:
    if var in theta:
        return _unify_recursive(theta[var], x, theta)
    elif is_variable(x) and x in theta:
        return _unify_recursive(var, theta[x], theta)
    else:
        theta[var] = x
        return True

def _unify_recursive(x, y, theta: Substitution) -> bool:
    if x == y:
        return True
    if is_variable(x):
        return _unify_var(x, y, theta)
    if is_variable(y):
        return _unify_var(y, x, theta)
    if is_compound(x) and is_compound(y) and len(x) == len(y):
        for i in range(len(x)):
            if not _unify_recursive(x[i], y[i], theta):
                return False
        return True
    return False

class Rule:
    def __init__(self, premises: list[Sentence], conclusion: Sentence):
        self.premises = premises
        self.conclusion = conclusion
        
    def __repr__(self):
        return f"{' AND '.join(map(str, self.premises))} => {self.conclusion}"

class KnowledgeBase:
    def __init__(self):
        self.facts: set[Sentence] = set()        
        self.rules: list[Rule] = []

    def add_fact(self, fact: Sentence):
        self.facts.add(fact)

    def add_rule(self, premises: list[Sentence], conclusion: Sentence):
        self.rules.append(Rule(premises, conclusion))

    def substitute(self, sentence: Sentence, theta: Substitution) -> Sentence:
        """Replaces variables in a sentence with their bound values from theta."""
        if not isinstance(sentence, tuple):
            return sentence
        
        # Recursively substitute variables in the tuple
        result = []
        for term in sentence:
            if is_variable(term) and term in theta:
                # If the variable is bound to another variable/tuple, substitute further
                result.append(theta[term]) 
            else:
                result.append(term)
        return tuple(result)

    # ==========================================
    # Forward Chaining (Modus Ponens) Engine
    # ==========================================

    def _match_premises(self, premises: list[Sentence], theta: Substitution) -> Iterator[Substitution]:
        """Recursively yields valid substitutions that satisfy all remaining premises."""
        if not premises:
            # All premises satisfied
            yield theta
            return

        first_premise = premises[0]
        rest_premises = premises[1:]
        
        # Substitute known variables into the current premise
        sub_premise = self.substitute(first_premise, theta)
        predicate = sub_premise[0]
        
        # Handle Native Predicates (e.g., Less, NotEqual)
        if predicate in NATIVE_PREDICATES:
            # Ensure all variables are bound before evaluating native functions
            if any(is_variable(arg) for arg in sub_premise[1:]):
                raise ValueError(f"Unbound variable(s) reached native predicate evaluate: {sub_premise}. "
                                 f"Ensure rules list structural premises before native ones.")
            
            # If the native function evaluates to True, continue matching
            if NATIVE_PREDICATES[predicate](*sub_premise[1:]):
                yield from self._match_premises(rest_premises, theta)
        
        # Handle standard Knowledge Base facts
        else:
            for fact in list(self.facts):
                new_theta = unify(sub_premise, fact, theta)
                if new_theta is not None:
                    yield from self._match_premises(rest_premises, new_theta)

    def forward_chain(self) -> int:
        """
        Applies Modus Ponens repeatedly until no new facts can be deduced.
        Returns the number of new facts deduced.
        """
        new_facts_count = 0
        added_this_iteration = True
        
        while added_this_iteration:
            added_this_iteration = False
            
            for rule in self.rules:
                # Find all variable bindings that satisfy the rule's premises
                for theta in self._match_premises(rule.premises, {}):
                    # Create the deduced conclusion
                    new_fact = self.substitute(rule.conclusion, theta)
                    
                    if new_fact not in self.facts:
                        self.add_fact(new_fact)
                        added_this_iteration = True
                        new_facts_count += 1
                        print(f"Deduced: {new_fact} (using {theta})")
                        
        return new_facts_count

def setup_futoshiki() -> KnowledgeBase:
    """Adds the First-Order Logic rules using the new predicate model."""
    kb = KnowledgeBase()

    kb.add_rule(
        premises=[('Given', '?c', '?v')],
        conclusion=('Val', '?c', '?v')
    )
    
    # RULE 1: If an inequality constraint exists, and the values obey it, emit ConstraintSatisfied
    kb.add_rule(
        premises=[
            ('BoardLess', '?c1', '?c2'),
            ('Val', '?c1', '?v1'),
            ('Val', '?c2', '?v2'),
            ('Less', '?v1', '?v2')  # Calls NATIVE_PREDICATES['Less']
        ],
        conclusion=('ConstraintSatisfied', '?c1', '?c2')
    )

    # RULE 2: If two distinct cells in the same row have the same value, emit ConflictRow
    kb.add_rule(
        premises=[
            ('SameRow', '?c1', '?c2'),
            ('Val', '?c1', '?v'),
            ('Val', '?c2', '?v'),
            ('NotEqual', '?c1', '?c2') # Calls NATIVE_PREDICATES['NotEqual']
        ],
        conclusion=('Conflict', '?c1', '?c2')
    )
    
    # RULE 3: Same for columns
    kb.add_rule(
        premises=[
            ('SameCol', '?c1', '?c2'),
            ('Val', '?c1', '?v'),
            ('Val', '?c2', '?v'),
            ('NotEqual', '?c1', '?c2')
        ],
        conclusion=('Conflict', '?c1', '?c2')
    )
    return kb

def load_futoshiki_from_file(filename: str, kb: KnowledgeBase):
    err_str = f"Failed to load Futoshiki puzzle from {filename}:"
    with open(filename, 'r') as f:
        # Filter out comments and empty lines
        lines = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
    
    try:
        N = int(lines[0])
        line_idx = 1
    except ValueError:
        print(f"{err_str} First line should be an integer representing grid size N.")
        return
    
    # 1. Emit Structural Facts (SameRow and SameCol)
    for i in range(N):
        for j1 in range(N):
            for j2 in range(N):
                if j1 != j2:
                    kb.add_fact(('SameRow', f'r{i}c{j1}', f'r{i}c{j2}'))
                    kb.add_fact(('SameCol', f'r{j1}c{i}', f'r{j2}c{i}'))

    # 2. Parse the Grid (N lines of N values)
    # 0 = empty, 1..N = Given pre-filled digit
    for i in range(N):
        row_vals = lines[line_idx].split(',')
        for j in range(N):
            val = int(row_vals[j].strip())
            if val != 0:
                # Arity 2: ('Given', 'r0c0', '3')
                kb.add_fact(('Given', f'r{i}c{j}', str(val)))
        line_idx += 1

    # 3. Parse Horizontal Constraints (N lines of N-1 values)
    # 1 = Left < Right, -1 = Left > Right
    for i in range(N):
        row_vals = lines[line_idx].split(',')
        for j in range(N - 1):
            val = int(row_vals[j].strip())
            left_cell = f'r{i}c{j}'
            right_cell = f'r{i}c{j+1}'
            
            if val == 1:
                kb.add_fact(('BoardLess', left_cell, right_cell))
            elif val == -1:
                # If Left > Right, then Right < Left
                kb.add_fact(('BoardLess', right_cell, left_cell))
        line_idx += 1

    # 4. Parse Vertical Constraints (N-1 lines of N values)
    # 1 = Top < Bottom, -1 = Top > Bottom
    for i in range(N - 1):
        row_vals = lines[line_idx].split(',')
        for j in range(N):
            val = int(row_vals[j].strip())
            top_cell = f'r{i}c{j}'
            bottom_cell = f'r{i+1}c{j}'
            
            if val == 1:
                kb.add_fact(('BoardLess', top_cell, bottom_cell))
            elif val == -1:
                # If Top > Bottom, then Bottom < Top
                kb.add_fact(('BoardLess', bottom_cell, top_cell))
        line_idx += 1


# ==========================================
# Execution Example
# ==========================================
if __name__ == "__main__":
    kb = setup_futoshiki()

    load_futoshiki_from_file("puzzle.txt", kb)
    
    print("\nRunning Forward Chaining...")
    kb.forward_chain()
    
    # Now we check the KB to see what it deduced about our board state
    print("\n--- Board Analysis Results ---")
    
    # Did we satisfy constraints?
    satisfied = [f for f in kb.facts if f[0] == 'ConstraintSatisfied']
    for s in satisfied:
        print(f"  -> {s[1]} < {s[2]} is correct.")
        
    # Did we trigger any row/col conflicts?
    conflicts = [f for f in kb.facts if f[0] in ('Conflict', 'Conflict')]
    if conflicts:
        print(f"\nCRITICAL FAILURES DETECTED ({len(conflicts)} rule violations):")
        for c in conflicts:
            print(f"  -> {c[0]} between {c[1]} and {c[2]}")