import sys

import pytest

from pharmpy.deps import pandas as pd
from pharmpy.internals.fs.cwd import chdir
from pharmpy.model import NormalDistribution
from pharmpy.modeling import (
    add_iiv,
    add_individual_parameter,
    add_peripheral_compartment,
    add_pk_iiv,
    create_joint_distribution,
    fix_parameters,
)
from pharmpy.tools import read_modelfit_results, retrieve_models, run_iivsearch
from pharmpy.tools.iivsearch.algorithms import (
    _create_param_dict,
    _is_rv_block_structure,
    _rv_block_structures,
    create_eta_blocks,
    td_exhaustive_block_structure,
    td_exhaustive_no_of_etas,
)
from pharmpy.tools.iivsearch.tool import create_workflow, validate_input
from pharmpy.workflows import Workflow

tflite_condition = (
    sys.version_info >= (3, 12)
    and sys.platform == 'win32'
    or sys.version_info >= (3, 12)
    and sys.platform == 'darwin'
)


@pytest.mark.parametrize(
    'list_of_parameters, expected_values',
    [([], 4), (['IVCL'], 1), (["IVCL", "IVV"], 0)],
)
def test_td_exhaustive_block_structure_ignore_fixed_params(
    load_model_for_test, testdata, list_of_parameters, expected_values
):
    model = load_model_for_test(testdata / 'nonmem' / 'pheno_real.mod')
    model = add_individual_parameter(model, 'PD1')
    model = add_iiv(model, 'PD1', 'exp')
    model = fix_parameters(model, list_of_parameters)
    wf = td_exhaustive_block_structure(model)
    fit_tasks = [task.name for task in wf.tasks if task.name.startswith('run')]
    assert len(fit_tasks) == expected_values


@pytest.mark.parametrize(
    'list_of_parameters, expected_values',
    [([], 3), (['CL'], 1), (["CL", "V"], 0)],
)
def test_brute_force_no_of_etas_keep(
    load_model_for_test, testdata, list_of_parameters, expected_values
):
    model = load_model_for_test(testdata / 'nonmem' / 'pheno_real.mod')
    wf = td_exhaustive_no_of_etas(model, keep=list_of_parameters)
    fit_tasks = [task.name for task in wf.tasks if task.name.startswith('run')]
    assert len(fit_tasks) == expected_values


def test_brute_force_no_of_etas_fixed(load_model_for_test, testdata):
    model = load_model_for_test(testdata / 'nonmem' / 'pheno_real.mod')
    model = fix_parameters(model, 'IVCL')
    wf = td_exhaustive_no_of_etas(model)
    fit_tasks = [task.name for task in wf.tasks if task.name.startswith('run')]
    assert len(fit_tasks) == 1


@pytest.mark.parametrize(
    'list_of_parameters, no_of_models',
    [([], 7), (['QP1'], 15)],
)
def test_brute_force_no_of_etas(load_model_for_test, testdata, list_of_parameters, no_of_models):
    model = load_model_for_test(testdata / 'nonmem' / 'models' / 'mox2.mod')
    model = add_peripheral_compartment(model)
    model = add_iiv(model, list_of_parameters, 'add')
    wf = td_exhaustive_no_of_etas(model)
    fit_tasks = [task.name for task in wf.tasks if task.name.startswith('run')]

    assert len(fit_tasks) == no_of_models


@pytest.mark.parametrize(
    'list_of_parameters, block_structure, no_of_models',
    [([], [], 4), (['QP1'], [], 14), ([], ['ETA_1', 'ETA_2'], 4)],
)
def test_brute_force_block_structure(
    load_model_for_test, testdata, list_of_parameters, block_structure, no_of_models
):
    model = load_model_for_test(testdata / 'nonmem' / 'models' / 'mox2.mod')
    res = read_modelfit_results(testdata / 'nonmem' / 'models' / 'mox2.mod')
    model = add_peripheral_compartment(model)
    model = add_iiv(model, list_of_parameters, 'add')
    if block_structure:
        model = create_joint_distribution(
            model, block_structure, individual_estimates=res.individual_estimates
        )

    wf = td_exhaustive_block_structure(model)
    fit_tasks = [task.name for task in wf.tasks if task.name.startswith('run')]

    assert len(fit_tasks) == no_of_models


