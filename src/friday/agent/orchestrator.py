from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from friday.config import Settings
from friday.learning.trajectory import TrajectoryRecorder
from friday.memory.conversation import ConversationMemory
from friday.models.router import ModelRouter
from friday.security.action_request import ActionRequest
from friday.security.audit import AuditLogger
from friday.security.capabilities import CapabilityRegistry
from friday.security.confirmation import ConfirmationManager
from friday.security.passphrase import verify_passphrase
from friday.security.policy import PolicyEngine
from friday.security.voice_auth import VoiceAuthProvider

from .evaluator import Evaluator
from .executor import Executor
from .fastpath import FastPathRouter
from .planner import Planner
from .recovery import RecoveryManager
from .state import TaskStateMachine
from .steering import SteeringController
from .task import Step, Task, TaskManager, TaskStatus

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
    if action == "computer.type":
        target = args.get("text", "that text")
        return f"Do you want me to type {target}?"
    if action == "computer.press":
        key = args.get("key", "that key")
        return f"Do you want me to press {key}?"
    if action == "computer.control_window":
        op = args.get("action", "control")
        # Get actual active window name for a natural prompt
        try:
            from friday.computer.windows import WindowManager
            wm = WindowManager()
            active = wm.get_active_window()
            app_name = active.title.split(" - ")[-1] if active.title else "the current window"
        except Exception:
            app_name = "the current window"
        return f"Do you want me to {op} {app_name}?"

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
            msg = result.get("message", "")
            if "already running" in msg.lower():
                return msg
            app_id = result.get("app_id", "the application")
            return f"I've opened {app_id} for you."

        if action == "applications.close":
            app_id = result.get("app_id", "the application")
            return f"I've closed {app_id}."

        if action == "computer.control_window":
            op = result.get("action", "controlled")
            app_name = result.get("app_name", "the window")
            return f"Done, I've {op}d {app_name}."

        if action == "system.get_time":
            t = result.get("time", "")
            return f"The current time is {t}."

        if action == "system.get_status":
            cpu = result.get("cpu_percent", "")
            ram = result.get("ram_percent", "")
            return f"System status: CPU is at {cpu}%, RAM usage is at {ram}%."

        if action == "system.lock":
            return "The workstation has been locked. Your screen is now secured."

        if action == "system.remember":
            msg = result.get("message", "Fact stored successfully.")
            return "Got it, Boss. I've remembered that for you."

        if action == "online.search":
            results = result.get("results", [])
            if not results:
                return "I didn't find anything useful for that."
            titles = []
            for r in results[:3]:
                title = r.get("title") if isinstance(r, dict) else str(r)
                if title:
                    titles.append(title)
            if not titles:
                return "I searched, but couldn't get readable results back."
            return "Here's what I found: " + "; ".join(titles)

        if action == "online.weather":
            loc = result.get("location", "your area")
            temp = result.get("temperature_c", "")
            cond = result.get("conditions", "")
            return f"It's {temp} degrees and {cond} in {loc}."

        if "message" in result:
            return str(result["message"])

    return str(result)

