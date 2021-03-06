from sklearn.ensemble import AdaBoostRegressor, RandomForestRegressor
from sklearn.neural_network import MLPRegressor

from gimeltune import Experiment, Real, SearchSpace, create_job


# noinspection DuplicatedCode
from gimeltune.search.algorithms import BayesianAlgorithm
from gimeltune.search.bandit import ThompsonSampler


def objective(experiment: Experiment):
    x = experiment.params.get("x")
    y = experiment.params.get("y")
    return ((1.5 - x + x * y)**2 + (2.25 - x + x * y**2)**2 +
            (2.625 - x + x * y**3)**2)


def test_minimal():
    space = SearchSpace()

    space.insert(Real("x", low=0.0, high=5.0))
    space.insert(Real("y", low=0.0, high=2.0))

    job = create_job(search_space=space, storage="tinydb:///foo.json")
    job.do(objective, n_trials=50)

    assert abs(job.best_value - 0) < 5
    assert len(job.dataframe) == 50


def test_job_with_algo_ensemble():
    space = SearchSpace()

    space.insert(Real("x", low=0.0, high=5.0))
    space.insert(Real("y", low=0.0, high=2.0))

    job = create_job(
        search_space=space,
        storage="tinydb:///foo.json",
        optimizer=ThompsonSampler
    )

    ada = BayesianAlgorithm(search_space=space, regressor=AdaBoostRegressor)
    forest = BayesianAlgorithm(search_space=space, regressor=RandomForestRegressor)
    classic = BayesianAlgorithm(search_space=space)

    classic.name = 'ClassicBayesianSearch'
    mlp = BayesianAlgorithm(search_space=space, regressor=MLPRegressor)

    job.do(objective, n_trials=50, algo_list=['template', ada, forest, classic, mlp])

    assert abs(job.best_value - 0) < 5
    assert len(job.dataframe) == 50
