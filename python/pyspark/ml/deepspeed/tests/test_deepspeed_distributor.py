#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
from contextlib import contextmanager
import os
import sys
import textwrap
from typing import Any,Dict, Tuple

import shutil
import unittest

from pyspark import SparkConf, SparkContext
from pyspark.ml.deepspeed.deepspeed_distributor import DeepspeedTorchDistributor
from pyspark.ml.torch.distributor import TorchDistributor
from pyspark.sql import SparkSession
from pyspark.testing.utils import SPARK_HOME
from pyspark.ml.torch.tests.test_distributor import get_local_mode_conf, set_up_test_dirs, get_distributed_mode_conf

class DeepspeedTorchDistributorUnitTests(unittest.TestCase):
    def _get_env_var(self, var_name: str, default_value: Any) -> Any:
        value = os.getenv(var_name)
        if value:
            return value
        os.environ[var_name] = str(default_value)
        return default_value

    def _get_env_variables_distributed(self) -> Tuple[Any, Any, Any]:
        master_addr = self._get_env_var("MASTER_ADDR", "127.0.0.1")
        master_port = self._get_env_var("MASTER_PORT", 2000)
        rank = self._get_env_var("RANK", 0)
        return master_addr, master_port, rank

    def test_get_torchrun_args_local(self) -> None:
        number_of_processes = 5
        expected_torchrun_args_local = ["--standalone", "--nnodes=1"]
        expected_processes_per_node_local = number_of_processes
        (
            get_local_mode_torchrun_args,
            process_per_node,
        ) = DeepspeedTorchDistributor._get_torchrun_args(True, number_of_processes)
        self.assertEqual(get_local_mode_torchrun_args, expected_torchrun_args_local)
        self.assertEqual(expected_processes_per_node_local, process_per_node)

    def test_get_torchrun_args_distributed(self) -> None:
        number_of_processes = 5
        master_addr, master_port, rank = self._get_env_variables_distributed()
        expected_torchrun_args_distributed = [
            f"--nnodes={number_of_processes}",
            f"--node_rank={rank}",
            f"--rdzv_endpoint={master_addr}:{master_port}",
            "--rdzv_id=0",
        ]
        torchrun_args_distributed, process_per_node = DeepspeedTorchDistributor._get_torchrun_args(
            False, number_of_processes
        )
        self.assertEqual(torchrun_args_distributed, expected_torchrun_args_distributed)
        self.assertEqual(process_per_node, 1)

    def test_create_torchrun_command_local(self) -> None:
        deepspeed_conf = "path/to/deepspeed"
        train_file_path = "path/to/exec"
        num_procs = 10
        input_params: Dict[str, Any] = {}
        input_params["local_mode"] = True
        input_params["num_processes"] = num_procs
        input_params["deepspeed_config"] = deepspeed_conf

        torchrun_local_args_expected = ["--standalone", "--nnodes=1"]
        with self.subTest(msg="Testing local training with no extra args"):
            local_cmd_no_args_expected = [
                sys.executable,
                "-m",
                "torch.distributed.run",
                *torchrun_local_args_expected,
                f"--nproc_per_node={num_procs}",
                train_file_path,
                "--deepspeed",
                "--deepspeed_config",
                deepspeed_conf,
            ]
            local_cmd = DeepspeedTorchDistributor._create_torchrun_command(
                input_params, train_file_path
            )
            self.assertEqual(local_cmd, local_cmd_no_args_expected)
        with self.subTest(msg="Testing local training with extra args for the training script"):
            local_mode_version_args = ["--arg1", "--arg2"]
            local_cmd_args_expected = [
                sys.executable,
                "-m",
                "torch.distributed.run",
                *torchrun_local_args_expected,
                f"--nproc_per_node={num_procs}",
                train_file_path,
                *local_mode_version_args,
                "--deepspeed",
                "--deepspeed_config",
                deepspeed_conf,
            ]

            local_cmd_with_args = DeepspeedTorchDistributor._create_torchrun_command(
                input_params, train_file_path, *local_mode_version_args
            )
            self.assertEqual(local_cmd_with_args, local_cmd_args_expected)

    def test_create_torchrun_command_distributed(self) -> None:
        deepspeed_conf = "path/to/deepspeed"
        train_file_path = "path/to/exec"
        num_procs = 10
        input_params: Dict[str, Any] = {}
        input_params["local_mode"] = True
        input_params["num_processes"] = num_procs
        input_params["deepspeed_config"] = deepspeed_conf
        (
            distributed_master_address,
            distributed_master_port,
            distributed_rank,
        ) = self._get_env_variables_distributed()
        distributed_torchrun_args = [
            f"--nnodes={num_procs}",
            f"--node_rank={distributed_rank}",
            f"--rdzv_endpoint={distributed_master_address}:{distributed_master_port}",
            "--rdzv_id=0",
        ]
        with self.subTest(msg="Distributed training command verification with no extra args"):
            distributed_cmd_no_args_expected = [
                sys.executable,
                "-m",
                "torch.distributed.run",
                *distributed_torchrun_args,
                "--nproc_per_node=1",
                train_file_path,
                "--deepspeed",
                "--deepspeed_config",
                deepspeed_conf,
            ]
            input_params["local_mode"] = False
            distributed_command = DeepspeedTorchDistributor._create_torchrun_command(
                input_params, train_file_path
            )
            self.assertEqual(distributed_cmd_no_args_expected, distributed_command)
        with self.subTest(msg="Distributed training command verification with extra arguments"):
            distributed_extra_args = ["-args1", "--args2"]
            distributed_cmd_args_expected = [
                sys.executable,
                "-m",
                "torch.distributed.run",
                *distributed_torchrun_args,
                "--nproc_per_node=1",
                train_file_path,
                *distributed_extra_args,
                "--deepspeed",
                "--deepspeed_config",
                deepspeed_conf,
            ]
            distributed_command_with_args = DeepspeedTorchDistributor._create_torchrun_command(
                input_params, train_file_path, *distributed_extra_args
            )
            self.assertEqual(distributed_cmd_args_expected, distributed_command_with_args)

