import pharmpy.model
from pharmpy.deps import sympy
from .CodeGenerator import CodeGenerator

def find_term(model: pharmpy.model, expr: sympy.Add) -> tuple[sympy.Symbol or sympy.Add, dict]:
    """
    For a given expression for the dependent variable, find the terms 
    connected to the actual result and the terms connected to the error model.

    Parameters
    ----------
    model : pharmpy.model
        A pharmpy model object
    expr : sympy.Add
        An expression for the dependent variable. Should be a sympy.Add statement

    Raises
    ------
    ValueError
        If the model either has multiple additative- or proportional error 
        terms, the function will raise a ValueError

    Returns
    -------
    res : sympy.Symbol or sympy.Add
        will return a sympy statement. Either a symbol or Add depending on the 
        state of the res
    errors_add_prop : dict
        A dictionary with two keys. One called "add" containing the additative
        error term (if found, otherwise None) and one called "prop" containing the 
        proportional error term (if found, otherwise None)

    """
    errors = []
    
    terms = sympy.Add.make_args(expr)
    for term in terms:
        error_term = False
        for symbol in term.free_symbols:
            if str(symbol) in model.random_variables.epsilons.names:
                error_term = True
            
        if error_term:
            errors.append(term)
        else:
            if "res"  not in locals():
                res = term
            else:
                res = res + term
    
    errors_add_prop = {"add": None, "prop": None}
    
    prop = False
    res_alias = find_aliases(res, model)
    for term in errors:
        for symbol in term.free_symbols:
            for ali in find_aliases(symbol, model):
                if ali in res_alias:
                    prop = True
                    # Remove the symbol that was found
                    # and substitute res to that symbol to avoid confusion
                    term = term.subs(symbol,1)
                    res = symbol
            
        if prop:
            if errors_add_prop["prop"] is None:
                errors_add_prop["prop"] = term    f
            else:
                raise ValueError("Multiple proportional error terms found. Check format of error model")
        else:
            if errors_add_prop["add"] is None:
                errors_add_prop["add"] = term
            else:
                pass
                #raise ValueError("Multiple additive error term found. Check format of error model")
    
    for pair in errors_add_prop.items():
        key = pair[0]
        term = pair[1]
        if term != None:
            term = convert_eps_to_sigma(term, model)
        errors_add_prop[key] = term
        
    return res, errors_add_prop

def add_error_model(cg: CodeGenerator,
                    expr: sympy.Symbol or sympy.Add,
                    error: dict,
                    symbol: str,
                    force_add: bool = False,
                    force_prop: bool = False,
                    force_comb: bool = False
                    ) -> None:
    """
    Adds an error parameter to the model code if needed. This is only needed if
    the error model follows non-convential syntax. If the error model follows 
    convential format. Nothing is added

    Parameters
    ----------
    cg : CodeGenerator
        Codegenerator object holding the code to be added to.
    expr : sympy.Symbol or sympy.Add
        Expression for the dependent variable.
    error : dict
        Dictionary with additive and proportional error terms.
    symbol : str
        Symbol of dependent variable.
    force_add : bool, optional
        If known error model, this can be set to force the error model to be 
        an additive one. The default is False.
    force_prop : bool, optional
        If known error model, this can be set to force the error model to be 
        an proportional one. The default is False.
    force_comb : bool, optional
        If known error model, this can be set to force the error model to be 
        an combination based. The default is False.

    Raises
    ------
    ValueError
        Will raise ValueError if model has defined error model that does not
        match the format of the found error terms.

    Returns
    -------
    None
        Modifies the given CodeGenerator object. Returns nothing
    
    Example
    -------
    TODO
        
    """
    cg.add(f'{symbol} <- {expr}')
    
    if force_add:
        assert error["prop"] is None
        
        if error["add"]:
            if not isinstance(error["add"], sympy.Symbol):
                cg.add(f'add_error <- {error["add"]}')
        else:
            raise ValueError("Model should have additive error but no such error was found.")
    elif force_prop:
        assert error["add"] is None
        
        if error["prop"]:
            if not isinstance(error["prop"], sympy.Symbol):
                cg.add(f'prop_error <- {error["prop"]}')
        else:
            raise ValueError("Model should have proportional error but no such error was found.")
    elif force_comb:
        assert error["add"] is not None and error["prop"] is not None
        
        if error["add"]:
            if not isinstance(error["add"], sympy.Symbol):
                cg.add(f'add_error <- {error["add"]}')
        else:
            raise ValueError("Model should have additive error but no such error was found.")
            
        if error["prop"]:
            if not isinstance(error["prop"], sympy.Symbol):
                cg.add(f'prop_error <- {error["prop"]}')
        else:
            raise ValueError("Model should have proportional error but no such error was found.")
    else:
        # Add term for the additive and proportional error (if exist)
        # as solution for nlmixr error model handling
        if error["add"]:
            if not isinstance(error["add"], sympy.Symbol):
                cg.add(f'add_error <- {error["add"]}')
        if error["prop"]:
            if not isinstance(error["prop"], sympy.Symbol):
                cg.add(f'prop_error <- {error["prop"]}')
        
