#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Real, loopback-only Killinchu OTLP/gRPC exporter contract.

This test emits one synthetic health span to an in-process gRPC collector.
It uses no external services, customer data or receipt/production claims.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import unittest

import grpc
from opentelemetry import trace
from opentelemetry.proto.collector.trace.v1 import (
    trace_service_pb2,
    trace_service_pb2_grpc,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vsp_otel import middleware as vsp  # noqa: E402

TRACE_ID = "1" * 32
PARENT_SPAN_ID = "2" * 16
INBOUND = f"00-{TRACE_ID}-{PARENT_SPAN_ID}-01"


class RecordingCollector(trace_service_pb2_grpc.TraceServiceServicer):
    def __init__(self):
        self.messages = []

    def Export(self, request, context):
        self.messages.append(request)
        return trace_service_pb2.ExportTraceServiceResponse()


class RealExporterTests(unittest.TestCase):
    def test_missing_or_public_endpoint_never_activates_export(self):
        tracer = vsp._Tracer("killinchu", endpoint=None)
        self.assertTrue(tracer.exporter.startswith("in-process-only:"))
        self.assertIsNone(tracer._tracer)
        disallowed = vsp._endpoint_policy("https://8.8.8.8:4317")
        self.assertFalse(disallowed["allowed"])
        self.assertEqual(disallowed["state"], "POLICY-DENIED")

    def test_real_w3c_child_span_reaches_an_exact_loopback_collector(self):
        collector = RecordingCollector()
        pool = ThreadPoolExecutor(max_workers=2)
        server = grpc.server(pool)
        trace_service_pb2_grpc.add_TraceServiceServicer_to_server(collector, server)
        port = server.add_insecure_port("127.0.0.1:0")
        self.assertGreater(port, 0)
        server.start()
        provider = None
        try:
            tracer = vsp._Tracer(
                "killinchu",
                endpoint=f"http://127.0.0.1:{port}",
            )
            self.assertTrue(tracer.exporter.startswith("otlp-grpc:configured:"))
            with tracer.server_span(
                "killinchu GET /api/killinchu/healthz",
                INBOUND,
                {"http.method": "GET", "http.route": "/api/killinchu/healthz"},
            ) as span:
                self.assertIsNotNone(span)
                context = span.get_span_context()
                self.assertEqual(context.trace_id, int(TRACE_ID, 16))
                self.assertNotEqual(context.span_id, int(PARENT_SPAN_ID, 16))
            provider = trace.get_tracer_provider()
            self.assertTrue(provider.force_flush(timeout_millis=8000))
            self.assertGreaterEqual(len(collector.messages), 1)
            resources = [resource for message in collector.messages
                         for resource in message.resource_spans]
            names = [attr.value.string_value for resource in resources
                     for attr in resource.resource.attributes
                     if attr.key == "service.name"]
            self.assertIn("killinchu", names)
            spans = [span for resource in resources
                     for scope in resource.scope_spans for span in scope.spans]
            self.assertTrue(any(
                span.trace_id.hex() == TRACE_ID
                and span.parent_span_id.hex() == PARENT_SPAN_ID
                for span in spans
            ), "An exported span must be a real W3C child of the injected parent")
        finally:
            if provider is not None and hasattr(provider, "shutdown"):
                provider.shutdown()
            server.stop(0).wait(timeout=3)
            pool.shutdown(wait=True)


if __name__ == "__main__":
    unittest.main()
