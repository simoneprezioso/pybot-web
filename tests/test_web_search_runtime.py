"""Exercise optional web search through PyBot's real module and arbiter pipeline."""
import os
import unittest
from unittest import mock

from bot import runtime, search


class WebSearchRuntime(unittest.TestCase):
    def setUp(self):
        self.environment = mock.patch.dict(os.environ, {"PYBOT_WEB_SEARCH": "1"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.lookup = mock.patch("bot.search.search")
        self.search = self.lookup.start()
        self.addCleanup(self.lookup.stop)
        self.search.return_value = search.SearchResponse(results=(
            search.SearchResult(
                title="Microsoft leadership",
                url="https://www.microsoft.com/en-us/leadership",
                snippet="Satya Nadella is Microsoft's chairman and chief executive officer.",
            ),
        ))

    def test_current_ceo_uses_one_search_and_records_the_selected_turn(self):
        text = "Who is the current CEO of Microsoft?"
        memory = {}
        result = runtime.turn(text, memory)

        self.assertEqual(result["module"], "web_search")
        self.assertIn("Satya Nadella", result["reply"])
        self.assertIn("https://www.microsoft.com/en-us/leadership", result["reply"])
        self.search.assert_called_once()
        self.assertIn("Microsoft", self.search.call_args.args[0])
        self.assertEqual(memory["turns"], [{
            "user": text, "bot": result["reply"], "module": "web_search",
        }])

    def test_ai_news_returns_sourced_snippets_with_one_search(self):
        self.search.return_value = search.SearchResponse(results=(
            search.SearchResult("AI research update", "https://example.org/ai-news",
                                "Researchers announced a new AI benchmark today."),
            search.SearchResult("AI policy update", "https://example.net/ai-policy",
                                "A public consultation on AI policy opened today."),
        ))
        result = runtime.turn("What happened in AI news today?", {})

        self.assertEqual(result["module"], "web_search")
        self.assertIn("AI benchmark", result["reply"])
        self.assertIn("https://example.org/ai-news", result["reply"])
        self.assertIn("https://example.net/ai-policy", result["reply"])
        self.search.assert_called_once()

    def test_explicit_natural_language_search_uses_web_module(self):
        result = runtime.turn("Search the web for Microsoft leadership", {})

        self.assertEqual(result["module"], "web_search")
        self.assertIn("https://www.microsoft.com/en-us/leadership", result["reply"])
        self.search.assert_called_once()

    def test_equal_results_for_different_queries_keep_search_precedence(self):
        for response in (self.search.return_value, search.SearchResponse(),
                         search.SearchResponse(error="unavailable")):
            with self.subTest(response=response):
                self.search.return_value = response
                self.search.reset_mock()
                memory = {}
                for text in ("Who is the current CEO of Microsoft?", "What happened in AI news today?"):
                    result = runtime.turn(text, memory)
                    self.assertEqual(result["module"], "web_search")
                self.assertEqual(self.search.call_count, 2)

    def test_search_is_disabled_by_default(self):
        os.environ.pop("PYBOT_WEB_SEARCH", None)
        result = runtime.turn("Who is the current CEO of Microsoft?", {})

        self.assertNotEqual(result["module"], "web_search")
        self.assertTrue(result["reply"].strip())
        self.search.assert_not_called()

    def test_explicit_disable_keeps_current_questions_offline(self):
        os.environ["PYBOT_WEB_SEARCH"] = "0"
        result = runtime.turn("What happened in AI news today?", {})

        self.assertNotEqual(result["module"], "web_search")
        self.assertTrue(result["reply"].strip())
        self.search.assert_not_called()

    def test_existing_answers_and_personal_statements_do_not_search(self):
        questions = (
            "What is 2 + 2?",
            "What is today's date?",
            "How do I descale a kettle?",
            "Hello!",
            "I am going to the park today.",
            "How do I make pancakes today?",
            "The weather today is lovely.",
            "The news today is depressing.",
            "What is Microsoft's CEO responsible for?",
        )
        for text in questions:
            with self.subTest(text=text):
                result = runtime.turn(text, {})
                self.assertNotEqual(result["module"], "web_search")
                self.assertTrue(result["reply"].strip())
        self.search.assert_not_called()

    def test_personal_recall_uses_conversation_memory(self):
        memory = {}
        runtime.turn("My name is Sam.", memory)
        result = runtime.turn("What is my name?", memory)

        self.assertNotEqual(result["module"], "web_search")
        self.assertIn("Sam", result["reply"])
        self.search.assert_not_called()
        self.assertEqual(len(memory["turns"]), 2)

    def test_unavailable_internet_returns_a_graceful_search_reply(self):
        self.search.return_value = search.SearchResponse(error="unavailable")
        result = runtime.turn("Who is the current CEO of Microsoft?", {})

        self.assertEqual(result["module"], "web_search")
        self.assertTrue(result["reply"].strip())
        self.assertRegex(result["reply"].lower(), r"unavailable|unable|cannot|couldn.t|offline")
        self.assertNotIn("Satya Nadella", result["reply"])
        self.search.assert_called_once()

    def test_empty_results_do_not_fabricate_a_current_answer(self):
        self.search.return_value = search.SearchResponse(results=())
        result = runtime.turn("Who is the current CEO of Microsoft?", {})

        self.assertEqual(result["module"], "web_search")
        self.assertRegex(result["reply"].lower(), r"no .*results|couldn.t find|no results")
        self.assertNotIn("Satya Nadella", result["reply"])
        self.search.assert_called_once()

    def test_emergency_response_retains_precedence(self):
        result = runtime.turn("What is the latest news? A baby cannot breathe", {})

        self.assertEqual(result["module"], "safety")
        self.assertNotIn("https://www.microsoft.com", result["reply"])
        self.search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
