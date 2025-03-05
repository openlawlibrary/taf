# Benchmark Testing

## Writing benchmark tests

To benchmark a test, you must first make sure that the test can be run multiple times in a row without issue. If the test relies on other tests to perform setup or cleanup, that must be changed before benchmarking can be done on that test. Once you have done that, import pytest (and the test you want to benchmark, if it's in a different file) and define a new test and pass in any variables you would need for the test you want to benchmark. Inside that test, call "benchmark()" and pass in the name of the test you want to benchmark, followed by any variables you need to pass to that test.

## Running benchmark tests

Once you have written benchmark tests, they will be run any time pytest is called, and the results will be displayed in a table once testing is complete. If you only want to run benchmark tests, add "--benchmark-only" to the call to pytest. By default, all benchmark tests will be run a minimum of 5 times. You can change that adding "--benchmark-min-rounds=" to the call to pytest. 

## Saving results

To save the results for later usage, add "--benchmark-save=NAME" followed by a name or "--benchmark-autosave" to store a .json file containing the results. This file will be stored in a folder with a name something along the lines of "Linux-CPython-3.10-64bit", with the exact name depending on the environment's OS, python version, etc., and its name will be prefixed by four digits and an underscore, starting with 0001_ and counting up. If you want the results stored elsewhere or with a different name, you can use "--benchmark-json=PATH" followed by a path, however you won't be able to run comparisons with it unless it gets moved to that folder and has its name start with four digits and an underscore.

## Comparing results

All files that you intend to compare MUST be stored in the same folder that output files are saved to. Additionally, the file name of any such file must begin with four digits and an underscore. Once there, you can compare against such a file by adding "-–benchmark-compare=" followed by the four digits at the start of the file's name to your call to pytest benchmark. This will compare the results of the run to the results of the stored run and create a comparison table in the console output. 

If you want to cause failure in the case of regression, also add "–-benchmark-compare-fail=" followed by an expression such as "min:5%" (fail if the quickest result of any test now is 5% slower than it was last time) or "mean:0.001" (fail if the average result of any test now is 0.001 seconds slower than it was last time) to determine what regression will cause the test to fail. It can be added multiple times to add multiple conditions. Note that it will always apply these standards to all benchmark tests being run by pytest.

To compare two already stored results, the standalone command "pytest-benchmark compare" followed by the paths of the files you wish to compare can do that. Unlike the previous method, these files do not need to be stored in any specific folder.

For further options, see https://pytest-benchmark.readthedocs.io/en/latest/usage.html