def test_rv_block_structures_4_etas(load_model_for_test, pheno_path):
    model = load_model_for_test(pheno_path)
    model = add_iiv(model, ['TAD', 'S1'], 'exp')

    block_structures = list(_rv_block_structures(model.random_variables.iiv.names))

    assert len(block_structures) == 15

    block_structures_integer_partitions = [
        tuple(map(len, block_structure)) for block_structure in block_structures
    ]
    assert block_structures_integer_partitions.count((4,)) == 1
    assert block_structures_integer_partitions.count((1, 3)) == 4
    assert block_structures_integer_partitions.count((2, 2)) == 3
    assert block_structures_integer_partitions.count((1, 1, 2)) == 6
    assert block_structures_integer_partitions.count((1, 1, 1, 1)) == 1


def test_rv_block_structures_5_etas(load_model_for_test, pheno_path):
    model = load_model_for_test(pheno_path)
    model = add_iiv(model, ['TVCL', 'TAD', 'S1'], 'exp')

    block_structures = list(_rv_block_structures(model.random_variables.iiv.names))
    assert len(block_structures) == 52

    block_structures_integer_partitions = [
        tuple(map(len, block_structure)) for block_structure in block_structures
    ]
    assert block_structures_integer_partitions.count((5,)) == 1
    assert block_structures_integer_partitions.count((1, 4)) == 5
    assert block_structures_integer_partitions.count((2, 3)) == 10
    assert block_structures_integer_partitions.count((1, 1, 3)) == 10
    assert block_structures_integer_partitions.count((1, 2, 2)) == 15
    assert block_structures_integer_partitions.count((1, 1, 1, 2)) == 10
    assert block_structures_integer_partitions.count((1, 1, 1, 1, 1)) == 1


def test_is_rv_block_structure(load_model_for_test, pheno_path):
    model = load_model_for_test(pheno_path)
    res = read_modelfit_results(pheno_path)
    model = add_iiv(model, ['TAD', 'S1'], 'exp')

    etas_block_structure = (('ETA_1', 'ETA_2'), ('ETA_TAD',), ('ETA_S1',))
    model = create_joint_distribution(
        model,
        list(etas_block_structure[0]),
        individual_estimates=res.individual_estimates,
    )
    etas = model.random_variables.iiv
    assert _is_rv_block_structure(etas, etas_block_structure, [])

    etas_block_structure = (('ETA_1',), ('ETA_2',), ('ETA_TAD', 'ETA_S1'))
    assert not _is_rv_block_structure(etas, etas_block_structure, [])

    etas_block_structure = (('ETA_1',), ('ETA_2', 'ETA_TAD'), ('ETA_S1',))
    assert not _is_rv_block_structure(etas, etas_block_structure, [])

    model = create_joint_distribution(model, individual_estimates=res.individual_estimates)
    etas_block_structure = (('ETA_1', 'ETA_2', 'ETA_TAD', 'ETA_S1'),)
    etas = model.random_variables.iiv
    assert _is_rv_block_structure(etas, etas_block_structure, [])


def test_create_joint_dist(load_model_for_test, testdata):
    model = load_model_for_test(testdata / 'nonmem' / 'models' / 'mox2.mod')
    res = read_modelfit_results(testdata / 'nonmem' / 'models' / 'mox2.mod')

    model = add_peripheral_compartment(model)
    model = add_pk_iiv(model)
    etas_block_structure = (('ETA_1', 'ETA_2'), ('ETA_QP1',), ('ETA_VP1',))
    model = create_eta_blocks(etas_block_structure, model, res)
    assert len(model.random_variables.iiv) == 4

    model = load_model_for_test(testdata / 'nonmem' / 'models' / 'mox2.mod')
    model = add_peripheral_compartment(model)
    model = add_pk_iiv(model)
    model = create_joint_distribution(
        model,
        ['ETA_1', 'ETA_2'],
        individual_estimates=res.individual_estimates,
    )
    etas_block_structure = (('ETA_1',), ('ETA_2',), ('ETA_3', 'ETA_VP1', 'ETA_QP1'))
    model = create_eta_blocks(etas_block_structure, model, res)
    assert len(model.random_variables.iiv) == 3


