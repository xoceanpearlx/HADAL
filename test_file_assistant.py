import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from file_assistant import (
    FileAssistant,
    LocalFileAIApp,
    UI_TEXT,
    build_tinyfish_query,
    format_research_report,
    run_tinyfish_research,
)


class FileAssistantTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.assistant = FileAssistant(self.root)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_lists_files_in_selected_folder(self):
        (self.root / "notes.txt").write_text("hello")
        (self.root / "docs").mkdir()

        result = self.assistant.list_files("")

        self.assertEqual(result["entries"], ["docs/", "notes.txt"])

    def test_rejects_paths_outside_selected_folder(self):
        with self.assertRaises(ValueError):
            self.assistant.list_files("..")

    def test_searches_names_recursively(self):
        nested = self.root / "docs"
        nested.mkdir()
        (nested / "Meeting-Notes.txt").write_text("hello")

        result = self.assistant.search_files("meeting")

        self.assertEqual(result["matches"], ["docs\\Meeting-Notes.txt"])

    def test_previews_and_applies_organization_after_confirmation(self):
        (self.root / "photo.jpg").write_text("image")
        (self.root / "README").write_text("readme")

        result = self.assistant.preview_organization()
        self.assertEqual(result["count"], 2)
        self.assertTrue((self.root / "photo.jpg").exists())

        with patch("builtins.input", return_value="yes"):
            applied = self.assistant.apply_organization()

        self.assertEqual(len(applied["moved"]), 2)
        self.assertTrue((self.root / "JPG" / "photo.jpg").is_file())
        self.assertTrue((self.root / "No extension" / "README").is_file())

    def test_cancellation_keeps_files_in_place(self):
        (self.root / "photo.jpg").write_text("image")
        self.assistant.preview_organization()

        with patch("builtins.input", return_value="no"):
            result = self.assistant.apply_organization()

        self.assertIn("Cancelled", result["status"])
        self.assertTrue((self.root / "photo.jpg").is_file())


class TinyFishResearchTests(unittest.TestCase):
    class FakeResponse:
        def __init__(self, events):
            self.lines = [
                f"data: {json.dumps(event)}\n".encode("utf-8")
                for event in events
            ]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def __iter__(self):
            return iter(self.lines)

    def test_sends_documented_headers_and_returns_cited_report(self):
        events = [
            {"event": "session", "session_id": "session-123"},
            {"event": "synthesis_delta", "delta": "Answer "},
            {"event": "synthesis_delta", "delta": "as it arrives."},
            {
                "event": "final_result",
                "result": "Answer with evidence.",
                "citations": [{"title": "Example", "url": "https://example.com"}],
            },
            {"event": "done"},
        ]
        captured = {}
        updates = []

        def opener(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return self.FakeResponse(events)

        result = run_tinyfish_research(
            "What is new?", "secret-test-key", language="hi", opener=opener,
            on_delta=updates.append,
        )

        self.assertEqual(captured["request"].get_header("X-api-key"), "secret-test-key")
        self.assertEqual(captured["request"].get_header("Content-type"), "application/json")
        self.assertEqual(captured["timeout"], 2700)
        payload = json.loads(captured["request"].data)
        self.assertEqual(payload["query"], build_tinyfish_query("What is new?"))
        self.assertEqual({key: value for key, value in payload.items() if key != "query"}, {
            "mode": "instant",
            "stream": True,
            "output_language": "hi",
        })
        self.assertEqual(result["result"], "Answer with evidence.")
        self.assertEqual(result["session_id"], "session-123")
        self.assertEqual(result["citations"][0]["url"], "https://example.com")
        self.assertEqual(updates, ["Answer ", "Answer as it arrives."])

    def test_research_answer_does_not_append_source_list(self):
        self.assertEqual(
            format_research_report("Short direct answer."),
            "Short direct answer.",
        )

    def test_requires_a_query_and_api_key(self):
        with self.assertRaises(ValueError):
            run_tinyfish_research(" ", "secret")
        with self.assertRaises(ValueError):
            run_tinyfish_research("Question", "")
        with self.assertRaises(ValueError):
            build_tinyfish_query("q" * 2000)

    def test_response_instructions_enforce_hadal_identity_and_concise_order(self):
        query = build_tinyfish_query("What is your name?")
        self.assertIn("answer HADAL, never Claude", query)
        self.assertIn("Start with a direct answer or short summary.", query)
        self.assertIn("at most 2 short sentences", query)
        self.assertTrue(query.endswith("Question: What is your name?"))
        self.assertLessEqual(len(query), 2000)

    def test_surfaces_research_stream_errors(self):
        response = self.FakeResponse([
            {"event": "error", "message": "Research is not enabled."},
        ])
        with self.assertRaisesRegex(RuntimeError, "Research is not enabled"):
            run_tinyfish_research(
                "Question",
                "secret-test-key",
                opener=lambda *_args, **_kwargs: response,
            )

    def test_rejects_empty_success_stream(self):
        response = self.FakeResponse([{"event": "done"}])
        with self.assertRaisesRegex(RuntimeError, "without returning"):
            run_tinyfish_research(
                "Question",
                "secret-test-key",
                opener=lambda *_args, **_kwargs: response,
            )


class LocalCommandRoutingTests(unittest.TestCase):
    def setUp(self):
        self.app = object.__new__(LocalFileAIApp)

    def test_quick_action_commands_use_local_tools(self):
        self.app._tool_list_files = lambda index, subfolder: {
            "root_index": index, "subfolder": subfolder
        }
        self.app._tool_search = lambda query: {"query": query}
        self.app._tool_preview = lambda index: {"root_index": index}

        self.assertEqual(
            self.app._run_local_command("List files in folder 2"),
            {"root_index": 2, "subfolder": ""},
        )
        self.assertEqual(
            self.app._run_local_command("Search filenames for report"),
            {"query": "report"},
        )
        self.assertEqual(
            self.app._run_local_command("Preview organization for folder 3"),
            {"root_index": 3},
        )

    def test_apply_requires_an_explicit_apply_command(self):
        calls = []
        self.app._run_tool_threadsafe = lambda name, args: calls.append((name, args))

        self.assertIsNone(self.app._run_local_command("Could you apply the plan?"))
        self.assertEqual(
            self.app._run_local_command("Apply the previewed organization"),
            None,
        )
        self.assertEqual(calls, [("apply_organization", {})])

    def test_regular_questions_are_left_for_tinyfish(self):
        self.assertIsNone(self.app._run_local_command("How does solar power work?"))
        self.assertTrue(LocalFileAIApp._is_local_command("List files in folder 1"))
        self.assertFalse(LocalFileAIApp._is_local_command("How does solar power work?"))

    def test_research_status_has_ocean_theme_in_both_languages(self):
        self.assertIn("Diving into the depths", UI_TEXT["research_status"]["en"])
        self.assertIn("गहराइयों", UI_TEXT["research_status"]["hi"])


if __name__ == "__main__":
    unittest.main()