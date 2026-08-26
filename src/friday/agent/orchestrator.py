"""
src/friday/agent/orchestrator.py

WHAT THIS IS FOR:
The central assembly-line coordinator for F.R.I.D.A.Y. v2 (blueprint §3, §11).
Coordinates intent parsing, planning, policy evaluation, isolated tool execution,
independent state verification, failure recovery, two-stage voice/passphrase confirmation,
and SQLite conversation memory.
"""

from __future__ import annotations

from typing import Any, Callable

from friday.config import Settings
from friday.models.router import ModelRouter
from friday.models.base import ModelMessage
from friday.security.policy import PolicyEngine, PolicyDecision
from friday.security.capabilities import CapabilityRegistry
from friday.security.confirmation import ConfirmationManager
from friday.security.audit import AuditLogger
from friday.security.voice_auth import VoiceAuthProvider
from friday.security.passphrase import verify_passphrase
from friday.memory.conversation import ConversationMemory
from friday.learning.trajectory import TrajectoryRecorder

from .task import Task, TaskManager, TaskStatus, Step
from .state import TaskStateMachine
from .planner import Planner, PlanningDepth
from .executor import Executor
from .evaluator import Evaluator
from .recovery import RecoveryManager
from .fastpath import FastPathRouter

APPROVE_WORDS = {"yes", "yeah", "yep", "confirm", "do it", "proceed", "go ahead", "sure", "ok", "okay"}
DENY_WORDS = {"no", "nope", "cancel", "stop", "don't", "abort"}


def _format_confirmation_prompt(action: str, args: dict[str, Any]) -> str:
    """Produce a natural spoken confirmation prompt without robotic phrasing."""
    if action == "applications.open":
        app_name = args.get("app_id", "the application")
        return f"Do you want me to open {app_name}?"
    if action == "applications.close":
        app_name = args.get("app_id", "the application")
        return f"Do you want me to close {app_name}?"
    if action == "filesystem.delete":
        filename = args.get("path", args.get("filename", "this file"))
        return f"Do you want me to delete {filename}?"
    if action == "filesystem.write":
        filename = args.get("path", args.get("filename", "this file"))
        return f"Do you want me to write to {filename}?"
    if action == "gmail.send":
        recipient = args.get("to", "this contact")
        return f"Do you want me to send an email to {recipient}?"
    if action == "calendar.create":
        title = args.get("title", "this event")
        return f"Do you want me to add {title} to your calendar?"
    if action == "calendar.delete":
        return "Do you want me to delete this calendar event?"
    if action == "system.lock":
        return "Do you want me to lock your computer?"
    if action in ("shutdown_friday", "system.shutdown_friday"):
        return "Do you want me to go off?"

    if action == "computer.click":
        target = args.get("text_label") or f"coordinates ({args.get('x')}, {args.get('y')})"
        return f"Do you want me to click on {target}?"

    clean_name = action.replace(".", " ").replace("_", " ")
    return f"Do you want me to {clean_name}?"


def _format_natural_reply(action: str, result: Any) -> str:
    """Format structured tool results into natural spoken English."""
    if isinstance(result, dict):
        status = result.get("status")
        if status == "error":
            msg = result.get("message", "An error occurred.")
            return f"I couldn't complete that: {msg}"

        if action == "gmail.search":
            msgs = result.get("messages", [])
            if not msgs:
                return "Your inbox is clear. You have no new messages."
            count = len(msgs)
            summaries = []
            for m in msgs[:3]:
                sender = m.get("from", "Unknown").split("<")[0].strip().replace('"', '')
                subj = m.get("subject", "(no subject)")
                summaries.append(f"{sender}: {subj}")
            return f"You have {count} recent email{'s' if count > 1 else ''}. " + "; ".join(summaries)

        if action == "gmail.read":
            sender = result.get("from", "Unknown").split("<")[0].strip().replace('"', '')
            subj = result.get("subject", "")
            body = result.get("body", "")[:200]
            return f"Email from {sender} about {subj}: {body}"

        if action == "calendar.list":
            events = result.get("events", [])
            if not events:
                return "You have no upcoming events on your calendar."
            count = len(events)
            lines = [f"{e.get('summary', 'Event')} at {e.get('start', '')}" for e in events[:3]]
            return f"You have {count} upcoming event{'s' if count > 1 else ''}: " + ", ".join(lines)

        if action == "applications.open":
            app_id = result.get("app_id", "the application")
            return f"I've opened {app_id} for you."

        if action == "applications.close":
            app_id = result.get("app_id", "the application")
            return f"I've closed {app_id}."

        if action == "system.get_time":
            t = result.get("time", "")
            return f"The current time is {t}."

        if action == "system.get_status":
            cpu = result.get("cpu_percent", "")
            ram = result.get("ram_percent", "")
            return f"System status: CPU is at {cpu}%, RAM usage is at {ram}%."

        if "message" in result:
            return str(result["message"])

    return str(result)


