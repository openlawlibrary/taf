import time
import pytest
import pytest_benchmark
import random

def test_benchmark(benchmark):
    benchmark(get_useless_number)
    #benchmark(time.sleep, 0.6)

def test_concurrency_with_file_writing(benchmark):
    benchmark(write_numbered_lines)


def test_benchmark_two(benchmark):
    benchmark(function_test)


def function_test():
    time.sleep(0.1)
    #assert False


def write_numbered_lines():
    for i in range(2):
        with open("C:\\Users\\doxie\\OneDrive\\Desktop\\TestOutput.txt", 'a') as the_file:
            the_file.write(f"Line {i}\n")
            the_file.close()
        time.sleep(random.random() / 1000)

def get_useless_number():
    try:
        x = 3
        return x
    finally:
        time.sleep(0.5)
        y = 4
        z = 3