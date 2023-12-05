import shutil
from pathlib import Path

import pytest

from pharmpy.internals.fs.cwd import chdir
from pharmpy.tools import run_amd


def _model_count(rundir: Path):
    return sum(
        map(
            lambda path: 0 if path.name in ['.lock', '.datasets'] else 1,
            ((rundir / 'models').iterdir()),
        )
    )


@pytest.mark.filterwarnings(
    'ignore:.*Adjusting initial estimates to create positive semidefinite omega/sigma matrices.',
    'ignore::UserWarning',
)
def test_amd(tmp_path, testdata):
    with chdir(tmp_path):
        shutil.copy2(testdata / 'nonmem' / 'models' / 'moxo_simulated_amd.csv', '.')
        shutil.copy2(testdata / 'nonmem' / 'models' / 'moxo_simulated_amd.datainfo', '.')
        input = 'moxo_simulated_amd.csv'
        res = run_amd(
            input,
            modeltype='basic_pk',
            administration='oral',
            search_space='PERIPHERALS(1)',
            occasion='VISI',
            strictness='minimization_successful or rounding_errors',
            retries_strategy='skip',
        )

        rundir = tmp_path / 'amd_dir1'
        assert rundir.is_dir()
        assert (rundir / 'results.json').exists()
        assert (rundir / 'results.csv').exists()
        subrundir = [
            'modelfit',
            'modelsearch',
            'iivsearch',
            'ruvsearch',
            'iovsearch',
            'allometry',
            'covsearch_exploratory',
        ]
        for dir in subrundir:
            dir = rundir / dir
            assert _model_count(dir) >= 1

        assert len(res.summary_tool) == len(subrundir)
        assert len(res.summary_models) >= 1
        assert len(res.summary_individuals_count) >= 1


def test_structure_mechanistic_exploratory(tmp_path, testdata):
    with chdir(tmp_path):
        shutil.copy2(testdata / 'nonmem' / 'models' / 'moxo_simulated_amd.csv', '.')
        shutil.copy2(testdata / 'nonmem' / 'models' / 'moxo_simulated_amd.datainfo', '.')
        input = 'moxo_simulated_amd.csv'
        res = run_amd(
            input,
            modeltype='basic_pk',
            administration='oral',
            search_space='COVARIATE(CL,WT,pow);COVARIATE?(VC,AGE,exp);COVARIATE?(MAT,SEX,cat)',
            order=['covariates'],
            mechanistic_covariates=["AGE"],
            occasion='VISI',
            strictness='minimization_successful or rounding_errors',
            retries_strategy='skip',
        )

        rundir = tmp_path / 'amd_dir1'
        assert rundir.is_dir()
        assert (rundir / 'results.json').exists()
        assert (rundir / 'results.csv').exists()
        subrundir = [
            'modelfit',
            'covsearch_structural',
            'covsearch_mechanistic',
            'covsearch_exploratory',
        ]
        for dir in subrundir:
            dir = rundir / dir
            assert _model_count(dir) >= 1

        assert len(res.summary_tool) == len(subrundir) - 1  # Mechanistic/Exploratory grouped as one
        assert len(res.summary_models) >= 1
        assert len(res.summary_individuals_count) >= 1
