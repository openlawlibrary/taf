import json
import os
import pytest
from pathlib import Path

from taf.utils import (
    TempPartition,
    _background_cleanup_threads,
    normalize_line_endings,
    safely_save_json_to_disk,
    safely_move_file,
)


def test_normalize_line_ending_extra_lines():
    test_content = b"""This is some text followed by two new lines


"""
    expected_content = b"This is some text followed by two new lines"
    replaced_content = normalize_line_endings(test_content)
    assert replaced_content == expected_content


def test_normalize_line_ending_no_new_line():
    test_content = b"This is some text without new line at the end of the file"
    expected_content = test_content
    replaced_content = normalize_line_endings(test_content)
    assert replaced_content == expected_content


def test_safely_save_json_to_disk_new_file(output_path):
    data = {"a": 1, "b": 2}
    dst_path = output_path / "new_test.json"
    safely_save_json_to_disk(data, dst_path)
    saved_text = dst_path.read_text()
    assert saved_text
    saved_json = json.loads(saved_text)
    assert len(saved_json)
    assert saved_json == data


def test_safely_save_json_to_disk_existing_file(output_path):
    data = {"a": 1, "b": 2}
    dst_path = output_path / "existing_test.json"
    dst_path.touch()
    safely_save_json_to_disk(data, dst_path)
    saved_text = dst_path.read_text()
    assert saved_text
    saved_json = json.loads(saved_text)
    assert len(saved_json)
    assert saved_json == data


def test_temp_partition_cleanup_async(output_path):
    temp_partition = TempPartition(Path(output_path))
    temp_dir = Path(temp_partition.temp_dir)
    for index in range(3):
        subdir = temp_dir / f"repo{index}" / "nested"
        subdir.mkdir(parents=True)
        (subdir / "file.txt").write_text("data")

    temp_partition.cleanup_async()

    # the temp dir is renamed away immediately, so a new TempPartition in the
    # same location would not collide with it
    assert not temp_dir.exists()
    for thread in _background_cleanup_threads:
        thread.join(timeout=30)
    assert not list(temp_dir.parent.glob(f"*{TempPartition.TRASH_SUFFIX}"))


def test_temp_partition_sweeps_stale_trash(output_path):
    first = TempPartition(Path(output_path))
    stale_trash = Path(f"{first.temp_dir}stale{TempPartition.TRASH_SUFFIX}")
    (stale_trash / "leftover").mkdir(parents=True)

    second = TempPartition(Path(output_path))

    assert not stale_trash.exists()
    first.cleanup()
    second.cleanup()


def test_temp_partition_sweep_skips_foreign_owned_trash(output_path, monkeypatch):
    # the sweep must not delete trash dirs owned by a different user (shared
    # /tmp on POSIX); simulate by making os.getuid return a uid that differs
    # from the trash dir's owner
    if not hasattr(os, "getuid"):
        pytest.skip("ownership check is POSIX-only")

    first = TempPartition(Path(output_path))
    foreign_trash = Path(f"{first.temp_dir}foreign{TempPartition.TRASH_SUFFIX}")
    (foreign_trash / "leftover").mkdir(parents=True)

    real_uid = os.stat(foreign_trash).st_uid
    monkeypatch.setattr(os, "getuid", lambda: real_uid + 1)

    second = TempPartition(Path(output_path))

    assert foreign_trash.exists()  # not ours -> left untouched
    import shutil as _shutil

    _shutil.rmtree(foreign_trash)
    first.cleanup()
    second.cleanup()


def test_safely_move_file_same_filesystem(output_path):
    src_path = output_path / "src.txt"
    data = "some test data"
    src_path.write_text(data)
    dst_path = output_path / "dst.txt"
    safely_move_file(src_path, dst_path, overwrite=True)
    assert not src_path.is_file()
    assert dst_path.is_file()
    assert dst_path.read_text() == data
