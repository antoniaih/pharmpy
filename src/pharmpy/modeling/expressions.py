from __future__ import annotations

from itertools import filterfalse
from typing import Callable, Dict, Iterable, List, Sequence, Set, Tuple, TypeVar, Union

from pharmpy.deps import sympy
from pharmpy.expressions import subs, sympify
from pharmpy.model import Assignment, Compartment, CompartmentalSystem, Model, ODESystem, Statements

from .parameters import get_thetas

T = TypeVar('T')
U = TypeVar('U')


def get_observation_expression(model):
    """Get the full symbolic expression for the observation according to the model

    This function currently only support models without ODE systems

    Parameters
    ----------
    model : Model
        Pharmpy model object

    Returns
    -------
    Expression
        Symbolic expression

    Examples
    --------
    >>> from pharmpy.modeling import load_example_model, get_observation_expression
    >>> import sympy
    >>> model = load_example_model("pheno_linear")
    >>> expr = get_observation_expression(model)
    >>> sympy.pprint(expr)
    D_EPSETA1_2⋅EPS(1)⋅(ETA(2) - OETA₂) + D_ETA1⋅(ETA(1) - OETA₁) + D_ETA2⋅(ETA(2)
     - OETA₂) + EPS(1)⋅(D_EPS1 + D_EPSETA1_1⋅(ETA(1) - OETA₁)) + OPRED
    """
    stats = model.statements
    dv = model.dependent_variable
    for i, s in enumerate(stats):
        if s.symbol == dv:
            y = s.expression
            break
    else:
        raise ValueError('Could not locate dependent variable expression')

    for j in range(i, -1, -1):
        y = subs(y, {stats[j].symbol: stats[j].expression}, simultaneous=True)

    return y


def get_individual_prediction_expression(model):
    """Get the full symbolic expression for the modelled individual prediction

    This function currently only support models without ODE systems

    Parameters
    ----------
    model : Model
        Pharmpy model object

    Returns
    -------
    Expression
        Symbolic expression

    Examples
    --------
    >>> from pharmpy.modeling import load_example_model, get_individual_prediction_expression
    >>> model = load_example_model("pheno_linear")
    >>> get_individual_prediction_expression(model)
    D_ETA1*(ETA(1) - OETA1) + D_ETA2*(ETA(2) - OETA2) + OPRED

    See Also
    --------
    get_population_prediction_expression : Get full symbolic epression for the population prediction
    """
    return subs(
        get_observation_expression(model),
        {sympy.Symbol(eps): 0 for eps in model.random_variables.epsilons.names},
        simultaneous=True,
    )


def get_population_prediction_expression(model):
    """Get the full symbolic expression for the modelled population prediction

    This function currently only support models without ODE systems

    Parameters
    ----------
    model : Model
        Pharmpy model object

    Returns
    -------
    Expression
        Symbolic expression

    Examples
    --------
    >>> from pharmpy.modeling import load_example_model, get_population_prediction_expression
    >>> model = load_example_model("pheno_linear")
    >>> get_population_prediction_expression(model)
    -D_ETA1*OETA1 - D_ETA2*OETA2 + OPRED

    See also
    --------
    get_individual_prediction_expression : Get full symbolic epression for the individual prediction
    """

    return subs(
        get_individual_prediction_expression(model),
        {sympy.Symbol(eta): 0 for eta in model.random_variables.etas.names},
        simultaneous=True,
    )


def calculate_eta_gradient_expression(model):
    """Calculate the symbolic expression for the eta gradient

    This function currently only support models without ODE systems

    Parameters
    ----------
    model : Model
        Pharmpy model object

    Returns
    -------
    Expression
        Symbolic expression

    Examples
    --------
    >>> from pharmpy.modeling import load_example_model, calculate_eta_gradient_expression
    >>> model = load_example_model("pheno_linear")
    >>> calculate_eta_gradient_expression(model)
    [D_ETA1, D_ETA2]

    See also
    --------
    calculate_epsilon_gradient_expression : Epsilon gradient
    """
    y = get_individual_prediction_expression(model)
    d = [y.diff(sympy.Symbol(x)) for x in model.random_variables.etas.names]
    return d


