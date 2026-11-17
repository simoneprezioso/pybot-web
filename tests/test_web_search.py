"""Routing and excerpt formatting are deterministic; no external calls are made."""
import os
import random
import unittest
from unittest import mock

from bot import search
from bot.modules import web_search


class WebSearchRules(unittest.TestCase):
    def test_public_changing_information_is_searchable(self):
        for text in (
            "Who is the current CEO of Microsoft?",
            "Who is the CEO of Microsoft?",
            "Who's Microsoft's current CEO?",
            "Can you tell me the current CEO of Microsoft?",
            "What happened in AI news today?",
            "whats going on in AI today?",
            "What's going on in AI today?",
            "What's happening in robotics this week?",
            "who is elon musk",
            "AI news today",
            "Please tell me AI news today",
            "What are current events?",
            "What is the weather in Rome?",
            "Weather in Rome",
            "What is the latest Python version?",
            "What is Bitcoin's price now?",
            "What are the latest football scores?",
        ):
            with self.subTest(text=text):
                self.assertEqual(web_search.query_for(text), text)

    def test_stable_local_and_personal_questions_are_not_searchable(self):
        for text in (
            "What is 2 + 2?", "What is today's date?", "What day is it today?",
            "How many days until Christmas?", "How do I descale a kettle?",
            "What should I cook tonight?", "How do I make pancakes today?",
            "Hello!", "I watched the news today.", "I am going outside today.",
            "What is my current plan?", "What's your latest news?",
            "What news did I tell you today?", "What did you tell me today?",
            "What is a CEO?", "What is a president?", "What is news?",
            "What is a stock price?", "What is an exchange rate?",
            "What is the current through a resistor?", "What is the temperature in physics?",
            "How does weather affect plants today?", "How do I update Python?",
            "What's going on with my garden today?",
            "Who is at the door?", "Who is responsible for cleaning?",
            "Who is Albert Einstein?",
            "The weather today is lovely.", "The news today is depressing.",
            "The latest Python version is broken.",
            "What is Microsoft's CEO responsible for?", "What does a current CEO do?",
            "Who was the president in 2000?", "Who was Microsoft's first CEO?",
            "How do you write a news article?", "", None,
        ):
            with self.subTest(text=text):
                self.assertIsNone(web_search.query_for(text))

    def test_explicit_requests_accept_arbitrary_natural_language(self):
        for text in (
            "Search the web for how to make pancakes",
            "Please search DuckDuckGo for how to make pancakes",
            "Can you search the internet for how to make pancakes",
            "Search for how to make pancakes",
            "Look up how to make pancakes",
            "Find online how to make pancakes",
        ):
            with self.subTest(text=text):
                self.assertEqual(web_search.query_for(text), "how to make pancakes")

    def test_manual_web_query_is_parsed_independently_of_automatic_configuration(self):
        for value in (None, "1", "0"):
            with mock.patch.dict(os.environ, {}):
                if value is None:
                    os.environ.pop("PYBOT_WEB_SEARCH", None)
                else:
                    os.environ["PYBOT_WEB_SEARCH"] = value
                for text, expected in (
                    ("/web AI news", "AI news"),
                    ("/web pancake recipe", "pancake recipe"),
                    ("/web   how to make pancakes  ", "how to make pancakes"),
                ):
                    with self.subTest(value=value, text=text):
                        self.assertEqual(web_search.query_for(text), expected)

    def test_manual_web_requires_an_exact_command_and_nonempty_query(self):
        for text in ("/web", "/web   ", "/webbing AI news", "/website AI news"):
            with self.subTest(text=text):
                self.assertIsNone(web_search.query_for(text))

    def test_manual_web_arbiter_hooks_do_not_perform_io(self):
        with mock.patch.dict(os.environ, {}), mock.patch.object(search, "search") as lookup:
            os.environ.pop("PYBOT_WEB_SEARCH", None)
            for text in ("/web AI news", "/web"):
                with self.subTest(text=text):
                    self.assertTrue(web_search.TAKES_AS_IT_COMES(text, {}))
                    self.assertTrue(web_search.CLAIMS_INSTEAD(text, {}))
            lookup.assert_not_called()

    def test_existing_safety_thread_blocks_manual_web_without_io(self):
        memory = {"turns": [{"module": "safety", "bot": "Emergency response"}]}
        with mock.patch.dict(os.environ, {}), mock.patch.object(search, "search") as lookup:
            os.environ.pop("PYBOT_WEB_SEARCH", None)
            self.assertIsNone(web_search.query_for("/web AI news", memory))
            self.assertIsNone(web_search.respond("/web AI news", memory))
            lookup.assert_not_called()

    def test_environment_opt_in_is_explicit(self):
        for value in ("1", "true", "TRUE", "yes", "on", " 1 "):
            with self.subTest(value=value), mock.patch.dict(os.environ, {"PYBOT_WEB_SEARCH": value}):
                self.assertTrue(web_search.enabled())
        for value in ("", "0", "false", "no", "off", "anything"):
            with self.subTest(value=value), mock.patch.dict(os.environ, {"PYBOT_WEB_SEARCH": value}):
                self.assertFalse(web_search.enabled())

    def test_status_does_not_probe_package_when_disabled(self):
        with mock.patch.dict(os.environ, {"PYBOT_WEB_SEARCH": "0"}), \
                mock.patch.object(web_search, "_package_available") as available:
            self.assertRegex(web_search.status_message(), r"off|disabled")
            available.assert_not_called()

    def test_search_request_is_not_mistaken_for_a_capability_question(self):
        with mock.patch.dict(os.environ, {"PYBOT_WEB_SEARCH": "1"}), \
                mock.patch.object(search, "search", return_value=search.SearchResponse()) as lookup:
            reply = web_search.respond("Can you search the internet for Python releases?", {})
            lookup.assert_called_once_with("Python releases?", max_results=3, timeout=5, timelimit=None)
            self.assertIn("No useful search results", reply)

    def test_public_person_mentioned_in_chat_keeps_local_recall(self):
        memory = {"turns": [{"user": "My friend is Alex Smith.", "bot": "Noted."}]}
        self.assertIsNone(web_search.query_for("Who is Alex Smith?", memory))

    def test_disabled_and_local_queries_never_call_transport(self):
        with mock.patch.object(search, "search") as lookup:
            with mock.patch.dict(os.environ, {"PYBOT_WEB_SEARCH": "0"}):
                self.assertIsNone(web_search.respond("Search for current AI news", {}))
            with mock.patch.dict(os.environ, {"PYBOT_WEB_SEARCH": "1"}):
                self.assertIsNone(web_search.respond("What is 2 + 2?", {}))
            lookup.assert_not_called()

    def test_arbiter_declarations_do_not_search(self):
        with mock.patch.dict(os.environ, {"PYBOT_WEB_SEARCH": "1"}), \
                mock.patch.object(search, "search") as lookup:
            for _ in range(3):
                self.assertTrue(web_search.TAKES_AS_IT_COMES("Who is the CEO of Microsoft?", {}))
                self.assertTrue(web_search.CLAIMS_INSTEAD("Who is the CEO of Microsoft?", {}))
            lookup.assert_not_called()

    def test_safety_guard_preserves_memory_and_random_wording(self):
        from bot.modules import safety

        memory = {"turns": []}
        before = random.getstate()

        def emergency(text, isolated):
            isolated["safety_case"] = "general"
            random.random()
            return "Existing emergency reply"

        with mock.patch.dict(os.environ, {"PYBOT_WEB_SEARCH": "1"}), \
                mock.patch.object(safety, "respond", side_effect=emergency), \
                mock.patch.object(search, "search") as lookup:
            self.assertIsNone(web_search.respond("What is the latest news?", memory))
            lookup.assert_not_called()
        self.assertEqual(memory, {"turns": []})
        self.assertEqual(random.getstate(), before)

    def test_existing_safety_thread_does_not_search(self):
        memory = {"turns": [{"module": "safety", "bot": "Emergency response"}]}
        with mock.patch.dict(os.environ, {"PYBOT_WEB_SEARCH": "1"}), \
                mock.patch.object(search, "search") as lookup:
            self.assertIsNone(web_search.respond("Search the web for today's news", memory))
            lookup.assert_not_called()

    def test_freshness_filters_follow_query(self):
        for query, expected in (
            ("AI news today", "d"), ("breaking AI news", "d"),
            ("AI news this week", "w"), ("AI news this month", "m"),
            ("Who is the current CEO of Microsoft?", None),
        ):
            with self.subTest(query=query), mock.patch.dict(os.environ, {"PYBOT_WEB_SEARCH": "1"}), \
                    mock.patch.object(search, "search", return_value=search.SearchResponse()) as lookup:
                web_search.respond("Search the web for " + query, {})
                lookup.assert_called_once_with(query, max_results=3, timeout=5, timelimit=expected)

    def test_conflicting_snippets_are_attributed_without_inferring_an_answer(self):
        response = search.SearchResponse(results=(
            search.SearchResult("Report A", "https://example.org/a", "Person A is the CEO."),
            search.SearchResult("Report B", "https://example.net/b", "Person B is the CEO."),
        ))
        with mock.patch.dict(os.environ, {"PYBOT_WEB_SEARCH": "1"}), \
                mock.patch.object(search, "search", return_value=response):
            reply = web_search.respond("Who is the CEO of Example?", {})
        self.assertIn("not independently verified", reply)
        self.assertIn("Report A: Person A is the CEO. Source: https://example.org/a", reply)
        self.assertIn("Report B: Person B is the CEO. Source: https://example.net/b", reply)
        self.assertNotIn("\n", reply)


if __name__ == "__main__":
    unittest.main()
