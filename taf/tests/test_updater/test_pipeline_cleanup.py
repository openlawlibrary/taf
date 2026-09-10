import types
import pytest
import signal
from unittest.mock import Mock, patch
from taf.updater.lifecycle_handlers import Event
from taf.tools.cli import safe_cleanup
from taf.updater.updater_pipeline import AuthenticationRepositoryUpdatePipeline


@pytest.fixture
def dummy_pipeline():
    """Mock pipeline with real cleanup/on_interrupt hooks bound, so safe_cleanup's
    generalized dispatch is exercised against actual pipeline behavior rather than
    just recording that a Mock was called."""
    pipeline = Mock(spec=AuthenticationRepositoryUpdatePipeline)
    pipeline.only_validate = False
    pipeline.state = Mock()
    pipeline.state.existing_repo = False
    pipeline.state.users_auth_repo = "some_repo"
    pipeline.state.event = None
    pipeline.remove_temp_repositories = Mock()
    pipeline.set_output = Mock()

    # Bind the real hook implementations instead of leaving them as bare Mocks,
    # so assertions check pipeline-specific side effects (state.event, temp repo
    # removal), not just "was this called".
    pipeline.cleanup = types.MethodType(
        AuthenticationRepositoryUpdatePipeline.cleanup, pipeline
    )
    pipeline.on_interrupt = types.MethodType(
        AuthenticationRepositoryUpdatePipeline.on_interrupt, pipeline
    )
    # Note: the pipeline defines no after_interrupt. Because this Mock uses
    # spec=AuthenticationRepositoryUpdatePipeline, hasattr(pipeline, "after_interrupt")
    # is False, matching production behavior.
    return pipeline


def test_pipeline_cleanup_calls_cleanup_on_success(dummy_pipeline):
    """On normal completion, cleanup() runs: output is set and temp repos are removed."""

    @safe_cleanup
    def dummy_method(self):
        return "success"

    result = dummy_method(dummy_pipeline)

    assert result == "success"
    dummy_pipeline.set_output.assert_called_once()
    dummy_pipeline.remove_temp_repositories.assert_called_once_with(final_cleanup=True)
    assert dummy_pipeline.state.event is None


def test_pipeline_cleanup_handles_normal_exception(dummy_pipeline):
    """On a normal exception, cleanup still runs."""

    @safe_cleanup
    def dummy_method(self):
        raise ValueError("Something went wrong")

    with pytest.raises(ValueError):
        dummy_method(dummy_pipeline)

    dummy_pipeline.remove_temp_repositories.assert_called_once_with(final_cleanup=True)
    assert dummy_pipeline.state.event is None


def test_pipeline_cleanup_handles_keyboard_interrupt_without_signal(dummy_pipeline):
    """A KeyboardInterrupt raised directly (not via the OS signal path) still triggers
    cleanup, but does NOT mark the state as FAILED — that only happens through
    on_interrupt, which is wired to the signal handler, and the pipeline defines no
    after_interrupt hook for the except-block path."""

    @safe_cleanup
    def dummy_method(self):
        raise KeyboardInterrupt("Simulated Ctrl+C")

    with pytest.raises(KeyboardInterrupt):
        dummy_method(dummy_pipeline)

    dummy_pipeline.remove_temp_repositories.assert_called_once_with(final_cleanup=True)
    assert dummy_pipeline.state.event is None


@patch("signal.signal")
def test_pipeline_on_interrupt_sets_failed_event_via_signal(
    mock_signal, dummy_pipeline
):
    """A real interrupt (SIGINT/SIGTERM) fires the registered handler, which calls
    on_interrupt and marks the update FAILED; cleanup still runs afterwards."""
    captured_handlers = {}

    def fake_signal(sig, handler):
        captured_handlers[sig] = handler
        return Mock()

    mock_signal.side_effect = fake_signal

    @safe_cleanup
    def dummy_method(self):
        # Simulate the OS delivering SIGINT mid-run
        captured_handlers[signal.SIGINT](signal.SIGINT, None)

    with pytest.raises(KeyboardInterrupt):
        dummy_method(dummy_pipeline)

    assert dummy_pipeline.state.event == Event.FAILED
    dummy_pipeline.remove_temp_repositories.assert_called_once_with(final_cleanup=True)


@patch("signal.signal")
def test_pipeline_on_interrupt_skips_failed_event_when_repo_preexisting(
    mock_signal, dummy_pipeline
):
    """on_interrupt only marks FAILED when the repo isn't pre-existing, validation-only
    mode is off, and users_auth_repo is set. If the repo already existed, state.event
    is left untouched."""
    dummy_pipeline.state.existing_repo = True

    captured_handlers = {}

    def fake_signal(sig, handler):
        captured_handlers[sig] = handler
        return Mock()

    mock_signal.side_effect = fake_signal

    @safe_cleanup
    def dummy_method(self):
        captured_handlers[signal.SIGINT](signal.SIGINT, None)

    with pytest.raises(KeyboardInterrupt):
        dummy_method(dummy_pipeline)

    assert dummy_pipeline.state.event is None
    dummy_pipeline.remove_temp_repositories.assert_called_once_with(final_cleanup=True)


@patch("signal.signal")
def test_pipeline_cleanup_registers_and_restores_signal_handlers(
    mock_signal, dummy_pipeline
):
    """Ensure SIGINT and SIGTERM are overridden temporarily and restored afterwards."""
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