def test_get_param_names(create_model_for_test, load_model_for_test, testdata):
    model = load_model_for_test(testdata / 'nonmem' / 'models' / 'mox2.mod')

    param_dict = _create_param_dict(model, model.random_variables.iiv)
    param_dict_ref = {'ETA_1': 'CL', 'ETA_2': 'VC', 'ETA_3': 'MAT'}

    assert param_dict == param_dict_ref

    model_code = model.model_code.replace(
        'CL = THETA(1) * EXP(ETA(1))', 'ETA_1 = ETA(1)\nCL = THETA(1) * EXP(ETA_1)'
    )
    model = create_model_for_test(model_code)

    param_dict = _create_param_dict(model, model.random_variables.iiv)

    assert param_dict == param_dict_ref


def test_create_workflow():
    assert isinstance(create_workflow('top_down_exhaustive'), Workflow)


def test_create_workflow_with_model(load_model_for_test, testdata):
    model = load_model_for_test(testdata / 'nonmem' / 'pheno.mod')
    assert isinstance(create_workflow('top_down_exhaustive', model=model), Workflow)


def test_validate_input():
    validate_input('top_down_exhaustive')


def test_validate_input_with_model(load_model_for_test, testdata):
    model = load_model_for_test(testdata / 'nonmem' / 'pheno.mod')
    validate_input('top_down_exhaustive', model=model)


@pytest.mark.parametrize(
    ('model_path', 'arguments', 'exception', 'match'),
    [
        (None, dict(algorithm=1), ValueError, 'Invalid `algorithm`'),
        (None, dict(algorithm='brute_force_no_of_eta'), ValueError, 'Invalid `algorithm`'),
        (None, dict(rank_type=1), ValueError, 'Invalid `rank_type`'),
        (None, dict(rank_type='bi'), ValueError, 'Invalid `rank_type`'),
        (None, dict(iiv_strategy=['no_add']), ValueError, 'Invalid `iiv_strategy`'),
        (None, dict(iiv_strategy='diagonal'), ValueError, 'Invalid `iiv_strategy`'),
        (None, dict(cutoff='1'), TypeError, 'Invalid `cutoff`'),
        (
            None,
            dict(model=1),
            TypeError,
            'Invalid `model`',
        ),
    ],
)
def test_validate_input_raises(
    load_model_for_test,
    testdata,
    model_path,
    arguments,
    exception,
    match,
):
    model = load_model_for_test(testdata.joinpath(*model_path)) if model_path else None

    harmless_arguments = dict(
        algorithm='top_down_exhaustive',
    )

    kwargs = {**harmless_arguments, 'model': model, **arguments}

    with pytest.raises(exception, match=match):
        validate_input(**kwargs)


@pytest.mark.skipif(tflite_condition, reason="Skipping tests requiring tflite for Python 3.12")
def test_no_of_etas_keep(tmp_path, load_model_for_test, testdata):
    model = load_model_for_test(testdata / 'nonmem' / 'models' / 'mox2.mod')
    results = read_modelfit_results(testdata / 'nonmem' / 'models' / 'mox2.mod')
    with chdir(tmp_path):
        res_keep1 = run_iivsearch(
            'top_down_exhaustive',
            results=results,
            model=model,
            keep=["CL"],
            estimation_tool='dummy',
            correlation_algorithm='skip',
        )
        no_of_models = 8
        assert len(res_keep1.summary_models) == no_of_models // 2
        assert res_keep1.summary_individuals.iloc[-1]['description'] == '[CL]'


