"""CLI search configuration tests; the runtime is mocked, so no network is used."""
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


if __name__ == "__main__":
    unittest.main()