def calculate_epsilon_gradient_expression(model):
    """Calculate the symbolic expression for the epsilon gradient

    This function currently only support models without ODE systems

    Parameters
    ----------
    model : Model
        Pharmpy model object

    Returns
    -------
    Expression
        Symbolic expression

    Examples
    --------
    >>> from pharmpy.modeling import load_example_model, calculate_epsilon_gradient_expression
    >>> model = load_example_model("pheno_linear")
    >>> calculate_epsilon_gradient_expression(model)
    [D_EPS1 + D_EPSETA1_1*(ETA(1) - OETA1) + D_EPSETA1_2*(ETA(2) - OETA2)]

    See also
    --------
    calculate_eta_gradient_expression : Eta gradient
    """

    y = get_observation_expression(model)
    d = [y.diff(sympy.Symbol(x)) for x in model.random_variables.epsilons.names]
    return d


def create_symbol(model, stem, force_numbering=False):
    """Create a new unique variable symbol given a model

    Parameters
    ----------
    model : Model
        Pharmpy model object
    stem : str
        First part of the new variable name
    force_numbering : bool
        Forces addition of number to name even if variable does not exist, e.g.
        COVEFF --> COVEFF1

    Returns
    -------
    Symbol
        Created symbol with unique name

    Examples
    --------
    >>> from pharmpy.modeling import load_example_model, create_symbol
    >>> model = load_example_model("pheno")
    >>> create_symbol(model, "TEMP")
    TEMP
    >>> create_symbol(model, "TEMP", force_numbering=True)
    TEMP1
    >>> create_symbol(model, "CL")
    CL1
    """
    symbols = [str(symbol) for symbol in model.statements.free_symbols]
    params = [param.name for param in model.parameters]
    rvs = model.random_variables.names
    dataset_col = model.datainfo.names
    misc = [model.dependent_variable]

    all_names = symbols + params + rvs + dataset_col + misc

    if str(stem) not in all_names and not force_numbering:
        return sympy.Symbol(str(stem))

    i = 1
    while True:
        candidate = f'{stem}{i}'
        if candidate not in all_names:
            return sympy.Symbol(candidate)
        i += 1


def _find_eta_assignments(model):
    # Is this find individual parameters?
    statements = model.statements.before_odes
    etas = {sympy.Symbol(eta) for eta in model.random_variables.etas.names}
    found = set()
    leafs = []
    for s in reversed(statements):
        if (
            etas & s.free_symbols
            and len(etas & statements.full_expression(s.symbol).free_symbols) == 1
            and s.symbol not in found
        ):
            leafs = [s] + leafs
            found.update(s.free_symbols)
    return leafs


def mu_reference_model(model):
    r"""Convert model to use mu-referencing

    Mu-referencing an eta is to separately define its actual mu (mean) parameter.
    For example: :math:`CL = \theta_1 e^{\eta_1}` with :math:`\eta_1` following a zero-mean
    normal distribution would give :math:`\mu_1 = \log{\theta_1}` and
    :math:`CL = e^{\mu_1 + \eta_1}`

    Parameters
    ----------
    model : Model
        Pharmpy model object

    Returns
    -------
    Model
        Reference to same object

    Example
    -------
    >>> from pharmpy.modeling import load_example_model, mu_reference_model
    >>> model = load_example_model("pheno")
    >>> mu_reference_model(model).statements.before_odes
            ⎧TIME  for AMT > 0
            ⎨
    BTIME = ⎩ 0     otherwise
    TAD = -BTIME + TIME
    TVCL = THETA(1)⋅WGT
    TVV = THETA(2)⋅WGT
          ⎧TVV⋅(THETA(3) + 1)  for APGR < 5
          ⎨
    TVV = ⎩       TVV           otherwise
    μ₁ = log(TVCL)
          ETA(1) + μ₁
    CL = ℯ
    μ₂ = log(TVV)
         ETA(2) + μ₂
    V = ℯ
    S₁ = V
    """
    assignments = _find_eta_assignments(model)
    for i, eta in enumerate(model.random_variables.etas.names, start=1):
        for s in assignments:
            symb = sympy.Symbol(eta)
            if symb in s.expression.free_symbols:
                assind = model.statements.find_assignment_index(s.symbol)
                assignment = model.statements[assind]
                expr = assignment.expression
                _, dep = expr.as_independent(symb)
                mu = sympy.Symbol(f'mu_{i}')
                newdep = subs(dep, {symb: mu + symb})
                mu_expr = sympy.solve(expr - newdep, mu)[0]
                mu_ass = Assignment(mu, mu_expr)
                model.statements = model.statements[0:assind] + mu_ass + model.statements[assind:]
                ind = model.statements.find_assignment_index(s.symbol)
                model.statements = (
                    model.statements[0:ind]
                    + Assignment(s.symbol, newdep)
                    + model.statements[ind + 1 :]
                )
    return model


