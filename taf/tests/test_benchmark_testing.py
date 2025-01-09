import time
import pytest
import pytest_benchmark

def test_benchmark(benchmark):
    benchmark(time.sleep, 0.6)


def test_benchmark_two(benchmark):
    benchmark(function_test)


def function_test():
    time.sleep(0.1)
    assert False