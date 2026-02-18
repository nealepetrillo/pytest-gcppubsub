"""Integration tests for pytest-gcppubsub using pytester."""

from __future__ import annotations

import shutil

import pytest

GCLOUD_AVAILABLE = shutil.which("gcloud") is not None
skip_no_gcloud = pytest.mark.skipif(
    not GCLOUD_AVAILABLE, reason="gcloud CLI not available"
)


class TestEmulatorLifecycle:
    """Test that the emulator starts, sets env vars, and port is reachable."""

    @skip_no_gcloud
    def test_emulator_starts_and_sets_env(self, pytester: pytest.Pytester) -> None:
        pytester.makepyfile(
            """
            import os
            import socket

            def test_env_vars_set(pubsub_emulator):
                assert os.environ["PUBSUB_EMULATOR_HOST"] == pubsub_emulator.host_port
                assert os.environ["PUBSUB_PROJECT_ID"] == pubsub_emulator.project

            def test_port_reachable(pubsub_emulator):
                sock = socket.create_connection(
                    (pubsub_emulator.host, pubsub_emulator.port), timeout=2.0
                )
                sock.close()

            def test_emulator_info_properties(pubsub_emulator):
                assert pubsub_emulator.host == "localhost"
                assert isinstance(pubsub_emulator.port, int)
                assert pubsub_emulator.project == "test-project"
                hp = f"{pubsub_emulator.host}:{pubsub_emulator.port}"
                assert pubsub_emulator.host_port == hp
            """
        )
        result = pytester.runpytest("-v", "--pubsub-port=0")
        result.assert_outcomes(passed=3)


class TestConfiguration:
    """Test configuration via ini and CLI."""

    @skip_no_gcloud
    def test_custom_project_via_ini(self, pytester: pytest.Pytester) -> None:
        pytester.makeini(
            """
            [pytest]
            pubsub_project_id = my-custom-project
            """
        )
        pytester.makepyfile(
            """
            import os

            def test_custom_project(pubsub_emulator):
                assert pubsub_emulator.project == "my-custom-project"
                assert os.environ["PUBSUB_PROJECT_ID"] == "my-custom-project"
            """
        )
        result = pytester.runpytest("-v", "--pubsub-port=0")
        result.assert_outcomes(passed=1)

    @skip_no_gcloud
    def test_cli_overrides_ini(self, pytester: pytest.Pytester) -> None:
        pytester.makeini(
            """
            [pytest]
            pubsub_project_id = ini-project
            """
        )
        pytester.makepyfile(
            """
            def test_cli_override(pubsub_emulator):
                assert pubsub_emulator.project == "cli-project"
            """
        )
        result = pytester.runpytest(
            "-v", "--pubsub-port=0", "--pubsub-project=cli-project"
        )
        result.assert_outcomes(passed=1)


class TestAutoPort:
    """Test automatic port assignment."""

    @skip_no_gcloud
    def test_port_zero_assigns_free_port(self, pytester: pytest.Pytester) -> None:
        pytester.makepyfile(
            """
            def test_auto_port(pubsub_emulator):
                assert pubsub_emulator.port != 0
                assert pubsub_emulator.port > 0
            """
        )
        result = pytester.runpytest("-v", "--pubsub-port=0")
        result.assert_outcomes(passed=1)


class TestClientFixtures:
    """Test that client fixtures are available."""

    @skip_no_gcloud
    def test_client_fixtures_available(self, pytester: pytest.Pytester) -> None:
        pytester.makepyfile(
            """
            def test_publisher(pubsub_publisher_client):
                assert pubsub_publisher_client is not None

            def test_subscriber(pubsub_subscriber_client):
                assert pubsub_subscriber_client is not None
            """
        )
        result = pytester.runpytest("-v", "--pubsub-port=0")
        # Either passed (client installed) or skipped (not installed)
        outcomes = result.parseoutcomes()
        total = outcomes.get("passed", 0) + outcomes.get("skipped", 0)
        assert total == 2
