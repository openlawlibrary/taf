# Benchmark Testing

## Writing benchmark tests

To benchmark a test, you must first make sure that the test can be run multiple times in a row without issue. If the test relies on other tests to perform setup or cleanup, that must be changed before benchmarking can be done on that test. Once you have done that, import pytest (and the test you want to benchmark, if it's in a different file) and define a new test and pass in any variables you would need for the test you want to benchmark. Inside that test, call "benchmark()" and pass in the name of the test you want to benchmark, followed by any variables you need to pass to that test. Import the benchmarked test under a name that does not start with `test_` (for example `test_clone_valid_happy_path as clone_valid_happy_path`), otherwise pytest collects it a second time.

Put benchmark tests in `taf/tests/test_updater/` in files named `benchmark_*.py`, not `test_*.py`. That way pytest does not pick them up when the regular tests are run.

## Running benchmark tests

Benchmark tests are not run by a plain `pytest taf/tests`. To run them, pass the file directly or tell pytest to collect benchmark files:

```bash
pytest taf/tests/test_updater/benchmark_update.py
pytest taf/tests/test_updater -o python_files='benchmark_*.py'
```

The results will be displayed in a table once testing is complete. By default, all benchmark tests will be run a minimum of 5 times. You can change that adding "--benchmark-min-rounds=" to the call to pytest. 

## Saving results

To save the results for later usage, add "--benchmark-save=NAME" followed by a name or "--benchmark-autosave" to store a .json file containing the results. This file will be stored in a folder with a name something along the lines of "Linux-CPython-3.10-64bit", with the exact name depending on the environment's OS, python version, etc., and its name will be prefixed by four digits and an underscore, starting with 0001_ and counting up. If you want the results stored elsewhere or with a different name, you can use "--benchmark-json=PATH" followed by a path, however you won't be able to run comparisons with it unless it gets moved to that folder and has its name start with four digits and an underscore.

## Comparing results

All files that you intend to compare must be stored in the benchmark storage folder (`.benchmarks/` by default), either in the folder that output files are saved to or directly in `.benchmarks/`. Additionally, the file name of any such file must begin with four digits and an underscore. Without a number, "--benchmark-compare" compares against the file with the highest number. Once there, you can compare against such a file by adding "-–benchmark-compare=" followed by the four digits at the start of the file's name to your call to pytest benchmark. This will compare the results of the run to the results of the stored run and create a comparison table in the console output. 

If you want to cause failure in the case of regression, also add "–-benchmark-compare-fail=" followed by an expression such as "min:5%" (fail if the quickest result of any test now is 5% slower than it was last time) or "mean:0.001" (fail if the average result of any test now is 0.001 seconds slower than it was last time) to determine what regression will cause the test to fail. It can be added multiple times to add multiple conditions. Note that it will always apply these standards to all benchmark tests being run by pytest.

To compare two already stored results, the standalone command "pytest-benchmark compare" followed by the paths of the files you wish to compare can do that. Unlike the previous method, these files do not need to be stored in any specific folder.

For further options, see https://pytest-benchmark.readthedocs.io/en/latest/usage.html


## Thresholds

On branches, CI fails the benchmarks when they are more than 20% slower than master's latest results. If a branch is expected to be slower, add it to `benchmark_thresholds.json` with the allowed percentage, a whole number from 0 to 99:

```json
{
  "feature/cool-feature": 30
}
```
