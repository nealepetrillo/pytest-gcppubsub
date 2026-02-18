"""pytest plugin for GCP PubSub emulator management."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest

from pytest_gcppubsub._emulator import EmulatorInfo, PubSubEmulator


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("gcppubsub", "GCP PubSub emulator")
    group.addoption(
        "--pubsub-host",
        dest="pubsub_host",
        default=None,
        help="Emulator host (default: localhost)",
    )
    group.addoption(
        "--pubsub-port",
        dest="pubsub_port",
        default=None,
        type=int,
        help="Emulator port (default: 8085, use 0 for auto)",
    )
    group.addoption(
        "--pubsub-project",
        dest="pubsub_project",
        default=None,
        help="GCP project ID (default: test-project)",
    )
    group.addoption(
        "--pubsub-timeout",
        dest="pubsub_timeout",
        default=None,
        type=float,
        help="Emulator startup timeout in seconds (default: 15)",
    )
    parser.addini(
        "pubsub_emulator_host",
        "PubSub emulator host",
        default="localhost",
    )
    parser.addini(
        "pubsub_emulator_port",
        "PubSub emulator port",
        default="8085",
    )
    parser.addini(
        "pubsub_project_id",
        "GCP project ID for emulator",
        default="test-project",
    )
    parser.addini(
        "pubsub_emulator_timeout",
        "Emulator startup timeout in seconds",
        default="15",
    )


def _get_option(config: pytest.Config, cli: str, ini: str) -> str:
    """Get a config value, CLI flag takes precedence over ini."""
    cli_val = config.getoption(cli)
    if cli_val is not None:
        return str(cli_val)
    return str(config.getini(ini))


@pytest.fixture(scope="session")
def pubsub_emulator(
    request: pytest.FixtureRequest,
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[EmulatorInfo]:
    """Start and manage a GCP PubSub emulator for the test session."""
    config = request.config

    host = _get_option(config, "pubsub_host", "pubsub_emulator_host")
    port = int(_get_option(config, "pubsub_port", "pubsub_emulator_port"))
    project = _get_option(config, "pubsub_project", "pubsub_project_id")
    timeout = float(
        _get_option(config, "pubsub_timeout", "pubsub_emulator_timeout")
    )

    # Detect xdist worker — use the shared tmp dir above all workers' bases
    shared_dir: Path | None = None
    if hasattr(config, "workerinput"):
        root_tmp_dir = tmp_path_factory.getbasetemp().parent
        shared_dir = root_tmp_dir / ".pubsub_emulator"
        shared_dir.mkdir(exist_ok=True)

    emulator = PubSubEmulator(
        host=host,
        port=port,
        project=project,
        timeout=timeout,
        shared_dir=shared_dir,
    )

    info = emulator.start()

    # Set env vars so google-cloud-pubsub clients auto-connect
    old_host = os.environ.get("PUBSUB_EMULATOR_HOST")
    old_project = os.environ.get("PUBSUB_PROJECT_ID")
    os.environ["PUBSUB_EMULATOR_HOST"] = info.host_port
    os.environ["PUBSUB_PROJECT_ID"] = info.project

    yield info

    # Restore env vars
    if old_host is None:
        os.environ.pop("PUBSUB_EMULATOR_HOST", None)
    else:
        os.environ["PUBSUB_EMULATOR_HOST"] = old_host
    if old_project is None:
        os.environ.pop("PUBSUB_PROJECT_ID", None)
    else:
        os.environ["PUBSUB_PROJECT_ID"] = old_project

    emulator.stop()


@pytest.fixture()
def pubsub_publisher_client(
    pubsub_emulator: EmulatorInfo,
) -> object:
    """Create a PublisherClient connected to the emulator."""
    try:
        from google.cloud import pubsub_v1
    except ImportError:
        pytest.skip("google-cloud-pubsub not installed")
    return pubsub_v1.PublisherClient()


@pytest.fixture()
def pubsub_subscriber_client(
    pubsub_emulator: EmulatorInfo,
) -> object:
    """Create a SubscriberClient connected to the emulator."""
    try:
        from google.cloud import pubsub_v1
    except ImportError:
        pytest.skip("google-cloud-pubsub not installed")
    return pubsub_v1.SubscriberClient()
