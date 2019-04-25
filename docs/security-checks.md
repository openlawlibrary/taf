# Security checks

## Branches

The following checks are meant to validate branches of the authentication repository and the target repositories.
Creation of branches is not meant to be one of TAF's responsibilities - it can only be used to validate already
existing branches. In order to create a branch that can later be validated by TAF, the following should be taken
into consideration:
- For each branch of a target repository that needs to be validated, there should be a branch of the
same name in the authentication repository.
- For each commit of the target repository's branch, there should be a commit on the authentication repository's branch of the same name. Commit SHA of the target repository's commit should match the commit SHA stored in the corresponding target file of the authentication repository.
- To increase security of the branches, authentication repository's branch should contain a branch
 identifier. That is, a target file called `branch`, present at each commit of that branch. The
 content of that file should be the same for all commits and should uniquely identify the branch.
-  There should be a target file called `capstone` at the end of the authentication branch.

The validation of branches includes the following:

1. Check if commit SHA of each commit on a target repository's branch matches value of the commit
SHA specified in the corresponding authentication repository's target file at the corresponding revision.
2. Check if versions of TUF metadata increase by one from one commit to the next commit of the authentication repository's branch.
3. If branch IDs are the same for each commit of the authentication repository's branch.
4. Capstone.

The first two checks should detect if a commit was removed from a branch of an authentication
repository (there will be inconsistences in version numbers) or one or more target repositories
(there will be a mismatch between commits and TUF metadata), as well unauthorized pushes to branches
of the target repositories (the SHAs of commits won't be noted in TUF) metadata. Unauthorized pushes
to the authentication repository should be evident by invalid metadata files.

### Branch IDs

This check is designed to detect if someone replaced one or more commits of the authentication
repository's branch with other valid commits (for instance, with commits of an older branch). This
check is only possible if, as noted above, `branch` target files have been generated and committed
while creating the branches. If a commit is replaced with a valid commit of an older branch, IDs of
branches won't match. If someone replaced a commit of a target repository without also replacing
the corresponding authentication repository commit, that attack would be detected while comparing
target commit SHAs with TUF metadata.

### Capstone

One of the attacks which could occur could consists of someone force pushing to the branch of the
authentication repository, thus removing one or more top commits. This is not the same as
someone pushing a new, invalid commit to the branch, in which case checking validity of metadata
should indicate a problem. However, a missing commit could not be detected in that way, since the
metadata is valid. So, the solution is to add an additional target file, called
`capstone`. If the last commit of the authentication repository does not have a target `capstone`
file, we can know that someone force pushed to the branch. Similarly to the previous check, this
check is only possible if the `capstone` was added while creating the branch.
