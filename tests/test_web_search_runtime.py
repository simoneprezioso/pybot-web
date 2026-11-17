"""Exercise optional web search through PyBot's real module and arbiter pipeline."""
import os
import unittest
from unittest import mock

from bot import runtime, search
from bot.modules import web_search


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

    def test_screenshot_ai_question_uses_current_search_results(self):
        self.search.return_value = search.SearchResponse(results=(
            search.SearchResult("AI news", "https://example.org/ai-today",
                                "An AI research announcement was published today."),
        ))
        result = runtime.turn("whats going on in AI today?", {})

        self.assertEqual(result["module"], "web_search")
        self.assertIn("AI research announcement", result["reply"])
        self.assertIn("https://example.org/ai-today", result["reply"])
        self.search.assert_called_once()

    def test_public_person_questions_search_regardless_of_capitalization(self):
        self.search.return_value = search.SearchResponse(results=(
            search.SearchResult("Elon Musk biography", "https://example.org/elon-musk",
                                "Elon Musk is a businessperson."),
        ))
        for text in ("Who is Elon Musk?", "who is elon musk"):
            with self.subTest(text=text):
                self.search.reset_mock()
                result = runtime.turn(text, {})
                self.assertEqual(result["module"], "web_search")
                self.assertIn("Elon Musk", result["reply"])
                self.assertIn("https://example.org/elon-musk", result["reply"])
                self.search.assert_called_once()

    def test_capability_questions_report_configuration_without_searching(self):
        questions = (
            "can you web search?",
            "can you search the web?",
            "do you have internet access?",
            "is web search enabled?",
        )
        for value, available, expected in (
            ("0", True, "off|disabled"),
            ("1", True, "enabled"),
            ("1", False, "ddgs"),
        ):
            with mock.patch.dict(os.environ, {"PYBOT_WEB_SEARCH": value}), \
                    mock.patch.object(web_search, "_package_available", return_value=available):
                for text in questions:
                    with self.subTest(value=value, available=available, text=text):
                        result = runtime.turn(text, {})
                        self.assertEqual(result["module"], "web_search")
                        self.assertRegex(result["reply"].lower(), expected)
                        if value == "0":
                            self.assertIn("--web-search", result["reply"])
                        if value == "1" and not available:
                            self.assertIn("install", result["reply"].lower())
        self.search.assert_not_called()

    def test_sequential_capability_questions_keep_truthful_search_status(self):
        for value, expected in (("0", "off|disabled"), ("1", "enabled")):
            memory = {}
            with self.subTest(value=value), \
                    mock.patch.dict(os.environ, {"PYBOT_WEB_SEARCH": value}), \
                    mock.patch.object(web_search, "_package_available", return_value=True):
                for text in ("can you web search?", "do you have internet access?"):
                    result = runtime.turn(text, memory)
                    self.assertEqual(result["module"], "web_search")
                    self.assertRegex(result["reply"].lower(), expected)
                self.assertEqual(len(memory["turns"]), 2)
        self.search.assert_not_called()

    def test_day_questions_keep_the_local_date_answer(self):
        for text in ("what day is it today?", "what day is today?"):
            with self.subTest(text=text):
                result = runtime.turn(text, {})
                self.assertNotEqual(result["module"], "web_search")
                self.assertRegex(result["reply"],
                                 r"Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday")
        self.search.assert_not_called()

    def test_known_historical_person_keeps_the_local_knowledge_answer(self):
        for text in ("Who is Albert Einstein?", "who is einstein"):
            with self.subTest(text=text):
                result = runtime.turn(text, {})
                self.assertEqual(result["module"], "answers")
                self.assertIn("Einstein", result["reply"])
                self.assertIn("relativity", result["reply"])
        self.search.assert_not_called()

    def test_previously_introduced_person_keeps_conversation_recall(self):
        memory = {}
        runtime.turn("My brother's name is Alex.", memory)
        result = runtime.turn("Who is Alex?", memory)

        self.assertEqual(result["module"], "memory_store")
        self.assertIn("Alex", result["reply"])
        self.assertIn("brother", result["reply"])
        self.search.assert_not_called()

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
            "who is my brother",
            "who am i",
            "who are you",
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
