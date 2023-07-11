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

import os
import unittest

from pyspark.ml import Pipeline
from pyspark.ml.classification import LogisticRegression, OneVsRest
from pyspark.ml.feature import VectorAssembler
from pyspark.ml.linalg import Vectors
from pyspark.ml.util import MetaAlgorithmReadWrite
from pyspark.testing.mlutils import SparkSessionTestCase


class MetaAlgorithmReadWriteTests(SparkSessionTestCase):
    def test_getAllNestedStages(self):
        def _check_uid_set_equal(stages, expected_stages):
            uids = set(map(lambda x: x.uid, stages))
            expected_uids = set(map(lambda x: x.uid, expected_stages))
            self.assertEqual(uids, expected_uids)

        df1 = self.spark.createDataFrame(
            [
                (Vectors.dense([1.0, 2.0]), 1.0),
                (Vectors.dense([-1.0, -2.0]), 0.0),
            ],
            ["features", "label"],
        )
        df2 = self.spark.createDataFrame(
            [
                (1.0, 2.0, 1.0),
                (1.0, 2.0, 0.0),
            ],
            ["a", "b", "label"],
        )
        vs = VectorAssembler(inputCols=["a", "b"], outputCol="features")
        lr = LogisticRegression()
        pipeline = Pipeline(stages=[vs, lr])
        pipelineModel = pipeline.fit(df2)
        ova = OneVsRest(classifier=lr)
        ovaModel = ova.fit(df1)

        ova_pipeline = Pipeline(stages=[vs, ova])
        nested_pipeline = Pipeline(stages=[ova_pipeline])

        _check_uid_set_equal(
            MetaAlgorithmReadWrite.getAllNestedStages(pipeline), [pipeline, vs, lr]
        )
        _check_uid_set_equal(
            MetaAlgorithmReadWrite.getAllNestedStages(pipelineModel),
            [pipelineModel] + pipelineModel.stages,
        )
        _check_uid_set_equal(MetaAlgorithmReadWrite.getAllNestedStages(ova), [ova, lr])
        _check_uid_set_equal(
            MetaAlgorithmReadWrite.getAllNestedStages(ovaModel), [ovaModel, lr] + ovaModel.models
        )
        _check_uid_set_equal(
            MetaAlgorithmReadWrite.getAllNestedStages(nested_pipeline),
            [nested_pipeline, ova_pipeline, vs, ova, lr],
        )

def test_function(x: float, y: float) -> float:
    return x**2 + y**2

from pyspark import cloudpickle
from pyspark.ml.util import FunctionPickler
class TestFunctionPickler(unittest.TestCase):

    def __init__(self):
        pass
    
    def check_if_test_function_pickled(self, f, og_fn, *arguments, **key_word_args):
        fn, args, kwargs = cloudpickle.load(f)
        self.assertEqual(fn, og_fn)
        self.assertEqual(args, arguments)
        self.assertEqual(kwargs, key_word_args)

    def test_pickle_func_and_get_path(self):
        x, y = 1, 3 # args of test_function
        with self.subTest(msg="See if it pickles correctly if no file_path or save_dir are specified"):
            pickled_fn_path = FunctionPickler.pickle_func_and_get_path(test_function, "", "", x, y)
            with open(pickled_fn_path, "rb") as f:
                self.check_if_test_function_pickled(f, test_function, x, y)
            os.remove(pickled_fn_path)

if __name__ == "__main__":
    from pyspark.ml.tests.test_util import *  # noqa: F401

    try:
        import xmlrunner

        testRunner = xmlrunner.XMLTestRunner(output="target/test-reports", verbosity=2)
    except ImportError:
        testRunner = None
    unittest.main(testRunner=testRunner, verbosity=2)
