"""
Rails ReAct Agent with clean architecture.

This module provides the main agent class that coordinates all components
for intelligent Rails code analysis using the ReAct pattern.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from rich.console import Console

from agent.config import AgentConfig
from agent.tool_registry import ToolRegistry
from agent.state_machine import ReActStateMachine, StepType
from agent.llm_client import LLMClient
from agent.response_analyzer import ResponseAnalyzer
from agent.exceptions import (
    AgentError,
    ReActMaxStepsError,
    ReActLoopError,
)
from agent.logging import AgentLogger, log_agent_start, log_agent_complete
from prompts.system_prompt import RAILS_REACT_SYSTEM_PROMPT
from chat.conversation import ConversationManager


class ReactRailsAgent:
    """
    Rails ReAct Agent with clean separation of concerns.

    This agent uses the ReAct pattern: Reasoning → Action → Observation → (repeat) → Answer
    with proper error handling, logging, and modular components.
    """

    def __init__(self, config: Optional[AgentConfig] = None, session=None):
        """
        Initialize the Rails agent.

        Args:
            config: Agent configuration
            session: ChatSession for LLM communication
        """
        self.config = config or AgentConfig.create_default()
        self.console = Console()
        self.logger = AgentLogger.get_logger(
            level=self.config.log_level, console=self.console
        )

        # Initialize components
        self.tool_registry = ToolRegistry(
            self.config.project_root, debug=self.config.debug_enabled
        )
        self.state_machine = ReActStateMachine()
        self.llm_client = LLMClient(session, self.console)
        self.response_analyzer = ResponseAnalyzer()

        # Initialize conversation manager
        self.conversation = ConversationManager()

        # Performance metrics
        self._start_time: Optional[float] = None

        self.logger.info(
            "ReactRailsAgent initialized",
            {
                "project_root": self.config.project_root,
                "max_steps": self.config.max_react_steps,
                "available_tools": len(self.tool_registry.get_available_tools()),
            },
        )

    def process_message(self, user_query: str) -> str:
        """
        Main entry point for processing user queries using ReAct pattern.

        Args:
            user_query: User's natural language query about Rails code

        Returns:
            Agent's response with analysis results
        """
        self._start_time = time.time()
        log_agent_start(user_query, self.config.project_root)

        try:
            with self.logger.operation("process_message"):
                # Format query based on verbose mode
                if self.config.debug_enabled:
                    # Verbose mode: show full query
                    display_query = user_query
                else:
                    # Compact mode: truncate long queries
                    if len(user_query) > 150:
                        # For multi-line queries, show first line + truncation
                        lines = user_query.split('\n')
                        if len(lines) > 1:
                            display_query = lines[0][:100] + f"... ({len(lines)} lines total)"
                        else:
                            display_query = user_query[:150] + "..."
                    else:
                        display_query = user_query

                self.logger.print_status(f"Analyzing: {display_query}", "working")

                # Reset state for new query
                self.state_machine.reset()
                self.conversation.clear_history()

                # Add user query to conversation
                self.conversation.add_user_message(user_query)

                # Execute ReAct loop
                response = self._execute_react_loop(user_query)

                # Add agent response to history
                self.conversation.add_assistant_message(response)

                # Log completion
                duration_ms = (time.time() - self._start_time) * 1000
                log_agent_complete(
                    duration_ms,
                    self.state_machine.state.current_step,
                    len(self.state_machine.state.tools_used),
                    True,
                )

                return response

        except Exception as e:
            return self._handle_processing_error(e, user_query)

    def _execute_react_loop(self, user_query: str) -> str:
        """
        Execute the main ReAct reasoning and acting loop.

        Args:
            user_query: User's query to analyze

        Returns:
            Final agent response
        """
        # Build initial messages with system prompt and conversation history
        messages = [
            {"role": "system", "content": RAILS_REACT_SYSTEM_PROMPT}
        ] + self.conversation.get_sanitized_history()

        while self.state_machine.should_continue(self.config.max_react_steps):
            try:
                step_num = self.state_machine.state.current_step + 1
                self.logger.set_context(step_number=step_num)

                with self.logger.operation(f"react_step_{step_num}"):
                    # Get LLM response with tool execution
                    llm_response = self._call_llm_with_tools(messages)

                    # Check for API errors - stop immediately without retry
                    if llm_response.error:
                        self.logger.error(
                            f"API error in step {step_num}: {llm_response.error}",
                            {"error": llm_response.error}
                        )
                        # Stop the loop - do not retry the failed request
                        break

                    # Process the response
                    should_stop = self._process_llm_response(
                        llm_response, messages, step_num
                    )

                    if should_stop:
                        break

                    # Check for loop detection
                    self._check_for_loops(step_num)

            except Exception as e:
                self.logger.error(f"Error in ReAct step {step_num}", {"error": str(e)})
                # Stop on any exception to prevent retry loops
                if isinstance(e, (ReActMaxStepsError, ReActLoopError)):
                    break
                # For other exceptions, also break instead of continuing
                # This prevents duplicate API calls on errors
                self.logger.warning(f"Stopping ReAct loop due to exception: {type(e).__name__}")
                break

        # Generate final response
        return self._generate_final_response()

    def _call_llm_with_tools(self, messages: List[Dict[str, Any]]) -> Any:
        """
        Call LLM with available tools and handle the response.

        Args:
            messages: Conversation messages

        Returns:
            LLM response with tool execution results
        """
        tool_schemas = self.tool_registry.build_tool_schemas()

        with self.logger.operation("llm_call"):
            return self.llm_client.call_llm(messages, tool_schemas)

    def _process_llm_response(
        self, llm_response: Any, messages: List[Dict[str, Any]], step_num: int
    ) -> bool:
        """
        Process LLM response and update state machine.

        Args:
            llm_response: Response from LLM
            messages: Current conversation messages
            step_num: Current step number

        Returns:
            True if should stop, False to continue
        """
        # Track tool call status for stuck detection
        has_tool_calls = bool(llm_response.tool_calls)
        self.state_machine.state.record_tool_call_status(has_tool_calls)

        # Record thought step if response has text
        if llm_response.text and llm_response.text.strip():
            self.state_machine.record_thought(llm_response.text)
            self.logger.log_react_step("thought", step_num, llm_response.text)

        # Record action and observation steps for tool calls
        if llm_response.tool_calls:
            # Add tool messages to conversation manager
            tool_messages = self.llm_client.format_tool_messages(
                llm_response.tool_calls
            )
            self.conversation.add_tool_messages(tool_messages)
            if step_num > 1:
                context_prompt = self._build_context_prompt()
                self._append_to_last_user_message(messages, context_prompt)
            else:
                self._refresh_messages_from_history(messages)

            # Process each tool call
            for tool_call in llm_response.tool_calls:
                # tool_call is a ToolCall object, not a dict
                tool_name = tool_call.name
                tool_input = tool_call.input

                # Record action
                self.state_machine.record_action(tool_name, tool_input)
                self.logger.log_react_step(
                    "action", step_num, f"Used {tool_name}", tool_name
                )

                # Record observation
                if tool_call.result:
                    result_text = tool_call.result
                    self.state_machine.record_observation(result_text, result_text)
                    self.logger.log_react_step("observation", step_num, result_text)

        # Check for stuck state: no tool calls for multiple consecutive steps
        if self.state_machine.state.is_stuck_without_tools(max_consecutive_no_tools=2):
            self.logger.warning(
                f"Agent stuck: {self.state_machine.state.consecutive_no_tool_calls} consecutive steps without tool calls"
            )
            # Force finalization with current knowledge
            if llm_response.text and llm_response.text.strip():
                self.state_machine.record_answer(llm_response.text)
                self.logger.log_react_step("answer", step_num, llm_response.text)
                return True
            else:
                # No meaningful response, stop with error
                self.state_machine.state.stop_with_reason(
                    "Agent stuck without tool calls"
                )
                return True

        # Check for timeout after finalization request
        if self.state_machine.state.is_stuck_after_finalization(
            max_steps_after_finalization=2
        ):
            self.logger.warning(f"Finalization timeout at step {step_num}")
            # Use the last meaningful response as answer
            if llm_response.text and llm_response.text.strip():
                self.state_machine.record_answer(llm_response.text)
                self.logger.log_react_step("answer", step_num, llm_response.text)
                return True
            else:
                self.state_machine.state.stop_with_reason("Finalization timeout")
                return True

        # Analyze response to determine if we should stop
        analysis = self.response_analyzer.analyze_response(
            llm_response.text, self.state_machine.state, step_num
        )

        if analysis.is_final:
            self.state_machine.record_answer(llm_response.text)
            self.logger.log_react_step("answer", step_num, llm_response.text)
            return True

        # Check if we should request finalization
        if (
            llm_response.tool_calls
            and self.response_analyzer.has_high_quality_tool_results(
                self.state_machine.state
            )
            and not self.state_machine.state.finalize_requested
        ):
            finalization_prompt = self.response_analyzer.generate_finalization_prompt()
            self._append_to_last_user_message(messages, finalization_prompt)
            self.state_machine.state.request_finalization()

        # Check if we should force different tool usage
        elif self.response_analyzer.should_force_different_tool(
            self.state_machine.state, step_num, self.config.tool_repetition_limit
        ):
            available_tools = set(self.tool_registry.get_tool_names())
            constraint_prompt = self.response_analyzer.generate_tool_constraint_prompt(
                self.state_machine.state, available_tools
            )
            self._append_to_last_user_message(messages, constraint_prompt)

        return False

    def _append_to_last_user_message(
        self, messages: List[Dict[str, Any]], text: str
    ) -> None:
        """Append text to the last user message and sync local state."""
        if not text:
            return

        self.conversation.append_to_last_user_message(text)
        self._refresh_messages_from_history(messages)

    def _refresh_messages_from_history(self, messages: List[Dict[str, Any]]) -> None:
        """Sync the working message list with the conversation history."""
        updated = [
            {"role": "system", "content": RAILS_REACT_SYSTEM_PROMPT}
        ] + self.conversation.get_sanitized_history()
        self._strip_prompt_caching_metadata(updated)
        messages[:] = updated

    def _strip_prompt_caching_metadata(self, messages: List[Dict[str, Any]]) -> None:
        for message in messages:
            self._strip_prompt_caching_from_message(message)

    def _strip_prompt_caching_from_message(self, message: Dict[str, Any]) -> None:
        if not isinstance(message, dict):
            return
        message.pop("cache_control", None)
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    block.pop("cache_control", None)

    def _build_context_prompt(self) -> str:
        """Build context-aware prompt for the current step."""
        available_tools = set(self.tool_registry.get_tool_names())
        return self.state_machine.get_context_prompt(available_tools)

    def _check_for_loops(self, step_num: int) -> None:
        """Check for and handle infinite loops in the ReAct process."""
        # Check for tool repetition without results
        if self.state_machine.state.should_force_different_tool(step_threshold=2):
            self.logger.warning(
                f"Potential loop detected at step {step_num}: repeated tool usage"
            )

            # If we've used significant steps without progress, stop
            if step_num > self.config.max_react_steps // 2:
                raise ReActLoopError(
                    step_num,
                    "Repeated tool usage without progress",
                    {"tools_used": list(self.state_machine.state.tools_used)},
                )

        # Check for stuck state (no tool calls repeatedly)
        if self.state_machine.state.is_stuck_without_tools(max_consecutive_no_tools=3):
            self.logger.error(
                f"Loop detected at step {step_num}: agent stuck without tool calls"
            )
            raise ReActLoopError(
                step_num,
                "Agent not making tool calls for multiple consecutive steps",
                {
                    "consecutive_no_tool_calls": self.state_machine.state.consecutive_no_tool_calls
                },
            )

    def _generate_final_response(self) -> str:
        """Generate the final response based on ReAct steps."""
        if (
            self.state_machine.state.should_stop
            and self.state_machine.state.stop_reason
        ):
            # We have a final answer
            answer_steps = [
                step
                for step in self.state_machine.state.steps
                if step.step_type == StepType.ANSWER
            ]
            if answer_steps:
                return answer_steps[-1].content

        # Generate summary if we hit limits
        if self.state_machine.state.stop_reason:
            return self._generate_timeout_summary()

        # Fallback: use the last meaningful response
        return self._generate_fallback_summary()

    def _generate_timeout_summary(self) -> str:
        """Generate a summary when the ReAct loop times out."""
        summary_parts = [
            "## Analysis Timeout - Partial Results\n",
            f"⚠️ **Analysis stopped: {self.state_machine.state.stop_reason}**\n",
        ]

        action_count = sum(
            1
            for step in self.state_machine.state.steps
            if step.step_type == StepType.ACTION
        )
        summary_parts.append(f"**Tools executed:** {action_count}")

        # Show the analysis trail
        summary_parts.append("### Analysis Trail:")
        for i, step in enumerate(self.state_machine.state.steps, 1):
            if step.step_type == StepType.THOUGHT:
                content = (
                    step.content[:100] + "..."
                    if len(step.content) > 100
                    else step.content
                )
                summary_parts.append(f"{i}. **Thought:** {content}")
            elif step.step_type == StepType.ACTION:
                summary_parts.append(f"{i}. **Action:** Used {step.tool_name}")
            elif step.step_type == StepType.OBSERVATION:
                content = (
                    step.content[:100] + "..."
                    if len(step.content) > 100
                    else step.content
                )
                summary_parts.append(f"{i}. **Result:** {content}")

        summary_parts.append(
            "\n**Suggestion:** Try a more specific query or use different search terms."
        )

        return "\n\n".join(summary_parts)

    def _generate_fallback_summary(self) -> str:
        """Generate a fallback summary of the analysis."""
        if not self.state_machine.state.steps:
            return "No analysis steps completed."

        summary_parts = ["## Rails Code Analysis Summary\n"]

        for step in self.state_machine.state.steps:
            if step.step_type == StepType.THOUGHT:
                summary_parts.append(f"**Reasoning:** {step.content}")
            elif step.step_type == StepType.ACTION:
                summary_parts.append(f"**Tool Used:** {step.tool_name}")
            elif step.step_type == StepType.OBSERVATION:
                content = (
                    step.content[:200] + "..."
                    if len(step.content) > 200
                    else step.content
                )
                summary_parts.append(f"**Result:** {content}")

        return "\n\n".join(summary_parts)

    def _handle_processing_error(self, error: Exception, user_query: str) -> str:
        """
        Handle errors during message processing.

        Args:
            error: The exception that occurred
            user_query: Original user query

        Returns:
            Error response message
        """
        duration_ms = (time.time() - self._start_time) * 1000 if self._start_time else 0
        log_agent_complete(
            duration_ms,
            self.state_machine.state.current_step,
            len(self.state_machine.state.tools_used),
            False,
        )

        if isinstance(error, AgentError):
            self.logger.error(f"Agent error: {error.message}", error.details)
            return f"Analysis error: {error.message}"
        else:
            self.logger.error(f"Unexpected error: {error}", exc_info=True)
            return f"Unexpected error during analysis: {error}"

    def set_project_root(self, project_root: str) -> None:
        """
        Update the project root and refresh components.

        Args:
            project_root: New project root directory
        """
        self.config = self.config.update(project_root=project_root)
        self.tool_registry.refresh(project_root)
        self.logger.info(f"Project root updated to: {project_root}")

    def get_status(self) -> Dict[str, Any]:
        """Get current agent status."""
        return {
            "config": self.config.to_dict(),
            "tool_registry": self.tool_registry.get_status_summary(),
            "state_machine": self.state_machine.state.to_dict(),
            "llm_client": self.llm_client.get_session_info(),
            "conversation_length": len(self.conversation.history),
        }

    def get_step_summary(self, limit: int = 12) -> str:
        """
        Return a compact human-readable summary of recent ReAct steps.

        Args:
            limit: Maximum number of steps to include

        Returns:
            Brief summary suitable for CLI display
        """
        return self.state_machine.state.get_summary(limit)
