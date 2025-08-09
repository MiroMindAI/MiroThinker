# Copyright 2025 Miromind.ai
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import time
from typing import Any, Sequence

import httpx

from .otlp_json import encode_spans
from .processor_interface import TracingExporter
from .spans import Span
from .traces import Trace

# import traceback

logger = logging.getLogger("miroflow")


class NoopExporter(TracingExporter):
    """
    NoopExporter does nothing. This replaces default BackendExporter.
    """

    def export(self, items: list[Trace | Span[Any]]):
        pass


class FanoutExporter(TracingExporter):
    """
    FanoutExporter is a tracing exporter that sends trace data to multiple exporters.
    It allows you to fan out the trace data to different destinations like console, file, or OpenTelemetry endpoint.
    """

    def __init__(self, exporters: Sequence[TracingExporter]):
        """
        Initialize the FanoutExporter with a list of exporters.
        :param exporters: List of TracingExporter instances.
        """
        self.exporters = exporters

    def export(self, items: list[Trace | Span[Any]]):
        for exporter in self.exporters:
            try:
                exporter.export(items)
            except Exception as e:
                logger.error(f"Failed to export trace data to {exporter}: {e}")


def _create_exponential_backoff_generator(
    max_retry_count: int, base_delay: float = 0.1, jitter: float = 0.1
):
    """
    Create a generator that yields delays for exponential backoff.
    :param max_retry_count: Maximum number of retries.
    :param base_delay: Base delay in seconds for the first retry.
    :return: A generator that yields delays for exponential backoff.
    """
    for i in range(max_retry_count):
        yield base_delay * (2**i)


def _should_retry(res: httpx.Response) -> bool:
    """
    Determine if the response indicates a retryable error.
    :param response: The HTTP response object.
    :return: True if the response indicates a retryable error, False otherwise.
    """
    if res.status_code == 408:
        return True
    if 500 <= res.status_code < 600:
        return True
    return False


class OtelExporter(TracingExporter):
    """
    OtelExporter is a tracing exporter that sends trace data to an OpenTelemetry endpoint.
    It uses the `http-json` format for exporting traces.
    """

    MAX_RETRY_COUNT = 16

    def __init__(self, endpoint: str = "http://localhost:4318/v1/traces"):
        """
        Initialize the OtelExporter with the OpenTelemetry endpoint.
        :param endpoint: The URL of the OpenTelemetry endpoint.
        """
        self.endpoint = endpoint
        self._client = httpx.Client()

    def export(self, items: list[Trace | Span[Any]]) -> None:
        headers = {"Content-Type": "application/json"}
        try:
            json_payload = encode_spans(items)
        except Exception as e:
            logger.error(f"Failed to encode spans: {e}")
            # traceback.print_exc()
            raise e
        logging.debug("json_payload: %s", json_payload)

        for delay in _create_exponential_backoff_generator(
            max_retry_count=self.MAX_RETRY_COUNT
        ):
            try:
                resp = self._client.post(
                    url=self.endpoint,
                    headers=headers,
                    content=json_payload,
                )

                if resp.status_code == 200:
                    return
                elif _should_retry(resp):
                    logger.warning(
                        f"Retrying export due to {resp.status_code} response"
                    )
                    time.sleep(delay)
                    continue
                else:
                    logger.error(
                        f"Failed to export trace data: {resp.status_code} - {resp.text}"
                    )
                    return
            except httpx.RequestError as e:
                logger.error(f"Request error during export: {e}")
                raise e
        return