def simplify_expression(model, expr):
    """Simplify expression given constraints in model

    Parameters
    ----------
    model : Model
        Pharmpy model object
    expr : Expression
        Expression to simplify

    Returns
    -------
    Expression
        Simplified expression

    Example
    -------
    >>> from pharmpy.plugins.nonmem import conf
    >>> conf.parameter_names = ['comment', 'basic']
    >>> from pharmpy.modeling import load_example_model, simplify_expression
    >>> model = load_example_model("pheno")
    >>> simplify_expression(model, "Abs(PTVCL)")
    PTVCL
    >>> conf.parameter_names = ['basic']
    """
    expr = sympify(expr)
    d = dict()
    for p in model.parameters:
        if p.fix:
            s = sympy.Float(p.init)
        elif p.upper < 0:
            s = sympy.Symbol(p.name, real=True, negative=True)
            d[s] = p.symbol
        elif p.upper <= 0:
            s = sympy.Symbol(p.name, real=True, nonpositive=True)
            d[s] = p.symbol
        elif p.lower > 0:
            s = sympy.Symbol(p.name, real=True, positive=True)
            d[s] = p.symbol
        elif p.lower >= 0:
            s = sympy.Symbol(p.name, real=True, nonnegative=True)
            d[s] = p.symbol
        else:
            s = sympy.Symbol(p.name, real=True)
            d[s] = p.symbol
        expr = subs(expr, {p.symbol: s})
    # Remaining symbols should all be real
    for s in expr.free_symbols:
        if s.is_real is not True:
            new = sympy.Symbol(s.name, real=True)
            expr = subs(expr, {s: new})
            d[new] = s
    simp = subs(sympy.simplify(expr), d)  # Subs symbols back to non-constrained
    return simp


def solve_ode_system(model):
    """Replace ODE system with analytical solution if possible

    Warnings
    --------
    This function can currently only handle the most simple of ODE systems.

    Parameters
    ----------
    model : Model
        Pharmpy model object

    Returns
    -------
    Model
        Reference to the same pharmpy model object

    Example
    -------
    >>> from pharmpy.modeling import *
    >>> model = load_example_model("pheno")
    >>> model.statements.ode_system
    Bolus(AMT)
    ┌───────┐       ┌──────┐
    │CENTRAL│──CL/V→│OUTPUT│
    └───────┘       └──────┘
    >>> solve_ode_system(model)        # doctest: +ELLIPSIS
    <...>

    """
    odes = model.statements.ode_system
    if odes is None:
        return model
    if isinstance(odes, CompartmentalSystem):
        odes = odes.to_explicit_system()
    ics = dict(odes.ics)
    ics.popitem()
    # FIXME: Should set assumptions on symbols before solving
    # FIXME: Need a way to handle systems with no explicit solutions
    sol = sympy.dsolve(odes.odes[:-1], ics=ics)
    new = []
    for s in model.statements:
        if isinstance(s, ODESystem):
            for eq in sol:
                ass = Assignment(eq.lhs, eq.rhs)
                new.append(ass)
        else:
            new.append(s)
    model.statements = Statements(new)
    return model


