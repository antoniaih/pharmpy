import random
import warnings
from dataclasses import dataclass, replace
from typing import Optional

from pharmpy.internals.fn.signature import with_same_arguments_as
from pharmpy.internals.fn.type import with_runtime_arguments_type_check
from pharmpy.model import Model
from pharmpy.modeling import calculate_parameters_from_ucp, calculate_ucp_scale, update_inits
from pharmpy.tools import summarize_modelfit_results
from pharmpy.tools.common import ToolResults, create_results
from pharmpy.tools.modelfit import create_fit_workflow
from pharmpy.workflows import ModelEntry, Task, Workflow, WorkflowBuilder, call_workflow
from pharmpy.workflows.results import ModelfitResults

SCALES = frozenset(('normal', 'UCP'))


@dataclass
class Retry:
    modelentry: ModelEntry
    number_of_retries: int


def create_workflow(
    model: Optional[Model] = None,
    results: Optional[ModelfitResults] = None,
    number_of_candidates: int = 5,
    degree: float = 0.1,
    strictness: Optional[str] = "minimization_successful or (rounding_errors and sigdigs >= 0.1)",
    scale: Optional[str] = "UCP",
    prefix_name: Optional[str] = "",  # FIXME : Remove once new database has been implemented
):
    """
    Run retries tool.

    Parameters
    ----------
    model : Optional[Model], optional
        Model object to run retries on. The default is None.
    results : Optional[ModelfitResults], optional
        Connected ModelfitResults object. The default is None.
    number_of_candidates : int, optional
        Number of retry candidates to run. The default is 5.
    degree: float
        Determines allowed increase/decrease from initial parameter estimate. Default is 0.1 (10%)
    strictness : Optional[str], optional
        Strictness criteria. The default is "minimization_successful or (rounding_errors and sigdigs >= 0.1)".
    scale : Optional[str]
        Which scale to update the initial values on. Either normal scale or UCP scale.
    prefix_name: Optional[str]
        Prefix the candidate model names with given string.

    Returns
    -------
    RetriesResults
        Retries tool results object.

    """

    wb = WorkflowBuilder(name='retries')

    if model is not None:
        start_task = Task('Start_retries', _start, results, model)
    else:
        # Remove?
        start_task = Task('Start_retries', _start, None)

    wb.add_task(start_task)

    candidate_tasks = []
    for i in range(1, number_of_candidates + 1):
        new_candidate_task = Task(
            f"Create_candidate_{i}",
            create_random_init_model,
            i,
            scale,
            degree,
            prefix_name,
        )
        wb.add_task(new_candidate_task, predecessors=start_task)
        candidate_tasks.append(new_candidate_task)
    task_gather = Task('Gather', lambda *retries: retries)
    wb.add_task(task_gather, predecessors=[start_task] + candidate_tasks)

    results_task = Task('Results', task_results, strictness)
    wb.add_task(results_task, predecessors=task_gather)

    return Workflow(wb)


def _start(results, model):
    # Convert to modelentry
    if results is None:
        # fit the model
        pass
    else:
        return ModelEntry.create(model=model, modelfit_results=results)


