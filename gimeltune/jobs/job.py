# MIT License
#
# Copyright (c) 2021 Templin Konstantin
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import inspect
import warnings
from datetime import datetime
from functools import partial
from typing import Any, Callable, List, Optional, Type, Union

import multiprocess as mp
import pandas as pd
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import ArgumentError

from rich.progress import Progress

from gimeltune.exceptions import (
    DuplicatedJobError,
    ExperimentNotFinishedError,
    InvalidStoragePassed,
    InvalidStorageRFC1738,
    JobNotFoundError,
    SearchAlgorithmNotFoundedError, InvalidOptimizer,
)
from gimeltune.models import Experiment, Result
from gimeltune.models.experiment import ExperimentState
from gimeltune.search import SearchSpace, RoundRobinMeta
from gimeltune.search.algorithms import (
    SearchAlgorithm,
    SeedAlgorithm,
    SkoptBayesianAlgorithm,
    get_algo,
)
from gimeltune.search.meta import MetaSearchAlgorithm
from gimeltune.storages import Storage, TinyDBStorage

__all__ = ["create_job", "load_job"]

from gimeltune.storages.rdb.storage import RDBStorage


class Job:
    """
    Facade of framework.
    """

    def __init__(
        self,
        name: str,
        storage: Storage,
        search_space: SearchSpace,
        job_id: int,
        pruners: Any = None,
        optimizer=RoundRobinMeta,
    ):

        self.name = name
        self.storage = storage
        self.pruners = pruners
        self.id = job_id

        if issubclass(type(optimizer), MetaSearchAlgorithm):
            self.optimizer = optimizer
        elif (
            not issubclass(type(optimizer), MetaSearchAlgorithm) and
            (
                not inspect.isclass(optimizer) or
                not issubclass(optimizer, MetaSearchAlgorithm)
            )
        ):
            raise InvalidOptimizer()
        else:
            self.optimizer = optimizer()

        self.search_space = search_space
        self.pending_experiments = 0

        self.seeds = []

        if not self.storage.is_job_name_exists(self.name):
            self.storage.insert_job(self)

    @property
    def best_parameters(self) -> Optional[dict]:
        """
        Get the best parameters in job.
        Load configurations with result
        and take params from best.

        :return: the best parameters' dict.
        """

        return self.best_experiment.params if self.best_experiment else None

    @property
    def best_value(self) -> Optional[Any]:
        """
        Get the best result value by objective.

        :return: float best value.
        """

        return (self.best_experiment.objective_result
                if self.best_experiment else None)

    @property
    def best_experiment(self) -> Optional[Experiment]:
        """
        Get the best experiment from job.

        :return: best experiment.
        """

        return self.storage.best_experiment(self.id)

    @property
    def experiments(self) -> List[Experiment]:
        """
        Get all experiments.

        :return:
        """

        return self.storage.get_experiments_by_job_id(self.id)

    @property
    def experiments_count(self) -> int:
        """

        :return:
        """

        return self.storage.get_experiments_count(self.id)

    def top_experiments(self, n: int):
        """
        Get top-n experiments by objective.

        :param n: max number of experiments.
        :return: list of experiments
        """

        return self.storage.top_experiments(self.id, n)

    @property
    def rewards(self):
        rewards = 0
        experiments = self.experiments
        m = float('+inf')

        for exp in experiments:
            if exp.objective_result < m:
                rewards += 1
                m = exp.objective_result

        return rewards

    def setup_default_algo(self):
        self.add_algorithm(
            SkoptBayesianAlgorithm(self.search_space))

    def _load_algo(self, algo_list=None):
        if self.seeds:
            self.add_algorithm(SeedAlgorithm(*self.seeds))

        if not algo_list:
            self.add_algorithm(
                SkoptBayesianAlgorithm(self.search_space))
        else:
            for algo in algo_list:
                if isinstance(algo, str):
                    try:
                        algo_cls = get_algo(algo)
                    except SearchAlgorithmNotFoundedError:
                        raise SearchAlgorithmNotFoundedError()
                elif isinstance(algo, SearchAlgorithm):
                    self.add_algorithm(algo)
                    continue
                elif issubclass(algo, SearchAlgorithm):
                    algo_cls = algo
                else:
                    raise SearchAlgorithmNotFoundedError()

                # noinspection PyArgumentList
                self.add_algorithm(
                    algo_cls(search_space=self.search_space))

    def do(
        self,
        objective: Callable,
        n_trials: int = 100,
        n_proc: int = 1,
        algo_list: List[Union[str, Type[SearchAlgorithm]]] = None,
        clear=True,
        progress_bar=True,
    ):
        """
        :param objective: objective function
        :param n_trials: count of max trials.
        :param n_proc: max number of processes.
        :param algo_list: chosen search algorithm's list.
        :param clear: clear algo list or not.
        :param progress_bar: show progress bar or not.
        :return: None
        """

        # noinspection PyPep8Naming

        if clear:
            cls = type(self.optimizer)
            self.optimizer = cls()

        if (
            algo_list or
            algo_list is None and not self.optimizer.algorithms
        ):
            self._load_algo(algo_list)

        trials = 0
        with Progress(transient=True, disable=not progress_bar) as bar:
            task = bar.add_task('Optimizing', total=n_trials)
            while trials < n_trials:
                bar.tasks[task].completed = trials

                configurations = self.ask()

                if not configurations:
                    warnings.warn("No new configurations.")
                    # TODO (qnbhd): make closing
                    break

                trials += len(configurations)

                # noinspection PyUnresolvedReferences
                with mp.Pool(n_proc) as p:
                    results = p.map(objective, configurations)

                # Applying result
                for experiment, result in zip(configurations, results):
                    experiment.success_finish()
                    self.tell(experiment, result)

    def tell(self, experiment, result: Union[float, Result]):
        """
        Finish concrete experiment.

        :return:
        :raises:
        """

        if experiment.is_finished():
            self.pending_experiments -= 1

            if isinstance(result, Result):
                self.optimizer.tell(experiment.params, result.objective_result)
                experiment.apply(result.objective_result)
                experiment.metrics = result.metrics
            else:
                self.optimizer.tell(experiment.params, result)
                experiment.apply(result)

            self.storage.insert_experiment(experiment)
            return

        raise ExperimentNotFinishedError()

    def _tell_for_loaded(self, experiment: Experiment):
        self.optimizer.tell(experiment.params, experiment.objective_result)

    def ask(self) -> Optional[List[Experiment]]:
        """
        Ask for a new experiment.
        :return:
        """

        configs = self.optimizer.ask()

        if not configs:
            return configs

        applyer = partial(
            Experiment,
            job_id=self.id,
            state=ExperimentState.WIP,
        )

        experiments = [
            applyer(
                params=config,
                id=self.experiments_count + self.pending_experiments + i,
                create_timestamp=datetime.timestamp(datetime.now())
            )
            for i, config in enumerate(configs)
        ]

        self.pending_experiments += len(experiments)

        return experiments

    def get_dataframe(self, brief=False, desc=False):
        container = []
        m = float('+inf')

        for experiment in self.experiments:
            dataframe_dict = experiment.dict()

            if dataframe_dict['objective_result'] < m:
                m = dataframe_dict['objective_result']
            else:
                if desc:
                    continue

            params = {
                f'param_{key}': value
                for key, value in dataframe_dict.pop("params").items()
            }

            metrics = dataframe_dict.pop("metrics") or dict()

            dataframe_dict["create_time"] = datetime.fromtimestamp(
                dataframe_dict["create_timestamp"])

            dataframe_dict["finish_time"] = datetime.fromtimestamp(
                dataframe_dict["finish_timestamp"])

            del dataframe_dict["create_timestamp"]
            del dataframe_dict["finish_timestamp"]
            del dataframe_dict["hash"]
            del dataframe_dict["job_id"]

            dataframe_dict["state"] = str(dataframe_dict["state"])

            if brief:
                idx = dataframe_dict['id']
                objective_result = dataframe_dict['objective_result']
                container.append(
                    {
                        'id': idx,
                        'objective_result': objective_result,
                        **params,
                        **metrics,
                    }
                )
                continue

            container.append(
                {
                    **dataframe_dict,
                    **params,
                    **metrics,
                }
            )

        df = pd.DataFrame(container)

        if container:
            df.set_index('id', inplace=True)

        return df

    @property
    def dataframe(self):
        return self.get_dataframe()

    def add_algorithm(self, algo: SearchAlgorithm):
        self.optimizer.add_algorithm(algo)

    def add_seed(self, seed):
        self.seeds.append(seed)