def make_declarative(model):
    """Make the model statments declarative

    Each symbol will only be declared once.

    Parameters
    ----------
    model : Model
        Pharmpy model

    Results
    -------
    Model
        Reference to the same model

    Examples
    --------
    >>> from pharmpy.modeling import *
    >>> model = load_example_model("pheno")
    >>> model.statements.before_odes
            ⎧TIME  for AMT > 0
            ⎨
    BTIME = ⎩ 0     otherwise
    TAD = -BTIME + TIME
    TVCL = THETA(1)⋅WGT
    TVV = THETA(2)⋅WGT
          ⎧TVV⋅(THETA(3) + 1)  for APGR < 5
          ⎨
    TVV = ⎩       TVV           otherwise
               ETA(1)
    CL = TVCL⋅ℯ
             ETA(2)
    V = TVV⋅ℯ
    S₁ = V
    >>> make_declarative(model)     # doctest: +ELLIPSIS
    <...>
    >>> model.statements.before_odes
            ⎧TIME  for AMT > 0
            ⎨
    BTIME = ⎩ 0     otherwise
    TAD = -BTIME + TIME
    TVCL = THETA(1)⋅WGT
          ⎧THETA(2)⋅WGT⋅(THETA(3) + 1)  for APGR < 5
          ⎨
    TVV = ⎩       THETA(2)⋅WGT           otherwise
               ETA(1)
    CL = TVCL⋅ℯ
             ETA(2)
    V = TVV⋅ℯ
    S₁ = V
    """
    assigned_symbols = set()
    duplicated_symbols = dict()  # symbol to last index
    for i, s in enumerate(model.statements):
        if not isinstance(s, Assignment):
            continue
        symb = s.symbol
        if symb in assigned_symbols:
            if symb not in duplicated_symbols:
                duplicated_symbols[symb] = []
            duplicated_symbols[symb].append(i)
        else:
            assigned_symbols.add(symb)

    current = dict()
    newstats = []
    for i, s in enumerate(model.statements):
        if not isinstance(s, Assignment):
            s.subs(current)
            newstats.append(s)  # FIXME: No copy method
        elif s.symbol in duplicated_symbols:
            if i not in duplicated_symbols[s.symbol]:
                current[s.symbol] = s.expression
            else:
                duplicated_symbols[s.symbol] = duplicated_symbols[s.symbol][1:]
                if duplicated_symbols[s.symbol]:
                    current[s.symbol] = subs(s.expression, current)
                else:
                    ass = Assignment(s.symbol, subs(s.expression, current))
                    newstats.append(ass)
                    del current[s.symbol]
        else:
            ass = Assignment(s.symbol, subs(s.expression, current))
            newstats.append(ass)

    model.statements = Statements(newstats)
    return model


def cleanup_model(model):
    """Perform various cleanups of a model

    This is what is currently done

    * Make model statements declarative, i.e. only one assignment per symbol
    * Inline all assignments of one symbol, e.g. X = Y

    Notes
    -----
    When creating NONMEM code from the cleaned model Pharmpy might need to
    add certain assignments to make it in line with what NONMEM requires.

    Parameters
    ----------
    model : Model
        Pharmpy model

    Returns
    -------
    Model
        Reference to the same model

    Examples
    --------
    >>> from pharmpy.modeling import *
    >>> model = load_example_model("pheno")
    >>> model.statements
            ⎧TIME  for AMT > 0
            ⎨
    BTIME = ⎩ 0     otherwise
    TAD = -BTIME + TIME
    TVCL = THETA(1)⋅WGT
    TVV = THETA(2)⋅WGT
          ⎧TVV⋅(THETA(3) + 1)  for APGR < 5
          ⎨
    TVV = ⎩       TVV           otherwise
               ETA(1)
    CL = TVCL⋅ℯ
             ETA(2)
    V = TVV⋅ℯ
    S₁ = V
    Bolus(AMT)
    ┌───────┐       ┌──────┐
    │CENTRAL│──CL/V→│OUTPUT│
    └───────┘       └──────┘
        A_CENTRAL
        ─────────
    F =     S₁
    W = F
    Y = EPS(1)⋅W + F
    IPRED = F
    IRES = DV - IPRED
            IRES
            ────
    IWRES =  W
    >>> cleanup_model(model)    # doctest: +ELLIPSIS
    <...>
    >>> model.statements
            ⎧TIME  for AMT > 0
            ⎨
    BTIME = ⎩ 0     otherwise
    TAD = -BTIME + TIME
    TVCL = THETA(1)⋅WGT
          ⎧THETA(2)⋅WGT⋅(THETA(3) + 1)  for APGR < 5
          ⎨
    TVV = ⎩       THETA(2)⋅WGT           otherwise
               ETA(1)
    CL = TVCL⋅ℯ
             ETA(2)
    V = TVV⋅ℯ
    Bolus(AMT)
    ┌───────┐       ┌──────┐
    │CENTRAL│──CL/V→│OUTPUT│
    └───────┘       └──────┘
        A_CENTRAL
        ─────────
    F =     V
    Y = EPS(1)⋅F + F
    IRES = DV - F
            IRES
            ────
    IWRES =  F
    """
    make_declarative(model)

    current = dict()
    newstats = []
    for s in model.statements:
        if isinstance(s, Assignment) and s.expression.is_Symbol:
            current[s.symbol] = s.expression
        else:
            # FIXME: Update when other Statements have been made immutable
            if isinstance(s, Assignment):
                n = s.subs(current)
                newstats.append(n)
            else:
                s.subs(current)
                newstats.append(s)

    model.statements = Statements(newstats)
    return model


