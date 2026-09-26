from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from friday.interaction.gemini_live import GeminiLiveSession
from friday.interaction.session import SessionState


class FakeTool:
    def __init__(self, name: str, result: Any = "success"):
        self.name = name
        self.result = result

    def run(self, **kwargs):
        return {"tool": self.name, "result": self.result, "args": kwargs}


class FakeToolRegistry:
    def __init__(self):
        self.tools = {
            "system.get_time": FakeTool("system.get_time", "07:50 PM"),
            "applications.open": FakeTool("applications.open", "opened"),
            "simple_tool": FakeTool("simple_tool", "ok"),
        }

    def all_schemas(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "system.get_time",
                    "description": "Get current local time",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "applications.open",
                    "description": "Open an application",
                    "parameters": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                    },
                },
            },
        ]

    def get(self, name: str):
        return self.tools.get(name)


class TestGeminiLiveSession(unittest.TestCase):
    def setUp(self):
        self.registry = FakeToolRegistry()

    def test_session_init(self):
        session = GeminiLiveSession(
            api_key="fake-key-for-test",
            model="gemini-3.1-flash-live-preview",
            voice_name="Aoede",
            followup_timeout=10.0,
            tool_registry=self.registry,
        )
        self.assertEqual(session.model, "gemini-3.1-flash-live-preview")
        self.assertEqual(session.voice_name, "Aoede")
        self.assertEqual(session.followup_timeout, 10.0)
        self.assertEqual(session.state, SessionState.IDLE)

    def test_build_tools_declaration_sanitizes_names(self):
        session = GeminiLiveSession(
            api_key="fake-key-for-test",
            tool_registry=self.registry,
        )
        tools = session._build_tools_declaration()
        self.assertIsNotNone(tools)
        self.assertEqual(len(tools), 1)
        declarations = tools[0].function_declarations
        names = [d.name for d in declarations]
        # Dots must be replaced with underscores for Gemini
        self.assertIn("system_get_time", names)
        self.assertIn("applications_open", names)
        for name in names:
            self.assertNotIn(".", name)

    def test_execute_local_tool_dotted_resolution(self):
        session = GeminiLiveSession(
            api_key="fake-key-for-test",
            tool_registry=self.registry,
        )
        # Call with sanitized underscore name
        res = session._execute_local_tool("system_get_time", {})
        self.assertEqual(res["tool"], "system.get_time")
        self.assertEqual(res["result"], "07:50 PM")

        # Call with arguments
        res_app = session._execute_local_tool("applications_open", {"name": "notepad"})
        self.assertEqual(res_app["tool"], "applications.open")
        self.assertEqual(res_app["args"], {"name": "notepad"})

    def test_execute_unknown_tool(self):
        session = GeminiLiveSession(
            api_key="fake-key-for-test",
            tool_registry=self.registry,
        )
        res = session._execute_local_tool("nonexistent_tool", {})
        self.assertIn("error", res)

    def test_state_change_callback(self):
        states = []
        session = GeminiLiveSession(
            api_key="fake-key-for-test",
            on_state_change=states.append,
        )
        session.set_state(SessionState.LISTENING)
        session.set_state(SessionState.SPEAKING)
        self.assertEqual(states, [SessionState.LISTENING, SessionState.SPEAKING])

    def test_missing_api_key_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("friday.interaction.gemini_live.SecretsManager") as mock_secrets:
                mock_secrets.return_value.get.return_value = None
                with self.assertRaises(ValueError):
                    GeminiLiveSession(api_key=None)

    def test_session_with_speech_synthesizer(self):
        mock_synth = MagicMock()
        session = GeminiLiveSession(
            api_key="fake-key-for-test",
            speech_synthesizer=mock_synth,
        )
        self.assertEqual(session.speech_synthesizer, mock_synth)

    def test_operational_rules_include_mouse_and_app_guidance(self):
        session = GeminiLiveSession(
            api_key="fake-key-for-test",
        )
        self.assertIn("computer_mouse", session.system_prompt)
        self.assertIn("applications_open", session.system_prompt)

    def test_execute_shutdown_sets_shutdown_pending_not_stop_requested(self):
        mock_registry = MagicMock()
        mock_tool = MagicMock()
        mock_tool.run.return_value = {"status": "shutdown_initiated"}
        mock_registry.get.return_value = mock_tool

        session = GeminiLiveSession(
            api_key="fake-key-for-test",
            tool_registry=mock_registry,
        )
        self.assertFalse(session._shutdown_pending)
        self.assertFalse(session._stop_requested)

        res = session._execute_local_tool("system_shutdown_friday", {})
        self.assertTrue(session._shutdown_pending)
        # _stop_requested MUST remain False so farewell speech is not aborted!
        self.assertFalse(session._stop_requested)
        self.assertEqual(res, {"status": "shutdown_initiated"})


if __name__ == "__main__":
    unittest.main()