def _load_storage(storage_or_name: Union[str, Optional[Storage]]) -> Storage:
    if storage_or_name is None:
        return RDBStorage("sqlite:///:memory:")

    if issubclass(type(storage_or_name), Storage):
        return storage_or_name

    if not isinstance(storage_or_name, str):
        raise InvalidStoragePassed()

    try:
        url = make_url(storage_or_name)
    except ArgumentError:
        raise InvalidStorageRFC1738()

    assert url.database

    if url.drivername == "tinydb":
        return TinyDBStorage(str(url.database))

    return RDBStorage(storage_or_name)


def create_job(
    *,
    search_space: SearchSpace,
    name: str = None,
    storage: Union[str, Optional[Storage]] = None,
    **kwargs,
):
    """

    :param search_space:
    :param name:
    :param storage:
    :return:
    """

    name = name or "job" + datetime.now().strftime("%H_%M_%S_%m_%d_%Y")

    storage = _load_storage(storage)

    assert isinstance(name, str)
    assert isinstance(search_space, SearchSpace)

    if storage.is_job_name_exists(name):
        raise DuplicatedJobError(f"Job {name} is already exists.")

    return Job(name, storage, search_space, storage.jobs_count + 1, **kwargs)


def load_job(*, search_space: SearchSpace,
             name: str,
             storage: Union[str, Storage] = None,
             **kwargs):
    """

    :param search_space:
    :param name:
    :param storage:
    :return:
    """

    storage = _load_storage(storage)

    job_id = storage.get_job_id_by_name(name)

    if not job_id:
        raise JobNotFoundError(f"Job {name} not found is storage.")

    experiments = storage.get_experiments_by_job_id(job_id)

    job = Job(name, storage, search_space, job_id, **kwargs)

    for experiment in experiments:
        # noinspection PyProtectedMember
        job._tell_for_loaded(experiment)

    return job