class AgentOrchestrator:

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
        
        from friday.memory.episodic import EpisodicMemory
        from friday.memory.preferences import PreferenceMemory
        from friday.memory.priming import ContextPrimingEngine
        from friday.memory.semantic import SemanticMemory
        from friday.skills.registry import SkillRegistry

        db = self.conversation_memory.db # Share the same DB connection wrapper
        self.semantic_memory = SemanticMemory(db)
        self.preference_memory = PreferenceMemory(db)
        self.episodic_memory = EpisodicMemory(db)
        self.skill_registry = SkillRegistry()
        self.priming_engine = ContextPrimingEngine(
            memory_db=self.semantic_memory,
            skill_registry=self.skill_registry,
            preference_store=self.preference_memory,
            episodic_memory=self.episodic_memory,
        )
        
        self.trajectory_recorder = TrajectoryRecorder(trajectories_dir=settings.paths.trajectories_dir)
        self.confirmation_mgr = ConfirmationManager(ttl_seconds=settings.security.confirmation_ttl_seconds)
        self.voice_auth = VoiceAuthProvider()

        self.planner = Planner()
        self.executor = Executor()
        self.evaluator = Evaluator(model_router=self.models)
        self.recovery = RecoveryManager()
        self.steering = SteeringController(
            on_replan=self._trigger_replan,
            on_pause=self._pause_execution
        )
        self.fastpath = FastPathRouter()
        self.state_machine = TaskStateMachine(on_transition=self._on_task_transition)
        self._replan_requested = False
        self._paused = False

    def _on_task_transition(self, task: Task, new_status: TaskStatus, reason: str) -> None:
        try:
            self.audit_logger.log_event(
                event="task.transition",
                task_id=task.id,
                arguments={"status": new_status.value, "reason": reason},
                risk="GREEN",
            )
        except Exception:
            pass

    def _trigger_replan(self, context: dict) -> None:
        """Callback for steering controller to trigger replan."""
        self._replan_requested = True
        try:
            self.audit_logger.log_event(
                event="steering.replan_requested",
                task_id=context.get("task_id", ""),
                arguments={"reason": context.get("reason", "")},
                risk="GREEN",
            )
        except Exception:
            pass

    def _pause_execution(self) -> None:
        """Callback for steering controller to pause execution."""
        self._paused = True
        try:
            self.audit_logger.log_event(
                event="steering.pause_requested",
                task_id="",
                arguments={},
                risk="GREEN",
            )
        except Exception:
            pass

    def _remember(self, role: str, content: str) -> None:
        try:
            self.conversation_memory.append(role, content)
        except Exception:
            pass

    def run(self, goal: str, on_transition: Callable[[TaskStatus], None] | None = None) -> Task:
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

        fast_intent = self.fastpath.match(goal)
        if fast_intent:
            task.plan = [Step(
                action=fast_intent.tool_name, 
                arguments=fast_intent.arguments, 
                expected_observation=fast_intent.success_reply or f"Executed {fast_intent.tool_name}",
                risk_scope=getattr(fast_intent, 'risk_tier', ''),
            )]
            return self._execute_plan(task)

        schemas = self.tools.all_schemas() if hasattr(self.tools, "all_schemas") else []
        history = self.conversation_memory.load_context(self.system_prompt)

        # Prime semantic and episodic memory with full context pipeline
        if hasattr(self, "priming_engine"):
            primed_context = self.priming_engine.prime(goal, history)

            # Combine memories for planner (backward compatible)
            memories = primed_context.relevant_memories + primed_context.relevant_preferences

            # Store full primed context in task for use during execution
            task.primed_context = primed_context
            task.context["required_capabilities"] = primed_context.required_capabilities
            task.context["task_type"] = primed_context.task_type.value
        else:
            memories = []
            task.primed_context = None

        task.plan = self.planner.plan(
            goal=goal,
            available_tools=schemas,
            memories=memories,
            model_router=self.models,
            system_prompt=self.system_prompt,
            conversation_history=history,
            primed_context=task.primed_context,
        )


        return self._execute_plan(task)

    def _execute_plan(self, task: Task) -> Task:
        task.current_step_index = max(task.current_step_index, 0)

        while task.current_step_index < len(task.plan):
            if task.steps_used >= task.max_steps:
                self.state_machine.transition(task, TaskStatus.FAILED, reason="Execution budget exceeded (max_steps)")
                return task
            if task.started_at and (time.time() - task.started_at.timestamp() > task.max_time_seconds):
                self.state_machine.transition(task, TaskStatus.FAILED, reason="Execution budget exceeded (max_time_seconds)")
                return task

            # Check execution budgets before each step
            within_budget, budget_reason = task.check_budgets()
            if not within_budget:
                self.state_machine.transition(task, TaskStatus.FAILED, reason=f"Execution budget exceeded: {budget_reason}")
                self._remember("assistant", f"Task stopped: {budget_reason}")
                self.trajectory_recorder.finish("BUDGET_EXCEEDED")
                return task

            step = task.plan[task.current_step_index]
            task.steps_used += 1
            step.retry_count = task.retries.get(str(task.current_step_index), 0)

            if step.action == "direct_answer":
                reply = step.arguments.get("text", step.expected_observation or "")
                task.last_message = reply
                self.state_machine.transition(task, TaskStatus.EXECUTING, reason="Direct answer")
                self.state_machine.transition(task, TaskStatus.VERIFYING, reason="No verification needed for text")
                self.state_machine.transition(task, TaskStatus.COMPLETED, reason=reply)
                self._remember("assistant", reply)
                self.trajectory_recorder.finish("SUCCESS")
                return task

            if step.action == "error":
                err_msg = step.arguments.get("message", "Planning error")
                self.state_machine.transition(task, TaskStatus.FAILED, reason=err_msg)
                self._remember("assistant", f"I encountered an error: {err_msg}")
                self.trajectory_recorder.finish("FAILURE")
                return task

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
                    prompt = _format_confirmation_prompt(step.action, step.arguments)
                    task.last_message = prompt
                    task.pending_auth = {
                        "step": step,
                        "stage": "voice" if dec_val == "REQUIRE_CONFIRMATION" else "second_factor",
                        "action": step.action,
                        "args": step.arguments,
                    }
                    if task.status != TaskStatus.AWAITING_AUTHORIZATION:
                        self.state_machine.transition(task, TaskStatus.AWAITING_AUTHORIZATION, reason=prompt)
                    self._remember("assistant", prompt)
                    return task

            self.state_machine.transition(task, TaskStatus.EXECUTING, reason=f"Running {step.action}")
            tool = self.tools.get(step.action) if hasattr(self.tools, "get") else None

            if not tool:
                self.state_machine.transition(task, TaskStatus.FAILED, reason=f"Tool not found: {step.action}")
                self._remember("assistant", f"Tool '{step.action}' is not available.")
                self.trajectory_recorder.finish("FAILURE")
                return task

            req = ActionRequest.from_tool(
                tool,
                step.arguments,
                task_id=task.id,
                step_id=str(task.current_step_index),
                requester="planner",
                context_source=getattr(
                    getattr(task.primed_context, "task_type", None),
                    "value",
                    "agent",
                ),
                target=step.arguments.get("text_label") or step.arguments.get("target"),
            )
            exec_result = self.executor.execute(tool, step, max_time_budget=task.max_time_seconds, request=req)

            
            task.observations.append(exec_result.observation)
            
            self.state_machine.transition(task, TaskStatus.VERIFYING, reason="Evaluating execution")
            eval_result = self.evaluator.evaluate(task, step, exec_result, tool)

            self.audit_logger.log_tool_execution(
                task_id=task.id,
                tool_name=step.action,
                risk_tier=tier or "GREEN",
                arguments=step.arguments,
                authorization="ALLOWED",
                result=exec_result.result if eval_result.passed else str(exec_result.error),
                verification=eval_result.reason,
            )

            task.actions.append({
                "step": step.action,
                "arguments": step.arguments,
                "result": exec_result.result,
                "verified": eval_result.passed,
                "verification": eval_result.reason,
            })

            self.trajectory_recorder.record_step(
                action=step.action,
                observation=exec_result.observation,
                result="SUCCESS" if eval_result.passed else "FAILURE",
            )

            if not eval_result.passed:
                self.state_machine.transition(task, TaskStatus.RECOVERING, reason=eval_result.reason)

                # Record failure for learning
                task.failures.append({
                    "step": step.action,
                    "step_index": task.current_step_index,
                    "error": exec_result.error,
                    "observation": exec_result.observation,
                    "verification_reason": eval_result.reason,
                })

                # Steering: handle verification failure
                steering_action = self.steering.on_verification_failure(
                    step_name=step.action,
                    reason=eval_result.reason,
                    context={"observation": exec_result.observation, "expected": step.expected_observation}
                )

                category = self.recovery.classify(exec_result.error or eval_result.reason, {
                    "observation": exec_result.observation,
                    "step": step.action,
                    "expected": step.expected_observation,
                })
                recovery_action = self.recovery.recover(task, step, category)

                # Handle recovery strategies (with steering integration)
                if recovery_action.strategy == "RETRY" or recovery_action.strategy == "WAIT_AND_RETRY":
                    wait_time = recovery_action.payload.get("wait_seconds", 1.0) if recovery_action.payload else 1.0
                    time.sleep(wait_time)
                    # Retry by not advancing step index
                    continue

                elif recovery_action.strategy == "RE_RESOLVE_TARGET":
                    # Re-resolve target with updated context
                    target_desc = recovery_action.payload.get("step_description", "") if recovery_action.payload else ""
                    if target_desc:
                        step.arguments["text_label"] = target_desc
                    # Also trigger steering for target lost
                    self.steering.on_target_lost(target_desc, {"step": step.action})
                    time.sleep(0.5)
                    continue

                elif recovery_action.strategy == "REPLAN" or eval_result.needs_replan or steering_action.type == "replan":
                    observations = [{"step": step.action, "observation": exec_result.observation, "error": exec_result.error}]
                    schemas = self.tools.all_schemas() if hasattr(self.tools, "all_schemas") else []
                    history = self.conversation_memory.load_context(self.system_prompt)
                    task.plan = self.planner.replan(
                        task, observations,
                        available_tools=schemas,
                        model_router=self.models,
                        system_prompt=self.system_prompt,
                        conversation_history=history,
                    )
                    task.current_step_index = 0
                    self.steering.reset_verification_failures()
                    if not task.plan:
                        # Replanning genuinely produced nothing usable. This used to
                        # fall through to the loop's normal exit and get reported as
                        # COMPLETED ("All steps completed") - a failure silently
                        # becoming a false success. Report it honestly instead.
                        self.state_machine.transition(task, TaskStatus.FAILED, reason="Replanning did not produce a usable next step.")
                        self._remember("assistant", "I couldn't figure out how to recover from that, so I'm stopping here.")
                        self.trajectory_recorder.finish("FAILURE")
                        return task
                    continue

                elif recovery_action.strategy == "REPAIR_INPUT":
                    # Attempt to auto-repair input arguments
                    continue

                elif recovery_action.strategy == "ASK_USER":
                    self.state_machine.transition(task, TaskStatus.BLOCKED, reason=recovery_action.reasoning)
                    self._remember("assistant", f"I need your help: {recovery_action.reasoning}")
                    self.trajectory_recorder.finish("BLOCKED")
                    return task

                else:
                    self.state_machine.transition(task, TaskStatus.FAILED, reason=eval_result.reason)
                    self._remember("assistant", f"That failed: {eval_result.reason}")
                    self.trajectory_recorder.finish("FAILURE")
                    return task

            # Reset verification failures on successful step
            self.steering.reset_verification_failures()
            task.current_step_index += 1

        completed_step = task.plan[-1] if task.plan else None
        last_exec = task.actions[-1] if task.actions else None
        self.state_machine.transition(task, TaskStatus.COMPLETED, reason="All steps completed")
        reply = "Done."
        if completed_step is not None and last_exec is not None and last_exec.get("verified") is True:
            reply = _format_natural_reply(completed_step.action, last_exec.get("result"))
        task.last_message = reply
        self._remember("assistant", reply)
        self.trajectory_recorder.finish("SUCCESS")
        return task

    def resume_with_voice(self, task_id: str, user_text: str, audio_path: str | None = None) -> Task | None:
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

            tool_name = auth_data.get("action", "")
            tool = self.tools.get(tool_name) if hasattr(self.tools, "get") else None
            tier = self.tools.tier_of(tool_name) if hasattr(self.tools, "tier_of") else None

            if (tool and getattr(tool, "critical", False)) or tier == "RED":
                auth_data["stage"] = "passphrase"
                task.last_message = "This is a critical action. Please speak the passphrase to proceed."
                self._remember("assistant", task.last_message)
                return task

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

        return task
