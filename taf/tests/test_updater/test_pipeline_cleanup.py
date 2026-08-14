import pytest
import signal
from unittest.mock import Mock, patch
from taf.updater.lifecycle_handlers import Event
from taf.tools.cli import safe_cleanup
from taf.updater.updater_pipeline import AuthenticationRepositoryUpdatePipeline


@pytest.fixture
def dummy_pipeline():
    """Mock pipeline with required attributes for testing the decorator."""
    pipeline = Mock(spec=AuthenticationRepositoryUpdatePipeline)
    pipeline.only_validate = False
    pipeline.state = Mock()
    pipeline.state.existing_repo = False
    pipeline.state.users_auth_repo = "some_repo"
    pipeline.state.event = None
    pipeline.remove_temp_repositories = Mock()
    return pipeline


def test_pipeline_cleanup_calls_cleanup_on_success(dummy_pipeline):
    """On normal completion, cleanup is called once."""

    @safe_cleanup
    def dummy_method(self):
        return "success"

    result = dummy_method(dummy_pipeline)
    assert result == "success"
    dummy_pipeline.remove_temp_repositories.assert_called_once()


def test_pipeline_cleanup_handles_keyboard_interrupt(dummy_pipeline):
    """On Ctrl+C, cleanup is called and state is set to FAILED."""

    @safe_cleanup
    def dummy_method(self):
        raise KeyboardInterrupt("Simulated Ctrl+C")

    with pytest.raises(KeyboardInterrupt):
        dummy_method(dummy_pipeline)

    dummy_pipeline.remove_temp_repositories.assert_called_once()
    assert dummy_pipeline.state.event == Event.FAILED


def test_pipeline_cleanup_handles_normal_exception(dummy_pipeline):
    """On a normal exception, cleanup is still called."""

    @safe_cleanup
    def dummy_method(self):
        raise ValueError("Something went wrong")

    with pytest.raises(ValueError):
        dummy_method(dummy_pipeline)

    dummy_pipeline.remove_temp_repositories.assert_called_once()


@patch("signal.signal")
def test_pipeline_cleanup_registers_and_restores_signal_handlers(
    mock_signal, dummy_pipeline
):
    """Ensure SIGINT and SIGTERM are overridden temporarily."""
    original_sigint = Mock()
    original_sigterm = Mock()
    mock_signal.side_effect = [
        original_sigint,
        original_sigterm,
        original_sigint,
        original_sigterm,
    ]

    @safe_cleanup
    def dummy_method(self):
        return "ok"

    dummy_method(dummy_pipeline)

    assert mock_signal.call_count == 4
    # Setting handlers
    assert mock_signal.call_args_list[0][0][0] == signal.SIGINT
    assert mock_signal.call_args_list[1][0][0] == signal.SIGTERM
    # Restoring handlers
    assert mock_signal.call_args_list[2][0][0] == signal.SIGINT
    assert mock_signal.call_args_list[3][0][0] == signal.SIGTERM
