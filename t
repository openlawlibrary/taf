[1mdiff --git a/taf/git.py b/taf/git.py[m
[1mindex 2af3a3d..f89b454 100644[m
[1m--- a/taf/git.py[m
[1m+++ b/taf/git.py[m
[36m@@ -786,7 +786,7 @@[m [mclass GitRepository:[m
             return self.pygit.list_files_at_revision(commit, path)[m
         except TAFError as e:[m
             raise e[m
[31m-        except Exception:[m
[32m+[m[32m        except Exception as e:[m
             self._log_warning([m
                 "Perfomance regression: Could not list files with pygit2. Reverting to git subprocess"[m
             )[m
[1mdiff --git a/taf/tests/test_updater.py b/taf/tests/test_updater.py[m
[1mindex f0c9a21..65cdd48 100644[m
[1m--- a/taf/tests/test_updater.py[m
[1m+++ b/taf/tests/test_updater.py[m
[36m@@ -399,8 +399,8 @@[m [mdef test_update_repo_wrong_flag(updater_repositories, origin_dir, client_dir):[m
 [m
 [m
 def test_update_repo_target_in_indeterminate_state(updater_repositories, origin_dir, client_dir):[m
[31m-    repositories = updater_repositories["test-updater-target-repository-has-uncommitted-changes"][m
[31m-    origin_dir = origin_dir / "test-updater-valid"[m
[32m+[m[32m    repositories = updater_repositories["test-updater-target-repository-has-indeterminate-state"][m
[32m+[m[32m    origin_dir = origin_dir / "test-updater-target-repository-has-indeterminate-state"[m
 [m
     targets_repo_path = client_dir / TARGET_REPO_REL_PATH[m
 [m
[1mdiff --git a/taf/updater/updater.py b/taf/updater/updater.py[m
[1mindex b1ecd0c..34bb41c 100644[m
[1m--- a/taf/updater/updater.py[m
[1m+++ b/taf/updater/updater.py[m
[36m@@ -1084,6 +1084,7 @@[m [mdef _merge_commit(repository, branch, commit_to_merge, checkout=True):[m
         # current git repository has uncommitted changes:[m
         # we do not want taf to lose any repo data, so we do not reset the repository.[m
         # for now, raise an update error and let the user manually reset the repository[m
[32m+[m[32m        breakpoint()[m
         taf_logger.error([m
             "Could not checkout branch {} during commit merge. Error {}", branch, e[m
         )[m