def greekify_model(model, named_subscripts=False):
    """Convert to using greek letters for all population parameters

    Parameters
    ----------
    model : Model
        Pharmpy model
    named_subscripts : bool
        Use previous parameter names as subscripts. Default is to use integer subscripts

    Returns
    -------
    Model
        Reference to the same model

    Examples
    --------
    >>> from pharmpy.modeling import *
    >>> model = load_example_model("pheno")
    >>> model.statements
            ⎧TIME  for AMT > 0
            ⎨
    BTIME = ⎩ 0     otherwise
    TAD = -BTIME + TIME
    TVCL = THETA(1)⋅WGT
    TVV = THETA(2)⋅WGT
          ⎧TVV⋅(THETA(3) + 1)  for APGR < 5
          ⎨
    TVV = ⎩       TVV           otherwise
               ETA(1)
    CL = TVCL⋅ℯ
             ETA(2)
    V = TVV⋅ℯ
    S₁ = V
    Bolus(AMT)
    ┌───────┐       ┌──────┐
    │CENTRAL│──CL/V→│OUTPUT│
    └───────┘       └──────┘
        A_CENTRAL
        ─────────
    F =     S₁
    W = F
    Y = EPS(1)⋅W + F
    IPRED = F
    IRES = DV - IPRED
            IRES
            ────
    IWRES =  W

    >>> greekify_model(cleanup_model(model))    # doctest: +ELLIPSIS
    <...>
    >>> model.statements
            ⎧TIME  for AMT > 0
            ⎨
    BTIME = ⎩ 0     otherwise
    TAD = -BTIME + TIME
    TVCL = WGT⋅θ₁
          ⎧WGT⋅θ₂⋅(θ₃ + 1)  for APGR < 5
          ⎨
    TVV = ⎩    WGT⋅θ₂        otherwise
               η₁
    CL = TVCL⋅ℯ
             η₂
    V = TVV⋅ℯ
    Bolus(AMT)
    ┌───────┐       ┌──────┐
    │CENTRAL│──CL/V→│OUTPUT│
    └───────┘       └──────┘
        A_CENTRAL
        ─────────
    F =     V
    Y = F⋅ε₁ + F
    IRES = DV - F
            IRES
            ────
    IWRES =  F

    """

    def get_subscript(param, i, named_subscripts):
        if named_subscripts:
            if isinstance(param, str):
                subscript = param
            else:
                subscript = param.name
        else:
            subscript = i
        return subscript

    def get_2d_subscript(param, row, col, named_subscripts):
        if named_subscripts:
            subscript = param.name
        else:
            subscript = f'{row}{col}'
        return subscript

    subs = dict()
    for i, theta in enumerate(get_thetas(model), start=1):
        subscript = get_subscript(theta, i, named_subscripts)
        subs[theta.symbol] = sympy.Symbol(f"theta_{subscript}")
    omega = model.random_variables.covariance_matrix
    for row in range(omega.rows):
        for col in range(omega.cols):
            if col > row:
                break
            elt = omega[row, col]
            if elt == 0:
                continue
            subscript = get_2d_subscript(elt, row + 1, col + 1, named_subscripts)
            subs[elt] = sympy.Symbol(f"omega_{subscript}")
    sigma = model.random_variables.covariance_matrix
    for row in range(sigma.rows):
        for col in range(sigma.cols):
            if col > row:
                break
            elt = sigma[row, col]
            if elt == 0:
                continue
            subscript = get_2d_subscript(elt, row + 1, col + 1, named_subscripts)
            subs[elt] = sympy.Symbol(f"sigma_{subscript}")
    for i, eta in enumerate(model.random_variables.etas.names, start=1):
        subscript = get_subscript(eta, i, named_subscripts)
        subs[sympy.Symbol(eta)] = sympy.Symbol(f"eta_{subscript}")
    for i, epsilon in enumerate(model.random_variables.epsilons.names, start=1):
        subscript = get_subscript(epsilon, i, named_subscripts)
        subs[sympy.Symbol(epsilon)] = sympy.Symbol(f"epsilon_{subscript}")
    model.statements = model.statements.subs(subs)
    return model