@pytest.mark.skipif(tflite_condition, reason="Skipping tests requiring tflite for Python 3.12")
def test_block_structure(tmp_path, load_model_for_test, testdata):
    model = load_model_for_test(testdata / 'nonmem' / 'models' / 'mox2.mod')
    results = read_modelfit_results(testdata / 'nonmem' / 'models' / 'mox2.mod')
    with chdir(tmp_path):
        res = run_iivsearch(
            'skip',
            results=results,
            model=model,
            estimation_tool='dummy',
            correlation_algorithm='top_down_exhaustive',
        )

        no_of_candidate_models = 4
        assert len(res.summary_tool) == no_of_candidate_models + 1
        assert len(res.summary_models) == no_of_candidate_models + 1

        res_models = [model for model in retrieve_models(res) if model.name != 'input_model']
        assert len(res_models) == no_of_candidate_models

        start_model = model
        assert all(model.random_variables != start_model.random_variables for model in res_models)

        assert res.summary_tool.loc[1, 'mox2']['description'] == '[CL]+[VC]+[MAT]'
        assert isinstance(start_model.random_variables['ETA_1'], NormalDistribution)

        assert res.summary_tool.loc[1, 'iivsearch_run1']['description'] == '[CL,VC,MAT]'
        assert len(res_models[0].random_variables['ETA_1'].names) == 3

        summary_tool_sorted_by_dbic = res.summary_tool.sort_values(by=['dbic'], ascending=False)
        summary_tool_sorted_by_bic = res.summary_tool.sort_values(by=['bic'])
        summary_tool_sorted_by_rank = res.summary_tool.sort_values(by=['rank'])
        pd.testing.assert_frame_equal(summary_tool_sorted_by_dbic, summary_tool_sorted_by_rank)
        pd.testing.assert_frame_equal(summary_tool_sorted_by_dbic, summary_tool_sorted_by_bic)

        rundir = tmp_path / 'iivsearch_dir1'
        assert rundir.is_dir()
        assert (rundir / 'metadata.json').exists()


@pytest.mark.parametrize(
    ('algorithm', 'correlation_algorithm', 'no_of_candidate_models'),
    (('top_down_exhaustive', 'skip', 7), ('bottom_up_stepwise', 'skip', 4)),
)
@pytest.mark.skipif(tflite_condition, reason="Skipping tests requiring tflite for Python 3.12")
def test_no_of_etas(
    tmp_path,
    load_model_for_test,
    testdata,
    algorithm,
    correlation_algorithm,
    no_of_candidate_models,
):
    model = load_model_for_test(testdata / 'nonmem' / 'models' / 'mox2.mod')
    results = read_modelfit_results(testdata / 'nonmem' / 'models' / 'mox2.mod')
    with chdir(tmp_path):
        res = run_iivsearch(
            algorithm,
            results=results,
            model=model,
            correlation_algorithm=correlation_algorithm,
            estimation_tool='dummy',
        )

        assert len(res.summary_tool) == no_of_candidate_models + 1
        assert len(res.summary_models) == no_of_candidate_models + 1

        res_models = [model for model in retrieve_models(res) if model.name != 'input_model']
        assert len(res_models) == no_of_candidate_models

        assert res.summary_tool.loc[1, 'mox2']['description'] == '[CL]+[VC]+[MAT]'
        assert model.random_variables.iiv.names == ['ETA_1', 'ETA_2', 'ETA_3']

        summary_tool_sorted_by_dbic = res.summary_tool.sort_values(by=['dbic'], ascending=False)
        summary_tool_sorted_by_bic = res.summary_tool.sort_values(by=['bic'])
        summary_tool_sorted_by_rank = res.summary_tool.sort_values(by=['rank'])
        pd.testing.assert_frame_equal(summary_tool_sorted_by_dbic, summary_tool_sorted_by_rank)
        pd.testing.assert_frame_equal(summary_tool_sorted_by_dbic, summary_tool_sorted_by_bic)

        rundir = tmp_path / 'iivsearch_dir1'
        assert rundir.is_dir()
        assert (rundir / 'metadata.json').exists()
