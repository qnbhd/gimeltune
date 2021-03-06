from unittest.mock import patch

from gimeltune import (Categorical, Experiment, Integer,
                       Real, SearchSpace, create_job)


def faked_random(nums):
    f = fake_random(nums)

    def inner(*args, **kwargs):
        return next(f)

    return inner


def fake_random(nums):
    i = 0
    while True:
        yield nums[i]
        i = (i + 1) % len(nums)


@patch(
    "random.random",
    side_effect=faked_random(
        [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]),
)
@patch("random.randint", side_effect=lambda lo, hi: lo)
@patch("random.choice", side_effect=lambda x: x[0])
def test_random_search(rr, ri, rc):
    space = SearchSpace()
    space.insert(Real("x", low=0.0, high=1.0))
    space.insert(Real("y", low=0.0, high=1.0))
    space.insert(Integer("z", low=0, high=2))
    space.insert(Categorical("w", choices=["foo"]))

    def objective(experiment: Experiment):
        params = experiment.params

        x = params.get("x")
        y = params.get("y")

        return (1 - x)**2 + (1 - y)**2

    job = create_job(search_space=space)
    job.do(objective, n_trials=10, algo_list=["random"])

    assert job.best_parameters == {"w": "foo", "x": 0.8, "y": 0.9, "z": 0}