class AgentOrchestrator:

    """
    The central coordinator that manages the lifecycle of a task.
    Implements a multi-step tool execution loop, utilizing Planner, Executor, Evaluator, and RecoveryManager.
    """

    def __init__(
        self,
        settings: Settings,
        model_router: ModelRouter,
        policy_engine: PolicyEngine,
        tool_registry: Any,
        task_manager: TaskManager | None = None,
        capability_registry: CapabilityRegistry | None = None,
        memory_manager: Any | None = None,
        audit_logger: AuditLogger | None = None,
        system_prompt: str | None = None,
    ):
        self.settings = settings
        self.models = model_router
        self.model_router = model_router
        self.policy = policy_engine
        self.policy_engine = policy_engine
        self.tools = tool_registry
        self.tool_registry = tool_registry
        self.tasks = task_manager or TaskManager()
        self.capabilities = capability_registry or CapabilityRegistry()
        self.memory = memory_manager
        self.audit_logger = audit_logger or AuditLogger(settings.paths.audit_dir)
        self.system_prompt = system_prompt or "You are FRIDAY, a local AI assistant."

        self.conversation_memory = ConversationMemory(
            db_path=f"{settings.paths.data_dir}/friday.db",
            context_limit=settings.runtime.context_window_messages,
        )
        self.trajectory_recorder = TrajectoryRecorder(trajectories_dir=settings.paths.trajectories_dir)
        self.confirmation_mgr = ConfirmationManager(ttl_seconds=settings.security.confirmation_ttl_seconds)
        self.voice_auth = VoiceAuthProvider()

        self.planner = Planner()
        self.executor = Executor()
        self.evaluator = Evaluator()
        self.recovery = RecoveryManager()
        self.fastpath = FastPathRouter()
        self.state_machine = TaskStateMachine(on_transition=self._on_task_transition)

    def _on_task_transition(self, task: Task, new_status: TaskStatus, reason: str) -> None:
        pass

    def _remember(self, role: str, content: str) -> None:
        try:
            self.conversation_memory.append(role, content)
        except Exception:
            pass

    def run(self, goal: str, on_transition: Callable[[TaskStatus], None] | None = None) -> Task:
        """Starts processing a user goal."""
        task = self.tasks.create(goal)
        self._remember("user", goal)
        self.trajectory_recorder.start(task.id, goal)

        if on_transition:
            original_on_transition = self.state_machine.on_transition

            def combined_transition(t: Task, status: TaskStatus, reason: str):
                if original_on_transition:
                    original_on_transition(t, status, reason)
                if t.id == task.id:
                    on_transition(status)

            self.state_machine.on_transition = combined_transition

        self.state_machine.transition(task, TaskStatus.PLANNING, reason="Received goal")

        # Check fast path
        fast_intent = self.fastpath.match(goal)
        if fast_intent:
            task.plan = [Step(action=fast_intent.tool_name, args=fast_intent.arguments, expected_outcome=fast_intent.success_reply or "")]
            return self._execute_plan(task)

        # Standard planning with model
        schemas = self.tools.all_schemas() if hasattr(self.tools, "all_schemas") else []
        task.plan = self.planner.create_plan(
            goal=goal,
            available_tools=schemas,
            memories=[],
            model_router=self.models,
        )

        return self._execute_plan(task)

    def _execute_plan(self, task: Task) -> Task:
        """Executes the steps in the task's plan."""
        if task.current_step_index < 0:
            task.current_step_index = 0

        while task.current_step_index < len(task.plan):
            step = task.plan[task.current_step_index]

            if step.action == "direct_answer":
                reply = step.args.get("text", step.expected_outcome or "")
                task.last_message = reply
                self.state_machine.transition(task, TaskStatus.EXECUTING, reason="Direct answer")
                self.state_machine.transition(task, TaskStatus.VERIFYING, reason="No verification needed for text")
                self.state_machine.transition(task, TaskStatus.COMPLETED, reason=reply)
                self._remember("assistant", reply)
                self.trajectory_recorder.finish("SUCCESS")
                return task

            if step.action == "error":
                err_msg = step.args.get("message", "Planning error")
                self.state_machine.transition(task, TaskStatus.FAILED, reason=err_msg)
                self._remember("assistant", f"I encountered an error: {err_msg}")
                self.trajectory_recorder.finish("FAILURE")
                return task

            # Policy Engine Check (unless already authorized)
            tier = self.tools.tier_of(step.action) if hasattr(self.tools, "tier_of") else None
            if not getattr(step, "authorized", False):
                decision = self.policy.evaluate(step.action, tier)
                dec_val = decision.decision.value if hasattr(decision.decision, "value") else str(decision.decision)

                if dec_val == "DENY":
                    self.state_machine.transition(task, TaskStatus.BLOCKED, reason=getattr(decision, "reason", "Policy denial"))
                    self._remember("assistant", f"I can't do that: {getattr(decision, 'reason', 'Blocked by policy')}")
                    self.trajectory_recorder.finish("BLOCKED")
                    return task

                if dec_val in ("REQUIRE_CONFIRMATION", "REQUIRE_SECOND_FACTOR"):
                    prompt = _format_confirmation_prompt(step.action, step.args)
                    task.last_message = prompt
                    task.pending_auth = {
                        "step": step,
                        "stage": "voice" if dec_val == "REQUIRE_CONFIRMATION" else "second_factor",
                        "action": step.action,
                        "args": step.args,
                    }
                    if task.status != TaskStatus.AWAITING_AUTHORIZATION:
                        self.state_machine.transition(task, TaskStatus.AWAITING_AUTHORIZATION, reason=prompt)
                    self._remember("assistant", prompt)
                    return task

            # ALLOW / AUTHORIZED path: execute tool
            self.state_machine.transition(task, TaskStatus.EXECUTING, reason=f"Running {step.action}")
            tool = self.tools.get(step.action) if hasattr(self.tools, "get") else None

            if not tool:
                self.state_machine.transition(task, TaskStatus.FAILED, reason=f"Tool not found: {step.action}")
                self._remember("assistant", f"Tool '{step.action}' is not available.")
                self.trajectory_recorder.finish("FAILURE")
                return task

            exec_result = self.executor.execute(tool, step.args)
            self.state_machine.transition(task, TaskStatus.VERIFYING, reason="Evaluating execution")
            eval_result = self.evaluator.evaluate(task, step, exec_result, tool)

            self.audit_logger.log_tool_execution(
                task_id=task.id,
                tool_name=step.action,
                risk_tier=tier or "GREEN",
                arguments=step.args,
                authorization="ALLOWED",
                result=exec_result.result if exec_result.success else str(exec_result.error),
                verification=eval_result.message,
            )

            self.trajectory_recorder.record_step(
                action=step.action,
                observation=str(exec_result.result),
                result="SUCCESS" if eval_result.success else "FAILURE",
            )

            if not eval_result.success:
                if eval_result.needs_recovery:
                    self.state_machine.transition(task, TaskStatus.RECOVERING, reason=eval_result.message)
                    strategy = self.recovery.classify_failure(exec_result.error or "", {})
                    recovered = self.recovery.attempt_recovery(task, strategy)
                    if recovered:
                        continue
                self.state_machine.transition(task, TaskStatus.FAILED, reason=eval_result.message)
                self._remember("assistant", f"That failed: {eval_result.message}")
                self.trajectory_recorder.finish("FAILURE")
                return task

            task.current_step_index += 1

        self.state_machine.transition(task, TaskStatus.COMPLETED, reason="All steps completed")
        reply = _format_natural_reply(step.action, exec_result.result) if 'exec_result' in locals() and exec_result.success else "Done."
        task.last_message = reply
        self._remember("assistant", reply)
        self.trajectory_recorder.finish("SUCCESS")
        return task


    def resume_with_voice(self, task_id: str, user_text: str, audio_path: str | None = None) -> Task | None:
        """Resumes a task parked in AWAITING_AUTHORIZATION with voice or passphrase input."""
        task = self.tasks.get(task_id) if hasattr(self.tasks, "get") else None
        if not task or task.status != TaskStatus.AWAITING_AUTHORIZATION:
            return task

        self._remember("user", user_text)
        normalized = user_text.strip().lower()

        if any(word in normalized for word in DENY_WORDS):
            task.pending_auth = None
            self.state_machine.transition(task, TaskStatus.BLOCKED, reason="User cancelled action")
            task.last_message = "Okay, cancelled."
            self._remember("assistant", task.last_message)
            return task

        auth_data = task.pending_auth or {}
        stage = auth_data.get("stage", "voice")

        if stage == "voice":
            if not any(word in normalized for word in APPROVE_WORDS):
                task.last_message = "I need a clear yes or no. Should I proceed?"
                self._remember("assistant", task.last_message)
                return task

            # Check if second factor passphrase required for RED tools
            tool_name = auth_data.get("action", "")
            tool = self.tools.get(tool_name) if hasattr(self.tools, "get") else None
            tier = self.tools.tier_of(tool_name) if hasattr(self.tools, "tier_of") else None

            if (tool and getattr(tool, "critical", False)) or tier == "RED":
                auth_data["stage"] = "passphrase"
                task.last_message = "This is a critical action. Please speak the passphrase to proceed."
                self._remember("assistant", task.last_message)
                return task

            # Proceed to execute approved step
            step = auth_data.get("step")
            if step:
                step.authorized = True
            task.pending_auth = None
            return self._execute_plan(task)

        elif stage == "passphrase":
            if verify_passphrase(user_text):
                step = auth_data.get("step")
                if step:
                    step.authorized = True
                task.pending_auth = None
                return self._execute_plan(task)
            else:
                self.state_machine.transition(task, TaskStatus.BLOCKED, reason="Incorrect passphrase")
                task.last_message = "That passphrase was incorrect. Action blocked."
                self._remember("assistant", task.last_message)
                return task


        return task