def get_individual_parameters(model: Model, level: str = 'all') -> List[str]:
    """Retrieves all parameters with IIV or IOV in :class:`pharmpy.model`.

    Parameters
    ----------
    model : Model
        Pharmpy model to retrieve the individuals parameters from

    level : str
        The variability level to look for: 'iiv', 'iov', or 'all' (default)

    Return
    ------
    list[str]
        A list of the parameter names as strings

    Example
    -------
    >>> from pharmpy.modeling import *
    >>> model = load_example_model("pheno")
    >>> get_individual_parameters(model)
    ['CL', 'V']
    >>> get_individual_parameters(model, 'iiv')
    ['CL', 'V']
    >>> get_individual_parameters(model, 'iov')
    []

    See also
    --------
    get_pk_parameters
    get_rv_parameters
    has_random_effect

    """

    rvs = _rvs(model, level)

    assignments = _get_natural_assignments(model.statements.before_odes)

    free_symbols = {assignment.symbol for assignment in assignments}

    dependency_graph = _dependency_graph(assignments)

    return sorted(
        map(
            str,
            _filter_symbols(
                dependency_graph,
                free_symbols,
                set().union(
                    *(rvs[rv].free_symbols for rv in rvs.names if rvs[rv].get_variance(rv) != 0)
                ),
            ),
        )
    )


def _rvs(model: Model, level: str):
    if level == 'iiv':
        return model.random_variables.iiv
    if level == 'iov':
        return model.random_variables.iov
    if level == 'all':
        return model.random_variables.etas

    raise ValueError(f'Cannot handle level `{level}`')


def _depends_on_any_of(
    assignments: Statements, symbol: sympy.Symbol, symbols: Iterable[sympy.Symbol]
):
    dependency_graph = _dependency_graph(assignments)
    if symbol not in dependency_graph:
        raise KeyError(symbol)

    # NOTE Could be faster by returning immediately once found
    return not _reachable_from({symbol}, lambda x: dependency_graph.get(x, [])).isdisjoint(symbols)


def has_random_effect(model: Model, parameter: str, level: str = 'all') -> bool:
    """Decides whether the given parameter of a :class:`pharmpy.model` has a
    random effect.

    Parameters
    ----------
    model : Model
        Input Pharmpy model
    parameter: str
        Input parameter
    level : str
        The variability level to look for: 'iiv', 'iov', or 'all' (default)

    Return
    ------
    bool
        Whether the given parameter has a random effect

    Example
    -------
    >>> from pharmpy.modeling import *
    >>> model = load_example_model("pheno")
    >>> has_random_effect(model, 'S1')
    True
    >>> has_random_effect(model, 'CL', 'iiv')
    True
    >>> has_random_effect(model, 'CL', 'iov')
    False

    See also
    --------
    get_individual_parameters
    get_rv_parameters

    """

    rvs = _rvs(model, level)
    symbol = sympy.Symbol(parameter)
    return _depends_on_any_of(model.statements.before_odes, symbol, map(sympy.Symbol, rvs.names))


def get_rv_parameters(model: Model, rv: str) -> List[str]:
    """Retrieves parameters in :class:`pharmpy.model` given a random variable.

    Parameters
    ----------
    model : Model
        Pharmpy model to retrieve parameters from
    rv : str
        Name of random variable to retrieve

    Return
    ------
    list[str]
        A list of parameter names for the given random variable

    Example
    -------
    >>> from pharmpy.modeling import *
    >>> model = load_example_model("pheno")
    >>> get_rv_parameters(model, 'ETA(1)')
    ['CL']

    See also
    --------
    has_random_effect
    get_pk_parameters
    get_individual_parameters

    """
    if rv not in model.random_variables.names:
        raise ValueError(f'Could not find random variable: {rv}')

    natural_assignments = _get_natural_assignments(model.statements.before_odes)

    free_symbols = model.statements.free_symbols
    dependency_graph = _dependency_graph(natural_assignments)
    return sorted(map(str, _filter_symbols(dependency_graph, free_symbols, {sympy.Symbol(rv)})))