def add_error_relation(cg: CodeGenerator, error: dict, symbol: str) -> None:
    """
    Add a code line in nlmixr2 deciding the error model of the dependent variable

    Parameters
    ----------
    cg : CodeGenerator
        Codegenerator object holding the code to be added to.
    error : dict
        Dictionary with additive and proportional error terms.
    symbol : str
        Symbol of dependent variable.

    Returns
    -------
    None
        Modifies the given CodeGenerator object. Returns nothing

    """
    # Add the actual error model depedent on the previously
    # defined variable add_error and prop_error
    if isinstance(error["add"], sympy.Symbol):
        add_error = error["add"]
    else:
        add_error = "add_error"
    if isinstance(error["prop"], sympy.Symbol):
        prop_error = error["prop"]
    else:
        prop_error = "prop_error"
    
        
    if error["add"] and error["prop"]:
        cg.add(f'{symbol} ~ add({add_error}) + prop({prop_error})')
    elif error["add"] and not error["prop"]:
        cg.add(f'{symbol} ~ add({add_error})')
    elif not error["add"] and error["prop"]:
        cg.add(f'{symbol} ~ prop({prop_error})')
        
def find_aliases(symbol:str, model: pharmpy.model) -> list:
    """
    Returns a list of all variable names that are the same as the inputed symbol

    Parameters
    ----------
    symbol : str
        The name of the variable to find aliases to.
    model : pharmpy.model
        A model by which the inputed symbol is related to.

    Returns
    -------
    list
        A list of aliases for the symbol.

    """
    aliases = [symbol]
    for expr in model.statements.after_odes:
        if symbol == expr.symbol and isinstance(expr.expression, sympy.Symbol):
            aliases.append(expr.expression)
        if symbol == expr.symbol and expr.expression.is_Piecewise:
            for e, c in expr.expression.args:
                if isinstance(e, sympy.Symbol):
                    aliases.append(e)
    return aliases

def convert_eps_to_sigma(expr: sympy.Symbol or sympy.Mul, model: pharmpy.model) -> sympy.Symbol or sympy.Mul:
    """
    Change the use of epsilon names to sigma names instead. Mostly used for 
    converting NONMEM format to nlmxir2

    Parameters
    ----------
    expr : sympy.Symbol or sympy.Mul
        A sympy term to change a variable name in
    model : pharmpy.Model
        A pharmpy model object

    Returns
    -------
    TYPE : sympy.Symbol or sympy.Mul
        Same expression as inputed, but with epsilon names changed to sigma.

    """
    eps_to_sigma = {sympy.Symbol(eps.names[0]): sympy.Symbol(str(eps.variance)) for eps in model.random_variables.epsilons}
    return expr.subs(eps_to_sigma)