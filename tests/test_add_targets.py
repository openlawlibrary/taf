
from pathlib import Path
import pytest
import json
import os
from pytest import fixture
import os
from taf.git import GitRepository


@fixture(autouse=True)
def run_around_tests(taf_happy_path):
  yield
  repo = GitRepository(taf_happy_path.repository_path)
  repo.reset_to_head()
  repo.clean()
  taf_happy_path._repository.targets.clear_targets()

def test_add_targets_new_files(taf_happy_path):

  old_targets = _get_old_targets(taf_happy_path)

  json_file_content = {'attr1': 'value1', 'attr2': 'value2'}
  regular_file_content = 'this file is not empty'
  data = {
    'new_json_file': {'target': json_file_content},
    'new_file': {'target': regular_file_content},
    'empty_file': {'target': None}
  }
  taf_happy_path.add_targets(data)
  _check_target_files(taf_happy_path, data, old_targets)


def test_add_targets_nested_files(taf_happy_path):

  old_targets = _get_old_targets(taf_happy_path)

  data = {
    'inner_folder1/new_file_1': {'target': 'file 1 content'},
    'inner_folder2/new_file_2': {'target': 'file 2 content'}
  }
  taf_happy_path.add_targets(data)
  _check_target_files(taf_happy_path, data, old_targets)

def _check_target_files(repo, data, old_targets):
  targets_path = repo.targets_path
  for target_rel_path, content in data.items():
    target_path = targets_path / target_rel_path
    assert target_path.exists()
    with open(str(target_path)) as f:
      file_content = f.read()
      target_content = content['target']
      if isinstance(target_content, dict):
        content_json = json.loads(file_content)
        assert content_json == target_content
      elif target_content:
        assert file_content == target_content
      else:
        assert file_content == ''

  # make sure that everything defined in repositories.json still exists
  repository_targets = []
  repositories_path = targets_path / 'repositories.json'
  assert repositories_path.exists()
  with open(str(repositories_path)) as f:
    repositories = json.load(f)['repositories']
    for target_rel_path in repositories:
      target_path = targets_path / target_rel_path
      assert target_path.exists()
      repository_targets.append(target_rel_path)

  for old_target in old_targets:
    if old_target not in repository_targets and old_target not in data and \
      old_target not in repo._required_files:
      assert (targets_path / old_target).exists() is False


def _get_old_targets(repo):
  targets_path = repo.targets_path
  old_targets = []
  for root, _, filenames in os.walk(str(targets_path)):
    for filename in filenames:
      rel_path = os.path.relpath(str(Path(root) / filename), str(targets_path))
      old_targets.append(Path(rel_path).as_posix())
  return old_targets
