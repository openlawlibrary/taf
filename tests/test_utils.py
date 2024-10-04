import json
from taf.utils import normalize_line_endings, safely_save_json_to_disk, safely_move_file


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


def test_safely_move_file_same_filesystem(output_path):
    src_path = output_path / "src.txt"
    data = "some test data"
    src_path.write_text(data)
    dst_path = output_path / "dst.txt"
    safely_move_file(src_path, dst_path, overwrite=True)
    assert not src_path.is_file()
    assert dst_path.is_file()
    assert dst_path.read_text() == data
