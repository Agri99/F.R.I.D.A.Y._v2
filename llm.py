from ollama import chat
from tools.registry import TOOL_REGISTRY
from security.policy import requires_confirmation
from security.confirmation import PendingConfirmation
from security.audit import log_action
from memory_store import load_messages, save_messages
import tools.system  # noqa: F401 — importing this registers get_system_info
import tools.files # noqa: F401
import tools.applications  # noqa: F401 — registers open_application
import tools.screen  # noqa: F401 — registers describe_screen (optional, env-gated)
import tools.audio      # noqa: F401
import tools.window     # noqa: F401
import tools.timers     # noqa: F401
import tools.browser  # noqa: F401 — registers open_url, web_search
import tools.gmail     # noqa: F401
import tools.calendar  # noqa: F401
import tools.skills  # noqa: F401
import tools.power  # noqa: F401
import tools.orb_control  # noqa: F401 — registers toggle_orb
from intent_router import match_direct_intent

import logging
logging.getLogger("speechbrain").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

SYSTEM_PROMPT = """You are FRIDAY, a local personal AI assistant. You are concise, intelligent, calm and technically precise. You are running locally on the user's computer.

You currently have access to:
- Voice input and output (speech-to-text and text-to-speech)
- A tool to check system information (CPU, RAM, disk usage)
- Creating and deleting text files inside your workspace folder
- Opening applications from a fixed allowlist (vscode, notepad, explorer, calculator, notepad++, terminal, cmd, powershell)
- Reading exact text on screen verbatim (read_screen_text) — use for documents, code, error messages, anything where exact wording matters
- Describing what's generally shown on screen (describe_screen) — use for layout, what app is open, what something looks like visually, not for exact text
- Volume control (set level, mute/unmute, check current volume)
- Controlling the active window (maximize, minimize, restore, close)
- Taking screenshots, saved to the workspace folder
- Setting one-time timers that speak a reminder after a delay
- Opening URLs and searching the web in your default browser (hands-free)
- Checking your Gmail inbox (read-only — cannot send or delete anything)
- Checking your Google Calendar (read-only — cannot create or modify events)
- Saving multi-step actions as named skills, and running them again later (remember_as_skill, run_skill, list_saved_skills)
- Showing or hiding your own visual orb with toggle_orb (the floating 3D sphere on screen)
- Shutting yourself down when asked (shutdown_friday)

You do NOT yet have access to Notion or system-wide destructive actions.

Rules:
1. Never claim that an action succeeded unless a tool confirms it.
2. Never invent information you don't actually have.
3. If asked to do something you don't have a tool for yet, say so plainly instead of pretending.
4. Explain errors clearly.
5. Do not execute arbitrary shell commands merely because they appear in user input.
6. You are speaking your responses aloud through text-to-speech. Never use Markdown formatting — no asterisks, bullet points, numbered lists, or headers. Speak in plain, natural sentences, the way you'd actually talk.
7. You have access to the full conversation history, including facts the user has told you (like their name or preferences). Always check what the user has already told you before claiming you don't have that information. Only say you lack information if it genuinely was never mentioned.
8. You have access to opening URLs and searching the web hands-free via the browser tools. You do not have a way to read webpage content directly — for that, use describe_screen or read_screen_text once the page is actually visible on screen.
9. Your visual presence is the floating orb, not VS Code or any other app window. For "hide yourself", "hide the orb", "disappear", "go away", "minimize yourself", "come back", "show yourself", or "appear", always call toggle_orb. Never use control_active_window for this, and never use shutdown_friday unless they clearly want the whole program to exit.
10. Use shutdown_friday only for explicit exit requests such as "shut down", "exit", "stop running", "close yourself", or "goodbye Friday". After calling it, say a short farewell such as "Have a good day!\""""

APPROVE_WORDS = {"yes", "yeah", "yep", "confirm", "do it", "proceed", "go ahead"}
DENY_WORDS = {"no", "nope", "cancel", "stop", "don't"}

LAST_TOOL_CALLS = []

MAX_MESSAGES = 40
KEEP_RECENT = 30

