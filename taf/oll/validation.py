from .exceptions import InvalidBranch


def validate_branch(auth_repo, branch_name):
  """
  This should check the following:
  - If all commits on a speculative branch have the same date in their repository metadata.
  - If commit sha of each commit of a speculative branch matches
  value of that repo's target in targets.json.
  - If versions of tuf metadata increases by one from one commit
  to the next commit of a speculative branch in the authentication repository
  """
  # for now create the target repositories based on the the HEAD targets.json
  # assuming that all commits on a branch (including the branching commit)
  # have the same target repositories defined in targets.json
  # TODO what if a user wants to start protecting a new repository?

  target_repos = auth_repo.targets()
  targets_and_commits = {target_repo: target_repo.
                         commits_on_branch_and_not_other(branch_name, 'master')
                         for target_repo in target_repos}

  auth_commits = auth_repo.commits_on_branch_and_not_other(branch_name, 'master')
  _check_lengths_of_branches(targets_and_commits)

  targets_version = None

  # Commits of authentication repository's branches should not be merged into master directly
  # in order to avoid merging timestamp and snapshot which could expire before a commit
  # is merged. On the other hand, commit belonging to branches of speculative repositories
  # are merged into master. This means that the number of commits not yet merged into master
  # for a given branch should be the same for all target repositories. However, that
  # number will, unless no commits have been merged yet, not correspond to the number
  # of commits of the matching authentication repository's branch.
  # Top n commits of the authentication repsitory's branch should correspond to the commits
  # target repositories' commits.Commits are ordered from the one at the end of the branch
  # to the branching commit

  # fill the shorter lists with None values, so that their sizes matches the sizes
  # of authentication repository's commits list
  for commits in targets_and_commits.values():
    commits.extend([None] * (len(auth_commits) - len(commits)))

  for commit_index in range(auth_commits):
    auth_commit = auth_commits[commit_index]
    # load content of targets.json
    targets = auth_repo.get_json(auth_commit, 'metadata/targets.json')
    for target, target_commits in targets_and_commits.items():
      target_commit = target_commits[commit_index]

      # check if codified-xml and html commits match the target commits specified in the tuf repo
      if target_commit is not None:
        _compare_commit_with_targets_metadata(auth_repo, auth_commit, target, target_commit)
        # _check_commits

      targets_version = _check_targets_version(targets, auth_commit, targets_version)


def _check_lengths_of_branches(targets_and_commits, branch_name):
  """
   Speculative branches of -xml-codified and -html repositories should always have the same
   length. Initially, authentication repo's speculative branch will have that same length
   too. However, once the first set of commits is merged, this will change. Commits on
   -xml-codified and -html repositories' speculative branches are merged into the master
   branches of these repos, unlike authentication repository's speculative commits.
   In case of the auth repo, new commits are created, with freshly generated snapshot
   and timestamp. So, -xml-codified and -xml speculative branches will become shorter
   after every merge.
   """

  lengths = set(len(commits) for commits in targets_and_commits.values())
  if len(lengths) > 1:
    msg = f'Branches {branch_name} of target repositories have a different number of commits'
    for target, commits in targets_and_commits.items():
      msg += f'\n{target.target_path} has {len(commits)} commits.'
    raise InvalidBranch(msg)


def _check_commits():
  pass


def _check_targets_version(targets, tuf_commit, current_version):
  """
  Checks version numbers specified in targets.json (compares it to the previous one)
  There are no other metadata files to check (when building a speculative branch, we do
  not generate snapshot and timestamp, just targets.json and we have no delegations)
  Return the read version number
  """
  new_version = targets['signed']['version']
  # substracting one because the commits are in the reverse order
  if current_version and new_version != current_version - 1:
    raise InvalidBranch(f'Version of metadata file targets.json at revision '
                        f'{tuf_commit} is not equal to previous version incremented '
                        'by one!')
  return new_version


def _compare_commit_with_targets_metadata(tuf_repo, tuf_commit, target_repo, target_repo_commit):
  """
  Check if commit sha of a repository's speculative branch commit matches the
  specified target value in targets.json.
  """
  targets_head_sha = tuf_repo.get_json(tuf_commit, f'targets/{target_repo.target_path}')['commit']
  if repo_commit != targets_head_sha:
    raise InvalidBranch(f'Commit {repo_commit} of repository {repo.name} does '
                        'not match the commit sha specified in targets.json!')
