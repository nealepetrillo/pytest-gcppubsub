# pytest-gcppubsub

A pytest plugin that manages the [GCP Pub/Sub emulator](https://cloud.google.com/pubsub/docs/emulator) lifecycle. Start the emulator automatically when your tests run — no manual setup required.

## Features

- **Automatic emulator management** — starts `gcloud beta emulators pubsub start` before tests and stops it after
- **pytest-xdist support** — parallel workers share a single emulator instance via file-lock coordination
- **Environment configuration** — sets `PUBSUB_EMULATOR_HOST` and `PUBSUB_PROJECT_ID` so `google-cloud-pubsub` clients connect automatically
- **Auto port assignment** — use `--pubsub-port=0` to pick a free port, avoiding conflicts
- **Async compatible** — session-scoped fixture works with `pytest-asyncio` out of the box

## Prerequisites

The [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) must be installed with the Pub/Sub emulator component:

```bash
gcloud components install pubsub-emulator
```

## Installation

```bash
pip install pytest-gcppubsub
```

To also install the `google-cloud-pubsub` client library (for the optional client fixtures):

```bash
pip install pytest-gcppubsub[client]
```

## Quick Start

Request the `pubsub_emulator` fixture in your tests:

```python
def test_publish_message(pubsub_emulator):
    from google.cloud import pubsub_v1

    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(pubsub_emulator.project, "my-topic")
    publisher.create_topic(request={"name": topic_path})

    future = publisher.publish(topic_path, b"hello world")
    future.result()
```

The plugin starts the emulator once per session and sets the environment variables so all `google-cloud-pubsub` clients route to it automatically.

## Fixtures

### `pubsub_emulator` (session-scoped)

Starts the Pub/Sub emulator and yields an `EmulatorInfo` object:

| Attribute | Type | Description |
|-----------|------|-------------|
| `host` | `str` | Emulator host (e.g. `localhost`) |
| `port` | `int` | Emulator port |
| `project` | `str` | GCP project ID |
| `host_port` | `str` | Combined `host:port` string |

Sets `PUBSUB_EMULATOR_HOST` and `PUBSUB_PROJECT_ID` environment variables for the session and restores them on teardown.

### `pubsub_publisher_client` (function-scoped)

Returns a `pubsub_v1.PublisherClient` connected to the emulator. Skips the test if `google-cloud-pubsub` is not installed.

### `pubsub_subscriber_client` (function-scoped)

Returns a `pubsub_v1.SubscriberClient` connected to the emulator. Skips the test if `google-cloud-pubsub` is not installed.

## Configuration

Settings can be provided via CLI flags or `pyproject.toml` / `pytest.ini`. CLI flags take precedence.

| CLI Flag | ini Option | Default | Description |
|----------|-----------|---------|-------------|
| `--pubsub-host` | `pubsub_emulator_host` | `localhost` | Emulator bind host |
| `--pubsub-port` | `pubsub_emulator_port` | `8085` | Emulator port (`0` for auto) |
| `--pubsub-project` | `pubsub_project_id` | `test-project` | GCP project ID |
| `--pubsub-timeout` | `pubsub_emulator_timeout` | `15` | Startup timeout (seconds) |

Example `pyproject.toml`:

```toml
[tool.pytest.ini_options]
pubsub_project_id = "my-test-project"
pubsub_emulator_port = "0"
```

## pytest-xdist Support

When running with `pytest-xdist`, the plugin coordinates workers so that only the first worker starts the emulator. Subsequent workers attach to the running instance. The last worker to finish tears it down. This uses file-lock based coordination and handles stale processes from crashed runs.

```bash
pytest -n auto  # all workers share one emulator
```

## Async Tests

The `pubsub_emulator` fixture is session-scoped and synchronous, which is compatible with async test functions. Since `PUBSUB_EMULATOR_HOST` is set in the environment, async clients like `PublisherAsyncClient` connect to the emulator automatically:

```python
import pytest
from google.cloud.pubsub_v1 import PublisherAsyncClient

@pytest.fixture
async def async_publisher(pubsub_emulator):
    return PublisherAsyncClient()

async def test_async_publish(async_publisher, pubsub_emulator):
    topic = f"projects/{pubsub_emulator.project}/topics/my-topic"
    await async_publisher.create_topic(request={"name": topic})
```

## License

MIT