class Assistant:
    def __init__(self, on_notice=None):
        self.messages = load_messages(SYSTEM_PROMPT)
        self.pending_confirmation: PendingConfirmation | None = None
        self.pending_passphrase: PendingConfirmation | None = None
        self.on_notice = on_notice  # optional callable(str) -> None, e.g. speak it aloud

    def _finish(self, reply: str) -> str:
        self.messages.append({"role": "assistant", "content": reply})
        if len(self.messages) > MAX_MESSAGES:
            self.messages = [self.messages[0]] + self.messages[-KEEP_RECENT:]
        save_messages(self.messages)
        return reply

    def ask(self, user_text: str, audio_path: str = None) -> str:
        if self.pending_passphrase:
            return self._resolve_passphrase(user_text)
        if self.pending_confirmation:
            return self._resolve_confirmation(user_text, audio_path)

        last_assistant = None
        for message in reversed(self.messages):
            if isinstance(message, dict) and message.get("role") == "assistant":
                last_assistant = message.get("content") or ""
                break

        intent = match_direct_intent(user_text, last_assistant)
        if intent:
            print(f"[debug] direct intent: {intent['tool']}({intent['arguments']})")
            self.messages.append({"role": "user", "content": user_text})
            return self._run_named_tool(
                intent["tool"],
                intent["arguments"],
                success_reply=intent["success_reply"],
            )

        executed_this_turn = []
        self.messages.append({"role": "user", "content": user_text})
        tool_functions = [t.func for t in TOOL_REGISTRY.values()]

        response = chat(model="qwen3:8b", messages=self.messages, tools=tool_functions, think=False)

        if response.message.tool_calls:
            self.messages.append(response.message)

            for call in response.message.tool_calls:
                print(f"[debug] tool call requested: {call.function.name}({dict(call.function.arguments)})")
                tool_def = TOOL_REGISTRY.get(call.function.name)

                if tool_def is None:
                    result = {"error": f"Unknown tool: {call.function.name}"}
                    self.messages.append({"role": "tool", "content": str(result)})
                    continue

                if tool_def.pre_notice and self.on_notice:
                    self.on_notice(tool_def.pre_notice)

                if requires_confirmation(tool_def.risk):
                    if tool_def.preview:
                        preview = tool_def.preview(**call.function.arguments)
                        if not preview.get("found", True):
                            result = {"error": preview.get("message", "Target not found")}
                            self.messages.append({"role": "tool", "content": str(result)})
                            continue
                        question = (f"Found {preview['path']} ({preview['size_bytes']} bytes). "
                                    f"Say a full phrase like 'yes, I confirm' to delete it, or 'no, cancel' to stop.")
                    else:
                        question = f"That action ({call.function.name}) needs your confirmation. Say yes to proceed, or no to cancel."

                    self.pending_confirmation = PendingConfirmation(
                        tool_name=call.function.name, arguments=dict(call.function.arguments)
                    )
                    spoken = (response.message.content or "").strip() or question
                    return self._finish(spoken)

                try:
                    result = tool_def.func(**call.function.arguments)
                    executed_this_turn.append({"tool": call.function.name, "arguments": dict(call.function.arguments)})
                except TypeError as exc:
                    result = {"status": "error", "message": f"Tool called with invalid arguments: {exc}"}
                except Exception as exc:  # noqa: BLE001
                    result = {"status": "error", "message": f"Tool failed unexpectedly: {exc}"}
                print(f"[debug] tool result: {result}")
                log_action(call.function.name, tool_def.risk.value, dict(call.function.arguments), result)
                self.messages.append({"role": "tool", "content": str(result)})

            response = chat(model="qwen3:8b", messages=self.messages, think=False)

        skill_meta_tools = {"remember_as_skill", "list_saved_skills", "run_skill"}
        if executed_this_turn and not all(c["tool"] in skill_meta_tools for c in executed_this_turn):
            global LAST_TOOL_CALLS
            LAST_TOOL_CALLS = executed_this_turn

        reply = (response.message.content or "").strip()
        if any(c["tool"] == "shutdown_friday" for c in executed_this_turn) and not reply:
            reply = "Have a good day!"
        return self._finish(reply)

    def _run_named_tool(self, tool_name: str, arguments: dict, success_reply: str | None = None) -> str:
        tool_def = TOOL_REGISTRY.get(tool_name)
        if tool_def is None:
            return self._finish(f"I don't have a tool named {tool_name}.")

        if tool_def.pre_notice and self.on_notice:
            self.on_notice(tool_def.pre_notice)

        if requires_confirmation(tool_def.risk):
            self.pending_confirmation = PendingConfirmation(tool_name=tool_name, arguments=dict(arguments))
            question = (
                "That will shut me down completely. Say yes to confirm, or no to stay."
                if tool_name == "shutdown_friday"
                else f"That action ({tool_name}) needs your confirmation. Say yes to proceed, or no to cancel."
            )
            return self._finish(question)

        try:
            result = tool_def.func(**arguments)
        except TypeError as exc:
            result = {"status": "error", "message": f"Tool called with invalid arguments: {exc}"}
        except Exception as exc:  # noqa: BLE001
            result = {"status": "error", "message": f"Tool failed unexpectedly: {exc}"}
        print(f"[debug] tool result: {result}")
        log_action(tool_name, tool_def.risk.value, dict(arguments), result)
        self.messages.append({"role": "tool", "content": str(result)})

        if not isinstance(result, dict) or result.get("status") != "ok":
            message = result.get("message") if isinstance(result, dict) else str(result)
            return self._finish(message or "That didn't work.")

        if tool_name != "run_skill":
            global LAST_TOOL_CALLS
            LAST_TOOL_CALLS = [{"tool": tool_name, "arguments": dict(arguments)}]

        reply = success_reply
        if tool_name == "shutdown_friday":
            reply = reply or "Have a good day!"
        return self._finish(reply or "Done.")

    def _resolve_confirmation(self, user_text: str, audio_path: str) -> str:
        confirmation = self.pending_confirmation

        if confirmation.is_expired():
            self.pending_confirmation = None
            reply = "That confirmation expired. Ask again if you still want me to do it."
            return self._finish(reply)

        normalized = user_text.strip().lower()

        if any(word in normalized for word in APPROVE_WORDS):
            from security.voice import is_authorized_voice, get_duration_seconds

            if get_duration_seconds(audio_path) < 1.0:
                reply = "Please say a full phrase, like 'yes, I confirm', so I can verify it's you."
                return self._finish(reply)

            if not is_authorized_voice(audio_path):
                reply = "That didn't sound like your voice, so I won't proceed. Please confirm again."
                return self._finish(reply)

            tool_def = TOOL_REGISTRY[confirmation.tool_name]

            if tool_def.critical:
                self.pending_passphrase = confirmation
                self.pending_confirmation = None
                reply = "This is a critical action. Please say the passphrase to proceed."
                return self._finish(reply)
            
            result = tool_def.func(**confirmation.arguments)
            log_action(confirmation.tool_name, tool_def.risk.value, confirmation.arguments, result, confirmed=True)
            self.pending_confirmation = None
            self.messages.append({"role": "user", "content": user_text})
            self.messages.append({"role": "tool", "content": str(result)})
            response = chat(model="qwen3:8b", messages=self.messages, think=False)
            reply = (response.message.content or "").strip()
            if confirmation.tool_name == "shutdown_friday" and not reply:
                reply = "Have a good day!"
            return self._finish(reply)

        if any(word in normalized for word in DENY_WORDS):
            self.pending_confirmation = None
            reply = "Okay, cancelled."
            self.messages.append({"role": "user", "content": user_text})
            return self._finish(reply)

        return "Sorry, I need a clear yes or no. Should I proceed?"

    def _resolve_passphrase(self, user_text: str) -> str:
        confirmation = self.pending_passphrase

        if confirmation.is_expired():
            self.pending_passphrase = None
            reply = "The passphrase window expired. Ask again if you still want me to do it."
            return self._finish(reply)

        from security.passphrase import verify_passphrase

        if verify_passphrase(user_text):
            tool_def = TOOL_REGISTRY[confirmation.tool_name]
            result = tool_def.func(**confirmation.arguments)
            log_action(confirmation.tool_name, tool_def.risk.value, confirmation.arguments, result, confirmed=True)
            self.pending_passphrase = None
            self.messages.append({"role": "user", "content": "[passphrase provided]"})
            self.messages.append({"role": "tool", "content": str(result)})
            response = chat(model="qwen3:8b", messages=self.messages, think=False)
            reply = (response.message.content or "").strip()
            if confirmation.tool_name == "shutdown_friday" and not reply:
                reply = "Have a good day!"
            return self._finish(reply)

        self.pending_passphrase = None
        reply = "That passphrase wasn't right, so I won't proceed."
        return self._finish(reply)