def get_pk_parameters(model: Model, kind: str = 'all') -> List[str]:
    """Retrieves PK parameters in :class:`pharmpy.model`.

    Parameters
    ----------
    model : Model
        Pharmpy model to retrieve the PK parameters from

    kind : str
        The type of parameter to retrieve: 'absorption', 'distribution',
        'elimination', or 'all' (default).

    Return
    ------
    list[str]
        A list of the PK parameter names of the given model

    Example
    -------
    >>> from pharmpy.modeling import *
    >>> model = load_example_model("pheno")
    >>> get_pk_parameters(model)
    ['CL', 'V']
    >>> get_pk_parameters(model, 'absorption')
    []
    >>> get_pk_parameters(model, 'distribution')
    ['V']
    >>> get_pk_parameters(model, 'elimination')
    ['CL']

    See also
    --------
    get_individual_parameters
    get_rv_parameters

    """
    natural_assignments = _get_natural_assignments(model.statements.before_odes)
    cs_remapped = _remap_compartmental_system(model.statements, natural_assignments)

    free_symbols = set(_pk_free_symbols(cs_remapped, kind))

    dependency_graph = _dependency_graph(natural_assignments)

    return sorted(map(str, _filter_symbols(dependency_graph, free_symbols)))


def _get_natural_assignments(before_odes):
    # Return assignments where assignments that are constants (e.g. X=1),
    # single length expressions (e.g. S1=V), and divisions between parameters
    # (e.g. K=CL/V) have been filtered out
    classified_assignments = list(_classify_assignments(list(_assignments(before_odes))))
    natural_assignments = list(_remove_synthetic_assignments(classified_assignments))
    return natural_assignments


def _remap_compartmental_system(sset, natural_assignments):
    # Return compartmental system where rates that are synthetic assignments
    # have been substituted with their full definition (e.g K -> CL/V)
    cs = sset.ode_system.to_compartmental_system()

    assignments = list(_assignments(sset.before_odes))
    for assignment in reversed(assignments):
        # FIXME can be made more general, doesn't cover cases with recursively defined symbols (e.g. V=V/2)
        if assignment not in natural_assignments:
            # NOTE Substitution must be made in this order
            cs = cs.subs({assignment.symbol: assignment.expression})
    return cs


def _pk_free_symbols(cs: CompartmentalSystem, kind: str) -> Iterable[sympy.Symbol]:

    if kind == 'all':
        return cs.free_symbols

    if kind == 'absorption':
        return (
            []
            if cs.dosing_compartment == cs.central_compartment
            else _pk_free_symbols_from_compartment(cs, cs.dosing_compartment)
        )

    if kind == 'distribution':
        return _pk_free_symbols_from_compartment(cs, cs.central_compartment)

    if kind == 'elimination':
        return _pk_free_symbols_from_compartment(cs, cs.output_compartment)

    raise ValueError(f'Cannot handle kind `{kind}`')


def _pk_free_symbols_from_compartment(
    cs: CompartmentalSystem, compartment: Compartment
) -> Iterable[sympy.Symbol]:
    vertices = _get_component(cs, compartment)
    edges = _get_component_edges(cs, vertices)
    is_central = compartment == cs.central_compartment
    return _get_component_free_symbols(is_central, vertices, edges)


def _get_component(cs: CompartmentalSystem, compartment: Compartment) -> Set[Compartment]:

    central_component_vertices = _strongly_connected_component_of(
        cs.central_compartment,
        lambda u: map(lambda flow: flow[0], cs.get_compartment_outflows(u)),
        lambda u: map(lambda flow: flow[0], cs.get_compartment_inflows(u)),
    )

    if compartment == cs.central_compartment:
        return central_component_vertices

    flows = (
        cs.get_compartment_inflows
        if compartment == cs.output_compartment
        else cs.get_compartment_outflows
    )

    return _reachable_from(
        {compartment},
        lambda u: filterfalse(
            central_component_vertices.__contains__,
            map(lambda flow: flow[0], flows(u)),
        ),
    )


def _get_component_edges(cs: CompartmentalSystem, vertices: Set[Compartment]):
    return (
        ((u, v, rate) for v in vertices for u, rate in cs.get_compartment_inflows(v))
        if cs.output_compartment in vertices
        else ((u, v, rate) for u in vertices for v, rate in cs.get_compartment_outflows(u))
    )


def _get_component_free_symbols(
    is_central: bool,
    vertices: Set[Compartment],
    edges: Iterable[Tuple[Compartment, Compartment, sympy.Expr]],
) -> Iterable[sympy.Symbol]:

    for (u, v, rate) in edges:
        # NOTE These must not necessarily be outgoing edges
        assert u in vertices or v in vertices

        if u not in vertices or v not in vertices:
            # NOTE This handles splitting the rate K = CL / V
            if len(rate.free_symbols) == 2:
                a, b = rate.free_symbols
                if rate == a / b:
                    yield a if v in vertices else b
                    continue
                elif rate == b / a:
                    yield b if v in vertices else a
                    continue

        if (u in vertices and v in vertices) or not is_central:
            # NOTE This handles all internal edges, and in/out rates (KA, CL/V)
            yield from rate.free_symbols

    for node in vertices:
        yield from node.free_symbols


