import re

from pharmpy import data
from pharmpy.statements import CompartmentalSystem, ExplicitODESystem, ModelStatements, ODESystem
from pharmpy.symbols import symbol


def update_parameters(model, old, new):
    new_names = {p.name for p in new}
    old_names = {p.name for p in old}
    removed = old_names - new_names
    if removed:
        remove_records = []
        next_theta = 1
        for theta_record in model.control_stream.get_records('THETA'):
            current_names = theta_record.name_map.keys()
            if removed >= current_names:
                remove_records.append(theta_record)
            elif not removed.isdisjoint(current_names):
                # one or more in the record
                theta_record.remove(removed & current_names)
                theta_record.renumber(next_theta)
                next_theta += len(theta_record)
            else:
                # keep all
                theta_record.renumber(next_theta)
                next_theta += len(theta_record)
        model.control_stream.remove_records(remove_records)

    for p in new:
        name = p.name
        if name not in model._old_parameters and \
                name not in model.random_variables.all_parameters():
            # This is a new theta
            theta_number = get_next_theta(model)
            record = create_theta_record(model, p)
            if re.match(r'THETA\(\d+\)', name):
                p.name = f'THETA({theta_number})'
            else:
                record.add_nonmem_name(name, theta_number)

    next_theta = 1
    for theta_record in model.control_stream.get_records('THETA'):
        theta_record.update(new, next_theta)
        next_theta += len(theta_record)
    next_omega = 1
    previous_size = None
    for omega_record in model.control_stream.get_records('OMEGA'):
        next_omega, previous_size = omega_record.update(new, next_omega, previous_size)
    next_sigma = 1
    previous_size = None
    for sigma_record in model.control_stream.get_records('SIGMA'):
        next_sigma, previous_size = sigma_record.update(new, next_sigma, previous_size)


def update_random_variables(model, old, new):
    new_names = {rv.name for rv in new}
    old_names = {rv.name for rv in old}
    removed = old_names - new_names
    if removed:
        remove_records = []
        next_eta = 1
        for omega_record in model.control_stream.get_records('OMEGA'):
            current_names = omega_record.eta_map.keys()
            if removed >= current_names:
                remove_records.append(omega_record)
            elif not removed.isdisjoint(current_names):
                # one or more in the record
                omega_record.remove(removed & current_names)
                omega_record.renumber(next_eta)
                # FIXME: No handling of OMEGA(1,1) etc in code
                next_eta += len(omega_record)
            else:
                # keep all
                omega_record.renumber(next_eta)
                next_eta += len(omega_record)
        model.control_stream.remove_records(remove_records)


def get_next_theta(model):
    """ Find the next available theta number
    """
    next_theta = 1
    for theta_record in model.control_stream.get_records('THETA'):
        thetas = theta_record.parameters(next_theta)
        next_theta += len(thetas)
    return next_theta


def create_theta_record(model, param):
    param_str = '$THETA  '

    if param.upper < 1000000:
        if param.lower <= -1000000:
            param_str += f'(-INF,{param.init},{param.upper})'
        else:
            param_str += f'({param.lower},{param.init},{param.upper})'
    else:
        if param.lower <= -1000000:
            param_str += f'{param.init}'
        else:
            param_str += f'({param.lower},{param.init})'
    if param.fix:
        param_str += ' FIX'
    param_str += '\n'
    record = model.control_stream.insert_record(param_str, 'THETA')
    return record


def update_ode_system(model, old, new):
    """Update ODE system

       Handle changes from CompartmentSystem to ExplicitODESystem
    """
    if type(old) == CompartmentalSystem and type(new) == ExplicitODESystem:
        subs = model.control_stream.get_records('SUBROUTINES')[0]
        subs.remove_option_startswith('TRANS')
        subs.remove_option_startswith('ADVAN')
        subs.append_option('ADVAN6')
        des = model.control_stream.insert_record('$DES\nDUMMY=0', 'PK')
        des.from_odes(new)
        mod = model.control_stream.insert_record('$MODEL TOL=3\n', 'SUBROUTINES')
        for eq, ic in zip(new.odes[:-1], list(new.ics.keys())[:-1]):
            name = eq.lhs.args[0].name[2:]
            if new.ics[ic] != 0:
                dose = True
            else:
                dose = False
            mod.add_compartment(name, dosing=dose)
    elif type(old) == CompartmentalSystem and type(new) == CompartmentalSystem:
        if old.find_depot() and not new.find_depot():
            subs = model.control_stream.get_records('SUBROUTINES')[0]
            advan = subs.get_option_startswith('ADVAN')
            statements = model.statements
            if advan == 'ADVAN2':
                subs.replace_option('ADVAN2', 'ADVAN1')
            elif advan == 'ADVAN4':
                subs.replace_option('ADVAN4', 'ADVAN3')
                statements.subs({symbol('K23'): symbol('K12'), symbol('K32'): symbol('K32')})
            elif advan == 'ADVAN12':
                subs.replace_option('ADVAN12', 'ADVAN11')
                statements.subs({symbol('K23'): symbol('K12'), symbol('K32'): symbol('K32'),
                                 symbol('K24'): symbol('K13'), symbol('K42'): symbol('K31')})
            elif advan == 'ADVAN5' or advan == 'ADVAN7':
                # FIXME: Add this. Here we can check which compartment name was removed
                pass

            # FIXME: It could possibly be other than the first below
            # also assumes that only one compartment has been removed
            secondary = secondary_pk_param_conversion_map(len(old), 1)
            statements.subs(secondary)
            model.statements = statements


def primary_pk_param_conversion_map(ncomp, trans, removed):
    """Conversion map for pk parameters for one removed compartment
    """
    if trans == 'TRANS1':
        pass


def secondary_pk_param_conversion_map(ncomp, removed):
    """Conversion map for pk parameters for one removed compartment

        ncomp - total number of compartments before removing (including output)
        removed - number of removed compartment
    """
    d = dict()
    for i in range(removed + 1, ncomp + 1):
        d.update({symbol(f'S{i})'): symbol(f'S{i - 1}'),
                  symbol(f'F{i}'): symbol(f'F{i - 1}'),
                  symbol(f'R{i}'): symbol(f'R{i - 1}'),
                  symbol(f'D{i}'): symbol(f'D{i - 1}'),
                  symbol(f'ALAG{i}'): symbol(f'ALAG{i - 1}')})
    return d


def update_statements(model, old, new, trans):
    trans['NaN'] = int(data.conf.na_rep)
    main_statements = ModelStatements()
    error_statements = ModelStatements()
    found_ode = False
    for s in new:
        if isinstance(s, ODESystem):
            found_ode = True
            old_system = old.ode_system
            if s != old_system:
                update_ode_system(model, old_system, s)
        else:
            if found_ode:
                error_statements.append(s)
            else:
                main_statements.append(s)
    main_statements.subs(trans)
    rec = model.get_pred_pk_record()
    rec.statements = main_statements
    error = model._get_error_record()
    if error:
        if len(error_statements) > 0:
            error_statements.pop(0)        # Remove the link statement
        error_statements.subs(trans)
        error.statements = error_statements