def _create_basic_function():
    # TODO: swap out with better test function
    # once Deepspeed better supports CPU
   def pythagoras(leg1: float, leg2: float):
       import deepspeed
       return (leg1 * leg1 + leg2 * leg2)**0.5
   return pythagoras 


@contextmanager
def _create_pytorch_training_test_file():
    # TODO: swap with better training file like below:
    #import deepspeed
    #import torch
    #import torch.nn as nn
    #from torch.utils.data import DataLoader, Dataset
    #
    ## Simple model class
    #class SimpleModel(nn.Module):
    #    def __init__(self):
    #        super(SimpleModel, self).__init__()
    #        self.fc = nn.Linear(10, 5)
    #
    #    def forward(self, x):
    #        return self.fc(x)
    #
    ## Dummy dataset class
    #class DummyDataset(Dataset):
    #    def __init__(self, num_samples=1000, input_dim=10, num_classes=5):
    #        self.num_samples = num_samples
    #        self.input_dim = input_dim
    #        self.num_classes = num_classes
    #        self.data = torch.randn(num_samples, input_dim)
    #        self.labels = torch.randint(0, num_classes, (num_samples,))
    #
    #    def __len__(self):
    #        return self.num_samples
    #
    #    def __getitem__(self, idx):
    #        return self.data[idx], self.labels[idx]
    #
    ## Instantiate the model and the data loader
    #model = SimpleModel()
    #dataset = DummyDataset()
    #data_loader = DataLoader(dataset, batch_size=8, shuffle=True)
    #
    #deepspeed_config = {
    #    "train_batch_size_per_gpu": 8,
    #    "optimizer": {
    #        "type": "Adam",
    #        "params": {
    #            "lr": 1e-4,
    #        },
    #    },
    #    "fp16": {
    #        "enabled": False,  # Set to True for mixed-precision training on supported hardware.
    #    },
    #}
    #model, _, _, _ = deepspeed.initialize(model=model, model_parameters=model.parameters(), config_params=deepspeed_config)
    #criterion = torch.nn.CrossEntropyLoss()
    #optimizer = model.optimizer
    ## Training loop
    #for epoch in range(num_epochs):
    #    model.train()
    #    for inputs, targets in data_loader:
    #        optimizer.zero_grad()
    #        outputs = model(inputs)
    #        loss = criterion(outputs, targets)
    #        loss.backward()
    #        optimizer.step()
    #torch.save(model.state_dict(), "cpu_trained_model.pt")
        str_to_write = textwrap.dedent(""" 
import sys
def pythagorean_thm(x : int, y: int):
    import deepspeed
    return (x*x + y*y)**0.5
print(pythagorean_thm(int(sys.argv[1]), int(sys.argv[2])))
""")
        cp_path = f"/tmp/test_deepspeed_training_file.py"
        with open(cp_path, "w") as f:
            f.write(str_to_write)
        yield cp_path 
        os.remove(cp_path)



