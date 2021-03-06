from gimeltune import (Categorical, Experiment, Integer,
                       Real, SearchSpace, create_job)


# noinspection DuplicatedCode
def objective(experiment: Experiment):
    x = experiment.params.get("x")
    y = experiment.params.get("y")
    return ((1.5 - x + x * y)**2 + (2.25 - x + x * y**2)**2 +
            (2.625 - x + x * y**3)**2)


def test_skopt():
    # noinspection DuplicatedCode
    space = SearchSpace()

    space.insert(Real("x", low=0.0, high=5.0))
    space.insert(Real("y", low=0.0, high=2.0))
    space.insert(Integer("z", low=0, high=1))
    space.insert(Categorical("w", choices=["foo"]))

    job = create_job(search_space=space)
    job.do(objective, n_trials=10, algo_list=["skopt"])
