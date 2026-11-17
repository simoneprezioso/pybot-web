"""CLI search configuration tests; the runtime is mocked, so no network is used."""
import argparse
import contextlib
import io
import os
import unittest
from unittest import mock

import pybot


class WebSearchOptions(unittest.TestCase):
    def invoke(self, flags, initial=None, *, fail=False):
        seen = []

        def load():
            seen.append(os.environ.get("PYBOT_WEB_SEARCH"))
            if fail:
                raise RuntimeError("loading failed")
            return object()

        with mock.patch.dict(os.environ, {}, clear=True):
            if initial is not None:
                os.environ["PYBOT_WEB_SEARCH"] = initial
            with mock.patch.object(pybot, "load_bot", side_effect=load), \
                    mock.patch.object(pybot, "one_shot") as one_shot:
                if fail:
                    with self.assertRaisesRegex(RuntimeError, "loading failed"):
                        pybot.main(flags + ["-p", "question"])
                else:
                    self.assertEqual(pybot.main(flags + ["-p", "question"]), 0)
                    one_shot.assert_called_once()
                self.assertEqual(os.environ.get("PYBOT_WEB_SEARCH"), initial)
        return seen

    def test_default_preserves_disabled_and_enabled_environment_settings(self):
        for initial in (None, "0", "1"):
            with self.subTest(initial=initial):
                self.assertEqual(self.invoke([], initial), [initial])

    def test_enable_overrides_the_environment_for_this_invocation(self):
        for initial in (None, "0", "1"):
            with self.subTest(initial=initial):
                self.assertEqual(self.invoke(["--web-search"], initial), ["1"])

    def test_disable_overrides_an_enabled_environment(self):
        for initial in (None, "1"):
            with self.subTest(initial=initial):
                self.assertEqual(self.invoke(["--no-web-search"], initial), ["0"])

    def test_environment_is_restored_if_loading_fails(self):
        self.assertEqual(self.invoke(["--web-search"], fail=True), ["1"])
        self.assertEqual(self.invoke(["--no-web-search"], "1", fail=True), ["0"])

    def test_conflicting_flags_fail_before_loading_the_bot(self):
        with mock.patch.object(pybot, "load_bot") as load, \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exited:
            pybot.main(["--web-search", "--no-web-search"])
        self.assertEqual(exited.exception.code, 2)
        load.assert_not_called()

    def test_help_documents_both_flags_without_loading_the_bot(self):
        out = io.StringIO()
        with mock.patch.object(pybot, "load_bot") as load, \
                contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as exited:
            pybot.main(["--help"])
        self.assertEqual(exited.exception.code, 0)
        self.assertIn("--web-search", out.getvalue())
        self.assertIn("--no-web-search", out.getvalue())
        load.assert_not_called()

    def test_piped_mode_keeps_the_setting_during_every_response(self):
        seen = []

        def turn(text, memory):
            seen.append((text, os.environ.get("PYBOT_WEB_SEARCH")))
            return {"reply": "result", "module": "web_search"}

        runtime = mock.Mock(turn=turn)
        output = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(pybot, "load_bot", return_value=runtime), \
                mock.patch("sys.stdin", io.StringIO("first\nsecond\n")), \
                contextlib.redirect_stdout(output):
            self.assertEqual(pybot.main(["--web-search"]), 0)
            self.assertNotIn("PYBOT_WEB_SEARCH", os.environ)
        self.assertEqual(seen, [("first", "1"), ("second", "1")])
        self.assertEqual(output.getvalue().splitlines(), ["result", "result"])


class WebSearchStartup(unittest.TestCase):
    def opening(self, value=None, available=True):
        output = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True):
            if value is not None:
                os.environ["PYBOT_WEB_SEARCH"] = value
            with mock.patch("importlib.util.find_spec", return_value=object() if available else None), \
                    mock.patch("bot.search._load_ddgs", side_effect=AssertionError("must not import ddgs")), \
                    contextlib.redirect_stdout(output):
                pybot.opening()
        return output.getvalue()

    def test_offline_startup_explains_how_to_enable_search(self):
        text = self.opening()
        self.assertIn("Web search is off. Start with --web-search to enable it.", text)
        self.assertTrue(text.startswith(pybot.LOGO + "\n\n" + pybot.TAGLINE))
        self.assertLess(text.index(pybot.HINT), text.index("Web search is off"))

    def test_enabled_startup_names_duckduckgo_without_importing_the_client(self):
        text = self.opening("1")
        self.assertIn("Web search is enabled (DuckDuckGo).", text)
        self.assertIn('search the web for ...', text)

    def test_enabled_startup_with_missing_dependency_explains_installation(self):
        text = self.opening("1", available=False)
        self.assertIn("ddgs is not installed", text)
        self.assertIn('python -m pip install ".[web]"', text)

    def test_interactive_flag_is_applied_before_startup_status_is_printed(self):
        output = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(pybot, "load_bot", return_value=object()), \
                mock.patch("sys.stdin.isatty", return_value=True), \
                mock.patch("importlib.util.find_spec", return_value=object()), \
                mock.patch("builtins.input", side_effect=["/exit"]), \
                contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(output):
            self.assertEqual(pybot.main(["--web-search"]), 0)
            self.assertNotIn("PYBOT_WEB_SEARCH", os.environ)
        self.assertIn("Web search is enabled (DuckDuckGo).", output.getvalue())

    def test_terminal_reset_shows_the_current_search_status_again(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        output = Terminal()
        args = argparse.Namespace(prompt=None, seed=None, verbose=False)
        with mock.patch.dict(os.environ, {"PYBOT_WEB_SEARCH": "1"}, clear=True), \
                mock.patch("importlib.util.find_spec", return_value=object()), \
                mock.patch("builtins.input", side_effect=["/reset", "/exit"]), \
                mock.patch.object(pybot, "clear_screen") as clear_screen, \
                contextlib.redirect_stdout(output):
            pybot.chat(object(), args)
        clear_screen.assert_called_once()
        self.assertEqual(output.getvalue().count("Web search is enabled (DuckDuckGo)."), 2)

    def test_one_shot_reply_has_no_startup_status(self):
        runtime = mock.Mock()
        runtime.turn.return_value = {"reply": "result", "module": "web_search"}
        output = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(pybot, "load_bot", return_value=runtime), \
                mock.patch.object(pybot, "opening") as opening, \
                contextlib.redirect_stdout(output):
            self.assertEqual(pybot.main(["--web-search", "-p", "current news"]), 0)
        opening.assert_not_called()
        self.assertEqual(output.getvalue(), "result\n")


if __name__ == "__main__":
    unittest.main()