# The program and function that we use in the end-to-end tests
# is very simple because in the Spark CI we only have access
# to CPUs and at this point in time, CPU support is limited
# in Deepspeed. Once Deepspeed better supports CPU training
# and inference, the hope is to switch out the training 
# and file for the tests with more realistic testing 
# that use Deepspeed constructs. 
class DeepspeedTorchDistributorDistributedEndToEnd(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        (cls.gpu_discovery_script_file_name, cls.mnist_dir_path) = set_up_test_dirs()
        # "loadDefaults" is set to False because if not, the SparkConf will 
        # use contain configurations from the LocalEndToEnd test,
        # which causes the test to break.
        conf = SparkConf(loadDefaults=False)
        for k, v in get_distributed_mode_conf().items():
            conf = conf.set(k, v)
        conf = conf.set(
            "spark.worker.resource.gpu.discoveryScript", cls.gpu_discovery_script_file_name
        )
        sc = SparkContext("local-cluster[2,2,512]",cls.__name__,conf=conf)
        cls.spark = SparkSession(sc)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.mnist_dir_path)
        os.unlink(cls.gpu_discovery_script_file_name)
        cls.spark.stop()

    def test_simple_function_e2e(self):
       train_fn = _create_basic_function()
       # Arguments for the pythagoras function train_fn
       x = 3
       y = 4
       dist = DeepspeedTorchDistributor(numGpus=2, useGpu=False, localMode=False)
       output = dist.run(train_fn, x, y)
       self.assertEqual(output, 5)

    def test_pytorch_file_e2e(self):
        # TODO: change to better test script
        # once Deepspeed CPU support is better
        with _create_pytorch_training_test_file() as cp_path:
            dist = DeepspeedTorchDistributor(numGpus=True, useGpu=False, localMode=False)
            dist.run(cp_path, 2, 5)


class DeepspeedDistributorLocalEndToEndTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.gpu_discovery_script_file_name, cls.mnist_dir_path = set_up_test_dirs()
        conf = SparkConf()
        for k, v in get_local_mode_conf().items():
            conf = conf.set(k, v)
        conf = conf.set(
            "spark.driver.resource.gpu.discoveryScript", cls.gpu_discovery_script_file_name
        )
        sc = SparkContext("local-cluster[2,2,512]",cls.__name__,conf=conf)
        cls.spark = SparkSession(sc)
    
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.mnist_dir_path)
        os.unlink(cls.gpu_discovery_script_file_name)
        cls.spark.stop()

    def test_simple_function_e2e(self):
       train_fn = _create_basic_function()
       # Arguments for the pythagoras function train_fn
       x = 3
       y = 4
       dist = DeepspeedTorchDistributor(numGpus=2, useGpu=False, localMode=True)
       output = dist.run(train_fn, x, y)
       self.assertEqual(output, 5)

    def test_pytorch_file_e2e(self):
        with _create_pytorch_training_test_file() as  path_to_train_file:
            dist = DeepspeedTorchDistributor(numGpus=2, useGpu=False, localMode=True)
            dist.run(path_to_train_file, 2, 5)


if __name__ == "__main__":
    from pyspark.ml.deepspeed.tests.test_deepspeed_distributor import *  # noqa: F401,F403

    try:
        import xmlrunner  # type:ignore

        testRunner = xmlrunner.XMLTestRunner(output="target/test-reports", verbosity=2)
    except ImportError:
        testRunner = None
    unittest.main(testRunner=testRunner, verbosity=2)