def create_random_init_model(context, index, scale, degree, prefix_name, modelentry):
    original_model = modelentry.model
    # Update inits once before running?

    # Add any description?
    if prefix_name:
        name = f'{prefix_name}_retries_run{index}'
    else:
        name = f'retries_run{index}'
    new_candidate_model = original_model.replace(name=name)

    if scale == "normal":
        maximum_tests = 20  # TODO : Convert to argument
        for try_number in range(1, maximum_tests + 1):
            new_parameters = {}
            for p in original_model.parameters:
                lower_bound = p.init - p.init * degree
                if lower_bound < p.lower:
                    lower_bound = p.lower + 10**-6
                upper_bound = p.init + p.init * degree
                if upper_bound > p.upper:
                    upper_bound = p.upper - 10**-6

                new_init = lower_bound + random.random() * (upper_bound - lower_bound)
                new_parameters[p.name] = new_init

            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "error",
                    message="Adjusting initial estimates to create positive semidefinite omega/sigma matrices",
                    category=UserWarning,
                )
                try:
                    new_candidate_model = update_inits(new_candidate_model, new_parameters)
                    break
                except UserWarning:
                    if try_number == maximum_tests:
                        raise ValueError(
                            f"{new_candidate_model.name} could not be determined"
                            f" to be positive semi-definite."
                        )

        new_candidate_model_fit_wf = create_fit_workflow(models=[new_candidate_model])
        new_candidate_model = call_workflow(
            new_candidate_model_fit_wf, f'fit_candidate_run{index}', context
        )
        new_modelentry = ModelEntry.create(
            model=new_candidate_model,
            modelfit_results=new_candidate_model.modelfit_results,
            parent=original_model,
        )
        return Retry(
            modelentry=new_modelentry,
            number_of_retries=try_number,
        )

    elif scale == "UCP":
        ucp_scale = calculate_ucp_scale(new_candidate_model)
        subs_dict = {}
        for p in new_candidate_model.parameters:
            subs_dict[p.name] = 0.1 - (0.1 * degree) + random.random() * 2 * degree * 0.1
        new_parameters = calculate_parameters_from_ucp(new_candidate_model, ucp_scale, subs_dict)

        new_candidate_model = update_inits(new_candidate_model, new_parameters)

        new_candidate_model_fit_wf = create_fit_workflow(models=[new_candidate_model])
        new_candidate_model = call_workflow(
            new_candidate_model_fit_wf, f'fit_candidate_run{index}', context
        )
        new_modelentry = ModelEntry.create(
            model=new_candidate_model,
            modelfit_results=new_candidate_model.modelfit_results,
            parent=original_model,
        )
        return Retry(
            modelentry=new_modelentry,
            number_of_retries=1,
        )
    else:
        # Should be caught in validate_input()
        raise ValueError(f'Scale ({scale}) is not supported')


def task_results(strictness, retries):
    # Note : the input (modelentry) is a part of retries
    retry_runs = []
    for r in retries:
        if isinstance(r, ModelEntry):
            input_model_entry = r
        elif isinstance(r, Retry):
            retry_runs.append(r)
        else:
            raise ValueError(f'Unknown type ({type(r)}) found when summarizing results.')
    res_models = [r.modelentry for r in retry_runs]
    results_to_summarize = [input_model_entry.modelfit_results] + [
        r.modelentry.modelfit_results for r in retry_runs
    ]
    rank_type = "ofv"
    cutoff = None

    summary_models = summarize_modelfit_results(results_to_summarize)
    summary_models['step'] = [0] + [1] * (len(summary_models) - 1)
    summary_models = summary_models.reset_index().set_index(['step', 'model'])

    res = create_results(
        RetriesResults,
        input_model_entry,
        input_model_entry,
        res_models,
        rank_type,
        cutoff,
        strictness=strictness,
        summary_models=summary_models,
    )

    res = replace(
        res,
        summary_tool=_modify_summary_tool(res.summary_tool, retry_runs),
    )

    return res


def _modify_summary_tool(summary_tool, retry_runs):
    summary_tool = summary_tool.reset_index()
    number_of_retries_dict = {r.modelentry.model.name: r.number_of_retries for r in retry_runs}
    summary_tool['Number_of_retries'] = summary_tool['model'].map(number_of_retries_dict)

    column_to_move = summary_tool.pop('Number_of_retries')
    summary_tool.insert(1, 'Number_of_retries', column_to_move)

    return summary_tool.set_index(['model'])


@with_runtime_arguments_type_check
@with_same_arguments_as(create_workflow)
def validate_input(model, results, number_of_candidates, degree, strictness, scale, prefix_name):
    if not isinstance(model, Model):
        raise ValueError(
            f'Invalid `model` type: got `{type(model)}`, must be one of pharmpy Model object.'
        )

    if not isinstance(results, ModelfitResults):
        raise ValueError(
            f'Invalid `results` type: got `{type(results)}`, must be one of pharmpy ModelfitResults object.'
        )

    if not isinstance(number_of_candidates, int):
        raise ValueError(
            f'Invalid `number_of_candidates` type: got `{type(number_of_candidates)}`, must be an integer.'
        )
    elif number_of_candidates <= 0:
        raise ValueError(
            f'`number_of_candidates` need to be a positiv integer, not `{number_of_candidates}`'
        )

    if not isinstance(degree, float):
        raise ValueError(f'Invalid `degree` type: got `{type(degree)}`, must be an number (float).')

    # STRICTNESS?

    if scale not in SCALES:
        raise ValueError(f'Invalid `scale`: got `{scale}`, must be one of {sorted(SCALES)}.')


@dataclass(frozen=True)
class RetriesResults(ToolResults):
    pass