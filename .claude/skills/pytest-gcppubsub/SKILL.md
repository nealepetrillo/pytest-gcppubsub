---
name: pytest-gcppubsub
description: "pytest plugin for managing a GCP Pub/Sub emulator during test sessions. Use when: (1) Writing tests for code that publishes or subscribes to Google Cloud Pub/Sub topics, (2) Needing a real Pub/Sub emulator (via gcloud) managed automatically by pytest, (3) Adding pytest fixtures for Pub/Sub publisher or subscriber clients, (4) Configuring Pub/Sub emulator host/port/project in pytest, (5) Running Pub/Sub tests in parallel with pytest-xdist, (6) Writing async tests against Pub/Sub with pytest-asyncio, (7) A project depends on pytest-gcppubsub."
---

# pytest-gcppubsub

pytest plugin that manages a GCP Pub/Sub emulator (`gcloud beta emulators pubsub`) for the test session. Requires Google Cloud SDK with the `pubsub-emulator` component installed.

## Installation

```bash
pip install pytest-gcppubsub            # emulator management only
pip install pytest-gcppubsub[client]    # includes google-cloud-pubsub client fixtures
```

## Fixtures

### `pubsub_emulator` (session-scoped)

Starts the emulator once per session, sets environment variables, yields `EmulatorInfo`, and tears down on session end.

**Environment variables set automatically:**
- `PUBSUB_EMULATOR_HOST` = `"{host}:{port}"`
- `PUBSUB_PROJECT_ID` = configured project ID

**`EmulatorInfo` attributes:**
- `host: str` — emulator host (e.g. `"localhost"`)
- `port: int` — emulator port
- `project: str` — GCP project ID
- `host_port: str` — combined `"{host}:{port}"` (property)

```python
def test_publish(pubsub_emulator):
    from google.cloud import pubsub_v1

    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(pubsub_emulator.project, "my-topic")
    publisher.create_topic(request={"name": topic_path})
    future = publisher.publish(topic_path, b"hello")
    assert future.result()
```

### `pubsub_publisher_client` (function-scoped)

Returns a `google.cloud.pubsub_v1.PublisherClient` connected to the emulator. Auto-skips if `google-cloud-pubsub` is not installed. Requires `pubsub_emulator`.

```python
def test_create_topic(pubsub_publisher_client, pubsub_emulator):
    topic = pubsub_publisher_client.create_topic(
        request={"name": f"projects/{pubsub_emulator.project}/topics/t1"}
    )
    assert topic.name.endswith("/topics/t1")
```

### `pubsub_subscriber_client` (function-scoped)

Returns a `google.cloud.pubsub_v1.SubscriberClient` connected to the emulator. Auto-skips if `google-cloud-pubsub` is not installed. Requires `pubsub_emulator`.

## Configuration

| CLI flag | INI option | Default | Description |
|---|---|---|---|
| `--pubsub-host` | `pubsub_emulator_host` | `localhost` | Emulator bind host |
| `--pubsub-port` | `pubsub_emulator_port` | `8085` | Port (`0` = auto-assign) |
| `--pubsub-project` | `pubsub_project_id` | `test-project` | GCP project ID |
| `--pubsub-timeout` | `pubsub_emulator_timeout` | `15` | Startup timeout (seconds) |

CLI flags override INI options. Example `pyproject.toml`:

```toml
[tool.pytest.ini_options]
pubsub_emulator_host = "localhost"
pubsub_emulator_port = "0"
pubsub_project_id = "my-test-project"
```

## pytest-xdist Support

Works automatically. When xdist workers are detected (`hasattr(config, "workerinput")`), the plugin uses `tmp_path_factory.getbasetemp().parent` to locate a shared temp directory across all workers, then coordinates via a file lock (`.pubsub_emulator/` subdirectory) so only one emulator runs. All workers share it; the last worker to finish tears it down.

The `pubsub_emulator` fixture accepts `tmp_path_factory: pytest.TempPathFactory` for this coordination.

## Async Testing

The emulator and env vars are session-scoped, so async clients work naturally:

```python
import pytest
from google.cloud.pubsub_v1 import PublisherAsyncClient

@pytest.fixture
async def async_publisher(pubsub_emulator):
    return PublisherAsyncClient()

@pytest.mark.asyncio
async def test_async_publish(async_publisher, pubsub_emulator):
    topic_path = f"projects/{pubsub_emulator.project}/topics/async-topic"
    await async_publisher.create_topic(request={"name": topic_path})
    result = await async_publisher.publish(topic_path, b"async msg")
    assert result
```
