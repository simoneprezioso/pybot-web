"""Tests of the optional transport; all external search calls are mocked."""
import itertools
import math
import sys
import types
import unittest
from unittest import mock

from bot import search as transport


def row(title="Microsoft leadership", href="https://example.org/leadership", body="A search excerpt."):
    return {"title": title, "href": href, "body": body}


class SearchTransport(unittest.TestCase):
    def setUp(self):
        self.loader = mock.patch("bot.search._load_ddgs")
        self.factory = self.loader.start().return_value
        self.addCleanup(self.loader.stop)
        self.registry = mock.patch("bot.search._available_backends", return_value=frozenset(transport.BACKENDS))
        self.available = self.registry.start()
        self.addCleanup(self.registry.stop)
        self.client = self.factory.return_value
        self.client.text.return_value = [row()]

    def test_natural_language_query_uses_duckduckgo_and_client_timeout(self):
        response = transport.search(" Who is the current CEO of Microsoft?\n", timeout=7, timelimit="d")
        self.factory.assert_called_once_with(timeout=7)
        self.client.text.assert_called_once_with(
            "Who is the current CEO of Microsoft?", max_results=3,
            backend="duckduckgo", timelimit="d")
        self.assertEqual(response.results, (
            transport.SearchResult("Microsoft leadership", "https://example.org/leadership", "A search excerpt."),))
        self.assertIsNone(response.error)

    def test_empty_duckduckgo_results_use_yahoo_and_stop_on_success(self):
        self.client.text.side_effect = [[], [row()], AssertionError("Startpage should not be called")]
        response = transport.search("pancake recipe", timeout=5, timelimit="w")
        self.assertEqual(len(response.results), 1)
        self.assertIsNone(response.error)
        self.assertEqual(self.client.text.call_args_list, [
            mock.call("pancake recipe", max_results=3, backend="duckduckgo", timelimit="w"),
            mock.call("pancake recipe", max_results=3, backend="yahoo", timelimit="w"),
        ])
        self.assertEqual(self.factory.call_args_list, [mock.call(timeout=5)] * 2)

    def test_failed_and_malformed_providers_fall_back_to_startpage(self):
        self.client.text.side_effect = [ConnectionError("secret"), [row(href="javascript:bad")], [row()]]
        response = transport.search("AI news today")
        self.assertEqual(len(response.results), 1)
        self.assertIsNone(response.error)
        self.assertEqual([call.kwargs["backend"] for call in self.client.text.call_args_list],
                         ["duckduckgo", "yahoo", "startpage"])

    def test_ddgs_empty_exception_falls_back(self):
        empty = type("DDGSException", (Exception,), {})("No results found.")
        self.client.text.side_effect = [empty, [row()]]
        self.assertEqual(len(transport.search("news").results), 1)
        self.assertEqual(self.client.text.call_count, 2)

    def test_all_empty_providers_are_bounded_without_retries(self):
        self.client.text.return_value = []
        self.assertEqual(transport.search("news"), transport.SearchResponse())
        self.assertEqual(self.client.text.call_count, 3)
        self.assertEqual([call.kwargs["backend"] for call in self.client.text.call_args_list],
                         ["duckduckgo", "yahoo", "startpage"])

    def test_unregistered_or_disabled_provider_cannot_trigger_ddgs_auto(self):
        self.available.return_value = frozenset(("duckduckgo", "startpage", "grokipedia"))
        self.client.text.side_effect = [[], [row()]]
        with mock.patch("bot.search.BACKENDS", ("duckduckgo", "yahoo", "google", "unknown", "startpage")):
            response = transport.search("news")
        self.assertEqual(len(response.results), 1)
        self.assertEqual([call.kwargs["backend"] for call in self.client.text.call_args_list],
                         ["duckduckgo", "startpage"])

    def test_no_registered_allowlisted_provider_makes_no_network_calls(self):
        self.available.return_value = frozenset(("grokipedia",))
        response = transport.search("news")
        self.assertIn("No supported", response.error)
        self.factory.assert_not_called()

    def test_registry_failure_fails_closed_without_network(self):
        self.available.side_effect = ImportError("secret")
        response = transport.search("news")
        self.assertIn("could not be checked", response.error)
        self.factory.assert_not_called()

    def test_engine_registry_filters_disabled_classes(self):
        module = types.ModuleType("ddgs.engines")
        module.ENGINES = {"text": {
            "duckduckgo": type("Duckduckgo", (), {"disabled": False}),
            "google": type("Google", (), {"disabled": True}),
            "unknown": type("Unknown", (), {}),
        }}
        # Call the real helper without loading any optional package.
        self.registry.stop()
        with mock.patch.dict(sys.modules, {"ddgs.engines": module}):
            self.assertEqual(transport._available_backends(), frozenset(("duckduckgo",)))

    def test_clean_html_whitespace_controls_and_bound_text(self):
        self.client.text.return_value = [row(
            title="<b>Some &amp; title</b>\x1b\n", body="<script>bad()</script>News\t update &lt;here&gt;.\u202e")]
        result = transport.search("news").results[0]
        self.assertEqual(result.title, "Some & title")
        self.assertEqual(result.snippet, "News update <here>.")
        self.client.text.return_value = [row(title="x" * 1000, body="word " * 1000)]
        result = transport.search("news").results[0]
        self.assertLessEqual(len(result.title), 160)
        self.assertLessEqual(len(result.snippet), 360)

    def test_skip_invalid_records_and_deduplicate_urls(self):
        self.client.text.return_value = [
            None, "not a row", row(href="javascript:alert(1)"), row(title=None),
            row(href="https://EXAMPLE.org/leadership#one"),
            row(href="https://example.org/leadership#two"), row(href="https://other.org/"),
        ]
        results = transport.search("news").results
        self.assertEqual([r.url for r in results], ["https://example.org/leadership", "https://other.org/"])

    def test_reject_unsafe_or_malformed_urls(self):
        for url in ("ftp://example.org/x", "/relative", "https:///missing", "https://user:password@example.org",
                    "https://example.org:bad/x", "https://[broken", "https://example.org/a\nb",
                    "https://exa mple.org", "https://example.org/\x00", "https://example.org/\u202e",
                    "\nhttps://example.org/", "https://example.org/\n"):
            with self.subTest(url=url):
                self.client.text.return_value = [row(href=url)]
                self.assertEqual(transport.search("news").results, ())

    def test_limit_output_and_iteration(self):
        self.client.text.return_value = [row(href="https://example.org/%s" % i) for i in range(10)]
        self.assertEqual(len(transport.search("news", max_results=2).results), 2)
        self.client.text.return_value = itertools.repeat(None)
        self.assertEqual(transport.search("news").results, ())

    def test_empty_and_malformed_result_sets(self):
        for rows in ([], None, [None], [{}]):
            with self.subTest(rows=rows):
                self.client.text.return_value = rows
                self.assertEqual(transport.search("news"), transport.SearchResponse())

    def test_missing_dependency_does_not_raise(self):
        with mock.patch("bot.search._load_ddgs", side_effect=ModuleNotFoundError("no ddgs")):
            response = transport.search("news")
        self.assertIn("optional ddgs", response.error)
        self.assertEqual(response.results, ())

    def test_older_python_keeps_offline_support(self):
        with mock.patch("bot.search.sys.version_info", (3, 8, 20)):
            response = transport.search("news")
        self.assertIn("Python 3.10", response.error)
        self.factory.assert_not_called()

    def test_network_failure_and_rate_limit_have_safe_errors(self):
        for error in (ConnectionError("secret proxy credential"), OSError("offline"),
                      type("RatelimitException", (Exception,), {})("secret")):
            with self.subTest(error=error):
                self.client.text.side_effect = error
                response = transport.search("news")
                self.assertIn("unavailable", response.error)
                self.assertNotIn("secret", response.error)

    def test_both_timeout_types_are_handled(self):
        for error in (TimeoutError(), type("TimeoutException", (Exception,), {})("secret")):
            with self.subTest(error=error):
                self.client.text.side_effect = error
                response = transport.search("news")
                self.assertIn("timed out", response.error)

    def test_ddgs_no_results_exception_is_empty(self):
        self.client.text.side_effect = type("DDGSException", (Exception,), {})("No results found.")
        self.assertEqual(transport.search("news"), transport.SearchResponse())

    def test_iterator_and_constructor_failures_are_handled(self):
        def failing_iterator():
            yield row()
            raise ConnectionError("secret")
        self.client.text.return_value = failing_iterator()
        self.assertIn("unavailable", transport.search("news").error)
        self.factory.side_effect = RuntimeError("secret")
        self.assertIn("unavailable", transport.search("news").error)

    def test_invalid_arguments_do_not_call_client(self):
        cases = [dict(query=""), dict(query=None), dict(query="news", max_results=True),
                 dict(query="news", max_results=0), dict(query="news", max_results=11),
                 dict(query="news", max_results=1.5), dict(query="news", timeout=0),
                 dict(query="news", timeout=True), dict(query="news", timeout=math.inf),
                 dict(query="news", timeout=math.nan), dict(query="news", timelimit="tomorrow")]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                self.assertIsNotNone(transport.search(**kwargs).error)
        self.factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
