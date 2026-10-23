"""The output normalising of the documentation tests is the same on every supported Python."""

from tests.docs.blocks import same_lines

TYPO = "NameError: name 'databse' is not defined"


def test_a_name_error_suggestion_of_newer_pythons_is_not_part_of_the_output() -> None:
    assert same_lines([TYPO], [TYPO + ". Did you mean: 'database'?"]) is None
    assert same_lines([TYPO + ". Did you mean: 'database'?"], [TYPO]) is None


def test_the_rest_of_a_name_error_line_is_still_compared() -> None:
    assert same_lines([TYPO], ["NameError: name 'databas' is not defined. Did you mean: 'database'?"]) is not None
    assert same_lines([TYPO], [TYPO + " in platform.py. Did you mean: 'database'?"]) is not None


def test_a_suggestion_of_another_error_is_still_compared() -> None:
    line = "AttributeError: 'Workspace' object has no attribute 'save'"
    assert same_lines([line], [line + ". Did you mean: 'to_json'?"]) is not None
