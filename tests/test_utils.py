from taf.utils import normalize_line_endings


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
