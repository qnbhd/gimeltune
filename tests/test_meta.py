import logging

import numpy as np
import pytest

from gimeltune import Real, SearchSpace, create_job, GridSearch
from gimeltune.exceptions import InvalidOptimizer
from gimeltune.search import RoundRobinMeta
from gimeltune.search.algorithms import TemplateSearchAlgorithm
from gimeltune.search.bandit import UCB1, UCBTuned, ThompsonSampler

log = logging.getLogger(__name__)


def test_different_optimizers():
    def f(experiment):
        x, y = experiment.params['x'], experiment.params['y']
        return x + np.cos(y)

    space = SearchSpace(
        Real('x', low=0.0, high=1.0),
        Real('y', low=0.0, high=1.0)
    )

    create_job(search_space=space, optimizer=RoundRobinMeta)
    create_job(search_space=space, optimizer=UCB1)

    with pytest.raises(InvalidOptimizer):
        create_job(search_space=space, optimizer=1)

    grid = GridSearch(search_space=space)
    template = TemplateSearchAlgorithm(search_space=space)
    template1 = TemplateSearchAlgorithm(search_space=space)

    op1 = RoundRobinMeta(grid, template)
    op2 = UCB1(template, grid, template1)
    op3 = UCBTuned(grid, template)

    ensemble = ThompsonSampler(op1, op2, op3)

    job = create_job(search_space=space, optimizer=ensemble)
    job.do(objective=f, n_proc=5, n_trials=20, clear=False)

    print(job.best_parameters)
    print(job.rewards)
