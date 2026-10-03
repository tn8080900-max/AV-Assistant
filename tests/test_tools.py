import tempfile
import unittest
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from backend.agent.agent import Agent
from backend.agent.state import AgentState
from backend.permissions.manager import PermissionLevel, may_run_automatically
from backend.tools.browser import open_website
from backend.tools.calculator import calculate
from backend.tools.file_search import search_files, validate_deletion_target
from backend.tools.registry import build_tool_registry


class CalculatorTests(unittest.TestCase):
    def test_basic_arithmetic(self) -> None:
        self.assertEqual(calculate("(12 + 8) * 3 / 2"), "30.0")

    def test_rejects_code_and_oversized_exponents(self) -> None:
        with self.assertRaises(ValueError):
            calculate("__import__('os').system('whoami')")
        with self.assertRaises(ValueError):
            calculate("2 ** 101")


class FileToolTests(unittest.TestCase):
    def test_search_is_limited_to_configured_root_and_skips_sensitive_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "allowed"
            root.mkdir()
            (root / "meeting-notes.txt").write_text("filename only", encoding="utf-8")
            (root / "api-token-backup.txt").write_text("sensitive name", encoding="utf-8")
            hidden = root / ".private"
            hidden.mkdir()
            (hidden / "meeting-notes-hidden.txt").write_text("hidden", encoding="utf-8")
            outside = Path(temporary) / "outside-meeting-notes.txt"
            outside.write_text("outside", encoding="utf-8")

            results = search_files("meeting-notes", [str(root)])
            self.assertEqual(results, [str(root / "meeting-notes.txt")])

    def test_deletion_requires_existing_file_inside_configured_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "allowed"
            root.mkdir()
            target = root / "ordinary.txt"
            target.write_text("safe example", encoding="utf-8")
            self.assertEqual(
                validate_deletion_target(str(target), [str(root)]),
                target.resolve(),
            )
            with self.assertRaises(ValueError):
                validate_deletion_target(str(Path(temporary) / "outside.txt"), [str(root)])
            with self.assertRaises(ValueError):
                validate_deletion_target(str(root / ".env"), [str(root)])

    def test_delete_tool_validates_path_before_asking_for_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "allowed"
            root.mkdir()
            target = root / "ordinary.txt"
            target.write_text("safe example", encoding="utf-8")
            settings = SimpleNamespace(
                allowed_directories=[str(root)],
                allowed_applications=[],
            )
            tool = build_tool_registry(settings)["delete_file"]

            self.assertEqual(
                tool.validate_arguments({"path": str(target)})["path"],
                str(target.resolve()),
            )
            with self.assertRaises(ValueError):
                tool.validate_arguments(
                    {"path": str(Path(temporary) / "outside.txt")}
                )


class PermissionTests(unittest.TestCase):
    def test_only_safe_tools_run_without_approval(self) -> None:
        self.assertTrue(may_run_automatically(PermissionLevel.SAFE))
        self.assertFalse(
            may_run_automatically(PermissionLevel.REQUIRES_CONFIRMATION)
        )

    def test_denied_delete_is_not_retried_in_the_session(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "ordinary.txt"
            target.write_text("must stay", encoding="utf-8")
            settings = SimpleNamespace(
                allowed_directories=[str(root)],
                allowed_applications=[],
            )

            class FakeCompletions:
                calls = 0

                def create(self, **_: object) -> object:
                    self.calls += 1
                    if self.calls <= 2:
                        message = SimpleNamespace(
                            content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    id=f"call-{self.calls}",
                                    function=SimpleNamespace(
                                        name="delete_file",
                                        arguments=json.dumps({"path": str(target)}),
                                    ),
                                )
                            ],
                        )
                    else:
                        message = SimpleNamespace(
                            content="I will leave the file untouched.",
                            tool_calls=None,
                        )
                    return SimpleNamespace(
                        choices=[SimpleNamespace(message=message)]
                    )

            completions = FakeCompletions()
            fake_client = SimpleNamespace(
                chat=SimpleNamespace(completions=completions)
            )
            with patch.object(
                Agent,
                "client",
                new_callable=PropertyMock,
                return_value=fake_client,
            ):
                agent = Agent(settings)
                pending = agent.run("Delete this file")
                self.assertEqual(pending["state"], AgentState.WAITING_FOR_PERMISSION)
                reply = agent.resolve_approval(
                    pending["pending_approval"]["request_id"], False
                )

            self.assertTrue(target.exists())
            self.assertEqual(completions.calls, 3)
            self.assertEqual(reply["answer"], "I will leave the file untouched.")


class BrowserToolTests(unittest.TestCase):
    def test_rejects_non_web_schemes(self) -> None:
        with self.assertRaises(ValueError):
            open_website("file:///C:/Users/Example/.env")


if __name__ == "__main__":
    unittest.main()