def _assignments(sset: Statements):
    return filter(lambda statement: isinstance(statement, Assignment), sset)


def _filter_symbols(
    dependency_graph: Dict[sympy.Symbol, Set[sympy.Symbol]],
    roots: Set[sympy.Symbol],
    leaves: Union[Set[sympy.Symbol], None] = None,
) -> Set[sympy.Symbol]:

    dependents = _graph_inverse(dependency_graph)

    free_symbols = _reachable_from(roots, lambda x: dependency_graph.get(x, []))

    reachable = (
        free_symbols
        if leaves is None
        else (
            _reachable_from(
                leaves,
                lambda x: dependents.get(x, []),
            ).intersection(free_symbols)
        )
    )

    return reachable.difference(dependents.keys()).intersection(dependency_graph.keys())


def _classify_assignments(assignments: Sequence[Assignment]):

    dependencies = _dependency_graph(assignments)

    # Keep all symbols that have dependencies (e.g. remove constants X=1)
    symbols = set(filter(dependencies.__getitem__, dependencies.keys()))

    for assignment in assignments:

        symbol = assignment.symbol
        expression = assignment.expression
        fs = expression.free_symbols

        if symbol not in fs:  # NOTE We skip redefinitions (e.g. CL=CL+1)
            if len(fs) == 1:
                a = next(iter(fs))
                if a in symbols:
                    yield 'synthetic', assignment  # E.g. S1=V
                    continue
            elif len(fs) == 2:
                it = iter(fs)
                a = next(it)
                b = next(it)
                if a in symbols and b in symbols and (expression == a / b or expression == b / a):
                    yield 'synthetic', assignment  # E.g. K=CL/V
                    continue

        yield 'natural', assignment


def _remove_synthetic_assignments(classified_assignments: List[Tuple[str, Assignment]]):

    assignments = []
    last_defined = {}

    for t, assignment in reversed(classified_assignments):
        if t == 'synthetic':
            substitution_starts_at_index = last_defined.get(assignment.symbol, 0)
            assignments = [
                succeeding
                if i < substitution_starts_at_index
                else Assignment(
                    succeeding.symbol,
                    subs(
                        succeeding.expression,
                        {assignment.symbol: assignment.expression},
                        simultaneous=True,
                    ),
                )
                for i, succeeding in enumerate(assignments)
            ]
        else:
            last_defined[assignment.symbol] = len(assignments)
            assignments.append(assignment)

    return reversed(assignments)


def _dependency_graph(assignments: Sequence[Assignment]):

    dependencies = {}

    for assignment in assignments:

        symbol = assignment.symbol
        fs = assignment.expression.free_symbols

        previous_def = dependencies.get(symbol)
        dependencies[symbol] = fs

        if previous_def is not None:
            # NOTE This handles redefinition of symbols by expanding
            # the previous definition of symbol into existing definitions
            for key, value in dependencies.items():
                if symbol in value:
                    dependencies[key] = (value - {symbol}) | previous_def

    return dependencies


def _graph_inverse(g: Dict[T, Set[U]]) -> Dict[U, Set[T]]:

    h = {}

    for left, deps in g.items():
        for right in deps:
            if right in h:
                h[right].add(left)
            else:
                h[right] = {left}

    return h


def _reachable_from(start_nodes: Set[T], neighbors: Callable[[T], Iterable[T]]) -> Set[T]:
    queue = list(start_nodes)
    closure = set(start_nodes)
    while queue:
        u = queue.pop()
        n = neighbors(u)
        for v in n:
            if v not in closure:
                queue.append(v)
                closure.add(v)

    return closure


def _strongly_connected_component_of(
    vertex: T, successors: Callable[[T], Iterable[T]], predecessors: Callable[[T], Iterable[T]]
):

    forward_reachable = _reachable_from({vertex}, successors)

    # NOTE This searches for backward reachable vertices on the graph induced
    # by the forward reachable vertices and is equivalent to (but less wasteful
    # than) first computing the backward reachable vertices on the original
    # graph and then computing the intersection with the forward reachable
    # vertices.
    return _reachable_from(
        {vertex},
        lambda u: filter(forward_reachable.__contains__, predecessors(u)),
    )
