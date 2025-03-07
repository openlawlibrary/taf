# CI Setup and Benchmark Testing Documentation

## Overview

This document outlines the Continuous Integration (CI) process implemented to facilitate dynamic benchmark testing based on configurable thresholds. The process involves a JSON configuration file that allows branch-specific benchmark thresholds to be set, enabling more precise control over performance testing.

## CI Process Description

The CI workflow is designed to perform benchmark tests on direct pushes to branches. It uses `pytest` with benchmark plugins to assess performance regressions or improvements. To accommodate varying performance expectations across features or branches, a JSON file named `benchmark_thresholds.json` is used to specify custom benchmark thresholds.

## How Benchmark Testing Works

Benchmark tests are run using `pytest` configured to only execute benchmark-related tests:

- **Flag `--benchmark-only`**: Restricts `pytest` to run only benchmark tests.
- **Flag `--benchmark-json`**: Outputs the results to a JSON file, allowing for subsequent comparisons.
- **Flag `--benchmark-compare`**: Compares current benchmarks against the last saved benchmarks.
- **Flag `--benchmark-compare-fail`**: Specifies a threshold for test failure; if performance degrades beyond this percentage, the test fails.

These benchmarks help ensure that new code does not introduce significant performance regressions.

## Setting Benchmark Thresholds

The benchmark threshold can be defined for each branch to accommodate specific performance criteria associated with different types of work (e.g., feature development, bug fixes). This threshold is set in the `benchmark_thresholds.json` file. If not set, threshold is set to 10 by default.

### Example `benchmark_thresholds.json`:

```json
{
  "feature/cool-feature": 20,
  "bugfix/urgent-fix": 15
}
```

## Artifact Handling

- **Uploading Artifacts**: After benchmarks are run, the resulting `0001_output.json` file is uploaded as an artifact to GitHub Actions, allowing it to be used in future benchmark comparisons.
- **Downloading Artifacts**: In subsequent CI runs, the previously saved benchmark artifact (`0001_output.json`) for the master branch is downloaded before tests are run.

