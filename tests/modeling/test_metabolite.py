from pharmpy.modeling import (
    add_metabolite,
    add_peripheral_compartment,
    has_presystemic_metabolite,
    remove_peripheral_compartment,
)


def test_add_metabolite(testdata, load_model_for_test):
    model = load_model_for_test(testdata / 'nonmem' / 'models' / 'pheno_conc.mod')
    model = add_metabolite(model)
    odes = model.statements.ode_system
    assert odes.compartment_names == ['CENTRAL', 'METABOLITE']
    assert not has_presystemic_metabolite(model)
    a = model.model_code.split('\n')
    assert a[20] == 'IF (DVID.EQ.1) THEN'
    assert a[21] == '    Y = Y'
    assert a[22] == 'ELSE'
    assert a[23] == '    Y = Y_M'
    assert a[24] == 'END IF'

    assert odes.central_compartment.name == 'CENTRAL'

def test_presystemic_metabolite(testdata, load_model_for_test):
    model = load_model_for_test(testdata / 'nonmem' / 'models' / 'pheno_conc.mod')
    model = add_metabolite(model, presystemic=True)
    odes = model.statements.ode_system

    assert odes.compartment_names == ['DEPOT', 'CENTRAL', 'METABOLITE']

    depot = odes.find_depot(model.statements)
    central = odes.central_compartment
    metabolite = odes.find_compartment("METABOLITE")

    assert has_presystemic_metabolite(model)
    assert odes.get_flow(depot, central)
    assert odes.get_flow(depot, metabolite)
    assert odes.get_flow(central, metabolite)

    assert odes.central_compartment.name == 'CENTRAL'