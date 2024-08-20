# Different states in TAF could be:

```
args:
    - `--force` - force all repositories into consistent state at LVC and then run updater; may lose data. provide info on all changes made to repositories in order get to consistent state (use reflog if needed)


LVC = Last Validated Commit

axis:
    - working directory
        - clean  
            - happy path
        - ~dirty~
            - DEFAULT: FAIL
            - --force: git clean -fd; git reset HEAD --hard; proceed with update
    - branch
        - correct
            - happy path
        - incorrect branch or detached HEAD?
            - DEFAULT: stay on the incorrect branch; update correct branch; provide warning that not on the correct branch
            - --force: switch to LVC branch; proceed with update
    - commit
        - at last validated commit
            - happy path
        - validatable (in authentication chain, even if it is in "future" relative to last validated commit; this could happen if you manually pull or reset --hard)
            - DEFAULT: update to LVC; proceed with update
        - not validatable (not in validation chain)
            - DEFAULT: FAIL
            - --force: force branch to LVC; proceed with update
        - trailing unvalidated commits (in law-xml-codified but not law) - we call them unauthenticated in updater
            - DEFAULT: FAIL
            - --force: reset LVC --hard; proceed with update
    - local repositories (all commits are consistent at repository level)
        - doesn't exist, no commit
            - DEFAULT: create repo; ff to LVC
    - local vs remote
        - remote is consistent with local - no trailing unauthenticated commits
            - happy path
        - remote is consistent with local - trailing unauthenticated commits on remote 
            - DEFAULT: update to last validatable commit on remote; then fail for any unauthenticate commits on repos that don't allow; notify of commits on repos that do allow
        - remote is consistent with local - trailing unauthenticated commits on local
            - DEFAULT: update to the last authenticatable commit on remote; FAIL if repo does not allow trailing commits or do nothing if repo allows trailing commits
            - --force: remove trailing commits
        - remote is consistent with local - trailing unauthenticated commits conflict on repo that allows trailing commits
            - DEFAULT: update to the last authenticatable commit on remote; FAIL
            - --force: update to the last authenticatable commit on remote; remove local commits
        - remote is inconsistent with local (i.e. both remote and local are valid but diverge)
            - DEFAULT: update to the last authenticable commit on remote; FAIL
        - remote state is not authenticatable (metadata issues, versions, keys, signing, etc.)
            - DEFAULT: Update to last authenticatable remote commit; then FAIL

States to specifically address:
    - html repo has commit with no corresponding law commit (remote is not valid so: Update to last valid/authenticatable remote commit; then FAIL)
    - local repository has valid commits that aren't on remote (remote is not valid so: Update to last valid/authenticatable remote commit; then FAIL)

Update algorithm:

- prep for update
    - this is where we address:
        - working directory axis
        - branch axis
        - commit axis (excluding commits past LVC)
        - local repositories axis
    - Get all local repositories consistent at LVC (EXCEPTION: allow commits past LVC)
        - --force: do everything you possibly can to get them to that state, if can't then fail
        - DEFAULT: can use:
            - fast forward
            - git clone for repos that have been removed
            - allowed to have commits past LVC - they will be validated during update process or FAIL at that point
- update
    - this is where we address:
        - local vs remote axis
        - commits past LVC (from commit axis)
 ```






