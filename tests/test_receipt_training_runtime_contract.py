"""Local runtime/workflow contracts; never submit a job or require credentials."""

import signal
import time
from pathlib import Path

import pytest

from scripts import dispatch_receipt_training as dispatcher
from tests.test_receipt_training_worker import make_manifest


ROOT = Path(__file__).resolve().parents[1]
POSIX_TIMERS = hasattr(signal, "setitimer") and hasattr(signal, "SIGALRM")


def test_cancellation_signals_are_sanitized_and_handlers_restored(monkeypatch):
    handlers = {signal.SIGINT: object(), signal.SIGTERM: object()}
    original = handlers.copy()

    def install(signum, handler):
        previous = handlers[signum]
        handlers[signum] = handler
        return previous

    monkeypatch.setattr(signal, "signal", install)
    with pytest.raises(dispatcher.DispatchError, match="RUNNER_INTERRUPTED"):
        with dispatcher.cancellation_guard():
            handlers[signal.SIGTERM](signal.SIGTERM, None)
    assert handlers == original


def test_cloud_cli_requires_absolute_timer_capability(monkeypatch):
    monkeypatch.delattr(signal, "setitimer", raising=False)
    with pytest.raises(dispatcher.DispatchError, match="BOUNDED_LINUX_RUNNER_REQUIRED"):
        with dispatcher.deadline_guard(1, required=True):
            pytest.fail("unsupported execution was admitted")


def test_cli_sanitizes_receipt_directory_creation_failure(monkeypatch, capsys):
    def fail_sink(path):
        raise OSError("private path detail")

    monkeypatch.setattr(dispatcher, "ReceiptSink", fail_sink)
    monkeypatch.setattr("sys.argv", ["dispatch"])
    assert dispatcher.main() == 1
    assert capsys.readouterr().out.strip() == "DISPATCH_FAILED"


@pytest.mark.skipif(not POSIX_TIMERS, reason="Production deadline enforcement uses Linux POSIX timers")
def test_absolute_deadline_interrupts_non_yielding_blocking_operation():
    previous = signal.getsignal(signal.SIGALRM)
    started = time.monotonic()
    with pytest.raises(dispatcher.DispatchError, match="OPERATION_DEADLINE_EXCEEDED"):
        with dispatcher.deadline_guard(0.05, required=True):
            time.sleep(5)
    assert time.monotonic() - started < 2
    assert signal.getsignal(signal.SIGALRM) == previous
    assert signal.getitimer(signal.ITIMER_REAL)[0] == 0


@pytest.mark.skipif(not POSIX_TIMERS, reason="Production deadline enforcement uses Linux POSIX timers")
def test_nested_phase_cannot_extend_outer_deadline():
    started = time.monotonic()
    with pytest.raises(dispatcher.DispatchError, match="OPERATION_DEADLINE_EXCEEDED"):
        with dispatcher.deadline_guard(0.05, required=True):
            with dispatcher.deadline_guard(20):
                time.sleep(5)
    assert time.monotonic() - started < 2
    assert signal.getitimer(signal.ITIMER_REAL)[0] == 0


@pytest.mark.skipif(not POSIX_TIMERS, reason="Production deadline enforcement uses Linux POSIX timers")
def test_sdk_log_keepalives_are_interrupted_without_yielding():
    provider = dispatcher.HFProvider.__new__(dispatcher.HFProvider)

    class API:
        def fetch_job_logs(self, **kwargs):
            time.sleep(5)
            yield "never reached"

    provider.api = API()
    with pytest.raises(dispatcher.DispatchError, match="OPERATION_DEADLINE_EXCEEDED"):
        with dispatcher.deadline_guard(0.05, required=True):
            provider.result("offline-job-only")


def test_workflow_manual_main_only_and_candidate_job_is_separate():
    workflow = (ROOT / ".github/workflows/hf-estate-ops.yml").read_text()
    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "if: inputs.op != 'launch-train-job'" in workflow
    assert "if: inputs.op == 'launch-train-job'" in workflow
    assert 'if op == "launch-train-job":' not in workflow
    assert "curl -" not in workflow
    assert "environment: hf-training" in workflow
    assert "HF_TOKEN: ${{ secrets.TRAINING_HF_TOKEN }}" in workflow
    assert "INPUT_TRAINING_MANIFEST: ${{ inputs.training_manifest }}" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "persist-credentials: false" in workflow
    assert "--submit --receipt-dir training-receipts" in workflow
    assert "if: always()" in workflow
    manifest = make_manifest()
    manifest["runtime"]["timeout_seconds"] = 14400
    manifest["authorization"].update(max_hourly_usd=1, max_cost_usd=4)
    dispatcher.validate_manifest(manifest)
    training_job = workflow.split("receipt-training:", 1)[1]
    minutes = int(training_job.split("timeout-minutes:", 1)[1].splitlines()[0])
    assert minutes * 60 >= manifest["runtime"]["timeout_seconds"] + 1200


def test_contract_ci_runs_all_three_offline_suites_without_secrets():
    workflow = (ROOT / ".github/workflows/training-contract.yml").read_text()
    assert "pull_request:" in workflow
    assert "secrets." not in workflow
    assert "--submit" not in workflow
    for name in ("worker", "dispatch", "runtime_contract"):
        assert f"tests/test_receipt_training_{name}.py" in workflow
