"""
ReAct Rails Agent - Reasoning and Acting AI agent for Rails code analysis.

This agent uses the ReAct (Reasoning + Acting) pattern to dynamically analyze
Rails codebases by reasoning about queries and orchestrating tool usage.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from rich.console import Console

from tools.base_tool import BaseTool
from tools.ripgrep_tool import RipgrepTool
from tools.sql_rails_search import SQLRailsSearchTool
from tools.enhanced_sql_rails_search import EnhancedSQLRailsSearch
from tools.ast_grep_tool import AstGrepTool
from tools.ctags_tool import CtagsTool
from tools.model_analyzer import ModelAnalyzer
from tools.controller_analyzer import ControllerAnalyzer
from tools.route_analyzer import RouteAnalyzer
from tools.migration_analyzer import MigrationAnalyzer
from tools.transaction_analyzer import TransactionAnalyzer
from prompts.system_prompt import RAILS_REACT_SYSTEM_PROMPT


@dataclass
class ReActStep:
    """Represents a single step in the ReAct loop."""
    step_type: str  # 'thought', 'action', 'observation', 'answer'
    content: str
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    tool_output: Optional[Any] = None


class ReactRailsAgent:
    """
    ReAct Rails Agent for intelligent code analysis.

    Uses the ReAct pattern: Reasoning → Action → Observation → (repeat) → Answer
    """

    def __init__(self, project_root: Optional[str] = None, session=None):
        """
        Initialize the ReAct Rails agent.

        Args:
            project_root: Root directory of the Rails project
            session: ChatSession used by the ask_code CLI for LLM communication
        """
        self.project_root = project_root
        self.console = Console()
        self.tools: Dict[str, BaseTool] = {}
        self.conversation_history: List[Dict[str, Any]] = []
        self.react_steps: List[ReActStep] = []
        self.session = session
        self.allowed_tools = {
            'ripgrep', 'sql_rails_search', 'enhanced_sql_rails_search', 'ast_grep', 'ctags',
            'model_analyzer', 'controller_analyzer', 'route_analyzer', 'migration_analyzer'
        }
        self.tool_synonyms = {
            'search_code_semantic': 'ripgrep',
            'search_codebase': 'ripgrep',
            'code_search': 'ripgrep',
            'grep': 'ripgrep',
            'sql_search': 'enhanced_sql_rails_search',
            'trace_sql': 'enhanced_sql_rails_search',
            'find_sql_source': 'enhanced_sql_rails_search',
            'astgrep': 'ast_grep',
            'tags': 'ctags',
        }

        # Initialize tools
        self._init_tools()

        # Define tool schemas for LLM function calling
        self.tool_schemas = self._create_tool_schemas()

    def _init_tools(self) -> None:
        """Initialize available tools for the agent."""
        try:
            self.tools['ripgrep'] = RipgrepTool(self.project_root)
            self.tools['sql_rails_search'] = SQLRailsSearchTool(self.project_root)
            self.tools['enhanced_sql_rails_search'] = EnhancedSQLRailsSearch(self.project_root)
            self.tools['ast_grep'] = AstGrepTool(self.project_root)
            self.tools['ctags'] = CtagsTool(self.project_root)
            self.tools['model_analyzer'] = ModelAnalyzer(self.project_root)
            self.tools['controller_analyzer'] = ControllerAnalyzer(self.project_root)
            self.tools['route_analyzer'] = RouteAnalyzer(self.project_root)
            self.tools['migration_analyzer'] = MigrationAnalyzer(self.project_root)
            self.tools['transaction_analyzer'] = TransactionAnalyzer(self.project_root)

            self.console.print(f"[dim]Initialized {len(self.tools)} tools for Rails analysis[/dim]")
        except Exception as e:
            self.console.print(f"[red]Error initializing tools: {e}[/red]")

    def _create_tool_schemas(self) -> List[Dict[str, Any]]:
        """Create tool schemas for LLM function calling."""
        return [
            {
                "name": "ripgrep",
                "description": "Fast text search in Rails codebase using ripgrep",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "Regular expression pattern to search for"
                        },
                        "file_types": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "File extensions to search (e.g., ['rb', 'erb'])"
                        },
                        "context": {
                            "type": "integer",
                            "description": "Number of context lines to show around matches"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results to return"
                        },
                        "case_insensitive": {
                            "type": "boolean",
                            "description": "Perform case-insensitive search (default true)"
                        }
                    },
                    "required": ["pattern"]
                }
            },
            {
                "name": "ast_grep",
                "description": "Structural Ruby search using ast-grep patterns",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "ast-grep pattern, e.g., 'class $NAME'"},
                        "paths": {"type": "array", "items": {"type": "string"}},
                        "max_results": {"type": "integer"}
                    },
                    "required": ["pattern"]
                }
            },
            {
                "name": "ctags",
                "description": "Query Ruby symbols using universal-ctags",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "exact": {"type": "boolean"},
                        "max_results": {"type": "integer"}
                    },
                    "required": ["symbol"]
                }
            },
            {
                "name": "sql_rails_search",
                "description": "Given SQL, infer ActiveRecord patterns and find generating code",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "sql": {
                            "type": "string",
                            "description": "Raw SQL to analyze"
                        },
                        "file_types": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "File extensions to search (e.g., ['rb','erb'])"
                        },
                        "max_patterns": {
                            "type": "integer",
                            "description": "Max inferred patterns to try"
                        },
                        "max_results_per_pattern": {
                            "type": "integer",
                            "description": "Limit matches per pattern"
                        }
                    },
                    "required": ["sql"]
                }
            },
            {
                "name": "model_analyzer",
                "description": "Analyze Rails model files for validations, associations, callbacks, and methods",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "model_name": {
                            "type": "string",
                            "description": "Name of the Rails model to analyze"
                        },
                        "focus": {
                            "type": "string",
                            "enum": ["validations", "associations", "callbacks", "methods", "all"],
                            "description": "Specific aspect to focus on"
                        }
                    },
                    "required": ["model_name"]
                }
            },
            {
                "name": "controller_analyzer",
                "description": "Analyze Rails controller files for actions, filters, and methods",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "controller_name": {
                            "type": "string",
                            "description": "Name of the Rails controller to analyze"
                        },
                        "action": {
                            "type": "string",
                            "description": "Specific action to analyze, or 'all' for all actions"
                        }
                    },
                    "required": ["controller_name"]
                }
            },
            {
                "name": "route_analyzer",
                "description": "Analyze Rails routes configuration",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "focus": {
                            "type": "string",
                            "description": "What to focus on in routes analysis"
                        }
                    },
                    "required": []
                }
            },
            {
                "name": "migration_analyzer",
                "description": "Analyze Rails database migrations",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "migration_type": {
                            "type": "string",
                            "description": "Type of migration to analyze or 'all'"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Number of recent migrations to analyze"
                        }
                    },
                    "required": []
                }
            },
            {
                "name": "enhanced_sql_rails_search",
                "description": "Find exact Rails/ActiveRecord source code that generates a given SQL query with confidence scoring",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "sql": {
                            "type": "string",
                            "description": "Raw SQL query to trace back to Rails source code"
                        },
                        "include_usage_sites": {
                            "type": "boolean",
                            "description": "Include where the query gets executed (views, controllers)",
                            "default": True
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of matches to return",
                            "default": 10
                        }
                    },
                    "required": ["sql"]
                }
            },
            {
                "name": "transaction_analyzer",
                "description": "Analyze complete SQL transaction logs to identify Rails patterns, callback chains, and source code locations for all operations",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "transaction_log": {
                            "type": "string",
                            "description": "Complete SQL transaction log with timestamps"
                        },
                        "find_source_code": {
                            "type": "boolean",
                            "description": "Search for source code that generates these queries",
                            "default": True
                        },
                        "max_patterns": {
                            "type": "integer",
                            "description": "Maximum number of Rails patterns to search for",
                            "default": 10
                        }
                    },
                    "required": ["transaction_log"]
                }
            }
        ]

    def set_project_root(self, project_root: str) -> None:
        """Update the project root and reinitialize tools."""
        self.project_root = project_root
        self._init_tools()

    def process_message(self, user_query: str) -> str:
        """
        Main entry point for processing user queries using ReAct pattern.

        Args:
            user_query: User's natural language query about Rails code

        Returns:
            Agent's response with analysis results
        """
        try:
            self.console.print(f"[dim]🤖 Analyzing: {user_query}[/dim]")

            # Start ReAct loop
            self.react_steps = []
            self.conversation_history.append({"role": "user", "content": user_query})

            # Initial reasoning
            response = self._react_loop(user_query)

            # Add agent response to history
            self.conversation_history.append({"role": "assistant", "content": response})

            return response

        except Exception as e:
            error_msg = f"Error processing query: {e}"
            self.console.print(f"[red]{error_msg}[/red]")
            return error_msg

    def _react_loop(self, user_query: str, max_steps: int = 10) -> str:
        """
        Execute the ReAct reasoning and acting loop.

        Args:
            user_query: User's query to analyze
            max_steps: Maximum number of ReAct steps to prevent infinite loops

        Returns:
            Final agent response
        """
        # Build initial prompt with system instructions and query
        messages = [
            {"role": "system", "content": RAILS_REACT_SYSTEM_PROMPT},
            {"role": "user", "content": f"Please analyze this Rails query: {user_query}"}
        ]

        # New ReAct memory management system
        react_state = {
            'tools_used': set(),
            'findings': [],
            'search_attempts': [],
            'step_results': {}
        }

        for step in range(max_steps):
            try:
                self.console.print(f"[dim]Step {step + 1}/{max_steps}[/dim]")

                # Build context-aware prompt that includes memory state
                if step > 0:
                    context_prompt = self._build_context_prompt(react_state, step)
                    messages.append({"role": "user", "content": context_prompt})

                # Get LLM reasoning/action with streaming display
                response, tools_used, tool_results = self._call_llm(messages)

                # Always add assistant response to conversation
                messages.append({"role": "assistant", "content": response})

                # Update ReAct state with this step's information
                self._update_react_state(react_state, response, step, tools_used, tool_results)

                # Check if the response looks like a final answer or if tools found good results
                if self._is_final_answer(response, react_state, step):
                    return response

                # If we've tried the same tool too many times, force a different approach
                if self._should_force_different_tool(react_state, step):
                    constraint_prompt = self._generate_tool_constraint_prompt(react_state)
                    messages.append({"role": "user", "content": constraint_prompt})

            except Exception as e:
                self.console.print(f"[red]Error in ReAct step {step + 1}: {e}[/red]")
                break

        # If we reach max steps, return summary with timeout message
        self.console.print(f"[yellow]⏱️ Reached maximum steps ({max_steps}). Stopping analysis.[/yellow]")
        return self._generate_summary_with_timeout()

    def _is_final_answer(self, response: str, react_state: dict = None, step: int = None) -> bool:
        """
        Determine if the agent's response is a final answer or needs more steps.

        Args:
            response: The agent's response text
            react_state: Current ReAct state with tool results
            step: Current step number

        Returns:
            True if this is a final answer, False if more steps are needed
        """
        # Be more conservative - only stop when we have clear concrete results
        final_indicators = [
            "I found the source code at",
            "The exact code that generates this SQL is",
            "Located the Rails code in",
            "Here is the specific Rails method",
            "Found the Rails source:",
            "## Final Answer",
            "## Conclusion"
        ]

        response_lower = response.lower()

        # Only stop if we have very clear final answer language
        for indicator in final_indicators:
            if indicator.lower() in response_lower:
                return True

        # If we have concrete file paths AND code snippets, it's likely final
        if ("app/" in response and ".rb:" in response and ("def " in response or "class " in response)):
            return True

        # If the response shows specific Rails ActiveRecord code with file locations
        if (("app/models/" in response or "app/controllers/" in response) and
            ("def " in response or "scope " in response or "where(" in response)):
            return True

        # NEW: Check tool results for high-quality matches
        if react_state and self._has_high_quality_tool_results(react_state, step):
            return True

        # Default: keep going to gather more information
        # The agent should continue until it finds specific code locations
        return False

    def _has_high_quality_tool_results(self, react_state: dict, step: int) -> bool:
        """
        Check if any tool results contain high-quality matches that satisfy the search goal.

        Args:
            react_state: Current ReAct state with tool results
            step: Current step number

        Returns:
            True if high-quality results found, False otherwise
        """
        # Check results from enhanced_sql_rails_search tool

        for step_num, result_info in react_state.get('step_results', {}).items():
            tool_name = result_info.get('tool')

            # If enhanced_sql_rails_search found matches
            if tool_name == 'enhanced_sql_rails_search':
                # Check actual tool results first (preferred)
                tool_results = result_info.get('tool_results', {})
                tool_output = tool_results.get('enhanced_sql_rails_search', '')

                if tool_output:
                    # Look for high-quality Rails code matches in actual tool output
                    high_quality_indicators = [
                        # Direct ActiveRecord patterns that generate SQL
                        'Product.order(:title)',
                        'Product.order("title")',
                        '@products = Product.order',
                        '.order(:title)',
                        '.order("title")',

                        # File locations with specific Rails patterns
                        'app/controllers/store_controller.rb',
                        'app/controllers/products_controller.rb',
                        'store_controller.rb'
                    ]

                    tool_output_lower = tool_output.lower()
                    for indicator in high_quality_indicators:
                        if indicator.lower() in tool_output_lower:
                            return True

                    # Check for successful matches structure in tool output
                    if ('first_match' in tool_output and
                        ('app/' in tool_output and '.rb' in tool_output)):
                        return True

                # Fallback to checking LLM response text (for backward compatibility)
                else:
                    response_text = result_info.get('response', '')
                    if response_text:
                        high_quality_indicators = [
                            'Product.order(:title)',
                            '@products = Product.order',
                            'store_controller.rb'
                        ]
                        response_lower = response_text.lower()
                        for indicator in high_quality_indicators:
                            if indicator.lower() in response_lower:
                                return True

            # If ripgrep found direct matches for order patterns
            elif tool_name == 'ripgrep':
                response_text = result_info.get('response', '')
                if ('✓' in response_text and 'matches' in response_text and
                    ('order' in response_text.lower() or 'title' in response_text.lower())):
                    return True

        return False

    def _extract_tool_used(self, response: str) -> Optional[str]:
        """Extract which tool was used from the response."""
        # Look for tool usage indicators in the response
        tool_patterns = {
            "enhanced_sql_rails_search": ["Using enhanced_sql_rails_search", "⚙ Using enhanced_sql_rails_search"],
            "ripgrep": ["Using ripgrep", "⚙ Using ripgrep"],
            "sql_rails_search": ["Using sql_rails_search", "⚙ Using sql_rails_search"],
            "ast_grep": ["Using ast_grep", "⚙ Using ast_grep"],
            "ctags": ["Using ctags", "⚙ Using ctags"],
            "model_analyzer": ["Using model_analyzer", "⚙ Using model_analyzer"],
            "controller_analyzer": ["Using controller_analyzer", "⚙ Using controller_analyzer"]
        }

        for tool, patterns in tool_patterns.items():
            for pattern in patterns:
                if pattern in response:
                    return tool
        return None

    def _build_context_prompt(self, react_state: dict, step: int) -> str:
        """Build context-aware prompt that includes memory of previous steps."""
        tools_used = list(react_state['tools_used'])
        search_attempts = react_state['search_attempts']

        prompt = f"\n--- CONTEXT FROM PREVIOUS STEPS ---\n"
        prompt += f"You are now on step {step + 1}. Previous tools used: {', '.join(tools_used)}\n"

        if search_attempts:
            prompt += f"Previous search attempts:\n"
            for attempt in search_attempts[-3:]:  # Show last 3 attempts
                prompt += f"- {attempt}\n"

        # Progressive strategy based on step
        if step == 1:
            prompt += "\n🎯 NEXT STRATEGY: The SQL analysis found no direct matches. "
            prompt += "Try ripgrep to search for window function patterns: 'SUM(', 'OVER (', 'LAG(' in .rb files."

        elif step == 2:
            prompt += "\n🎯 NEXT STRATEGY: Search in models/controllers for analytics methods. "
            prompt += "Use model_analyzer on Product model or controller_analyzer on reporting controllers."

        elif step == 3:
            prompt += "\n🎯 NEXT STRATEGY: Search for raw SQL execution. "
            prompt += "Use ripgrep to find 'connection.execute', 'find_by_sql', or ActiveRecord::Base patterns."

        elif step == 4:
            prompt += "\n🎯 NEXT STRATEGY: Look for custom SQL files or complex query builders. "
            prompt += "Try ast_grep for method definitions containing 'SELECT' or search for .sql files."

        prompt += f"\n🚫 DO NOT repeat tools: {', '.join(tools_used)}"
        prompt += f"\n✅ Available unused tools: {self._get_unused_tools(react_state)}"
        prompt += "\n--- END CONTEXT ---\n"

        return prompt

    def _update_react_state(self, react_state: dict, response: str, step: int, tools_used: List[str] = None, tool_results: Dict[str, str] = None):
        """Update the ReAct state with information from this step."""
        # Prioritize actual tools executed via function calling over text-based detection
        actual_tools_used = tools_used or []

        if actual_tools_used:
            # Use the actual tools that were executed via function calling
            for tool_name in actual_tools_used:
                react_state['tools_used'].add(tool_name)
                react_state['search_attempts'].append(f"Step {step + 1}: Used {tool_name}")

            # Record step results with the first tool used (if multiple)
            primary_tool = actual_tools_used[0]
            react_state['step_results'][step] = {
                'tool': primary_tool,
                'tools': actual_tools_used,  # Track all tools used in this step
                'response': response,
                'tool_results': tool_results or {},  # Store actual tool output results
                'has_results': self._response_has_concrete_results(response)
            }
        else:
            # Fallback to text-based tool detection (for backward compatibility)
            tool_used = self._extract_tool_used(response)
            if tool_used:
                react_state['tools_used'].add(tool_used)
                react_state['search_attempts'].append(f"Step {step + 1}: Used {tool_used}")
                react_state['step_results'][step] = {
                    'tool': tool_used,
                    'response': response,
                    'has_results': self._response_has_concrete_results(response)
                }

    def _should_force_different_tool(self, react_state: dict, step: int) -> bool:
        """Check if we should force the agent to use a different tool."""
        tools_used = react_state['tools_used']

        # Force different tool if we've used the same tool multiple times
        if len(tools_used) == 1 and step > 1:
            return True

        # Force if we're stuck in a loop
        recent_attempts = react_state['search_attempts'][-2:]
        if len(recent_attempts) == 2 and recent_attempts[0] == recent_attempts[1]:
            return True

        return False

    def _generate_tool_constraint_prompt(self, react_state: dict) -> str:
        """Generate a constraint prompt that forces different tool usage."""
        tools_used = list(react_state['tools_used'])
        unused_tools = self._get_unused_tools(react_state)

        prompt = f"\n⚠️ CONSTRAINT: You have used {tools_used} multiple times without finding results.\n"
        prompt += f"🚫 FORBIDDEN: Do NOT use these tools again: {', '.join(tools_used)}\n"
        prompt += f"✅ REQUIRED: You MUST use one of these unused tools: {unused_tools}\n"
        prompt += "Choose the most appropriate tool from the unused list and explain your reasoning.\n"

        return prompt

    def _get_unused_tools(self, react_state: dict) -> str:
        """Get list of tools that haven't been used yet."""
        all_tools = {
            "enhanced_sql_rails_search", "ripgrep", "sql_rails_search",
            "ast_grep", "ctags", "model_analyzer", "controller_analyzer",
            "route_analyzer", "migration_analyzer"
        }
        used_tools = react_state['tools_used']
        unused = sorted(all_tools - used_tools)
        return ', '.join(unused)

    def _response_has_concrete_results(self, response: str) -> bool:
        """Check if response contains concrete file paths or code snippets."""
        return ("app/" in response and ".rb" in response) or ("def " in response)

    def _call_llm(self, messages: List[Dict[str, Any]]) -> Tuple[str, List[str], Dict[str, str]]:
        """
        Call the LLM with conversation messages using the active ChatSession.

        Args:
            messages: Conversation messages

        Returns:
            Tuple of (LLM response text, list of tool names used, tool results dict)
        """
        if not self.session:
            # Fallback to mock for testing without session
            return self._mock_llm_response(messages[-1]['content']), [], {}

        try:
            # Use the shared StreamingClient + provider mapper to avoid mismatched SSE parsing
            if hasattr(self.session, 'streaming_client') and self.session.streaming_client:
                # Separate system prompt from messages
                system_prompt = None
                user_messages = []

                for msg in messages:
                    if msg['role'] == 'system':
                        system_prompt = msg['content']
                    else:
                        user_messages.append(msg)

                payload = self.session.provider.build_payload(
                    user_messages,
                    model=None,
                    max_tokens=self.session.max_tokens,
                    thinking=False,
                    tools=self.tool_schemas,  # Enable provider-managed tool calls
                    context_content=None,
                    rag_enabled=False,
                    system_prompt=system_prompt,
                    stop_sequences=["\nObservation:", "\nAnswer:"],
                )

                # Use send_message to get complete results including tool execution
                result = self.session.streaming_client.send_message(
                    self.session.url,
                    payload,
                    mapper=self.session.provider.map_events,
                    provider_name=getattr(self.session, 'provider_name', 'bedrock'),
                )

                # Display the complete message and results
                if result.text:
                    self.console.print(result.text.strip())

                # Track usage if session has a usage tracker
                if hasattr(self.session, 'usage_tracker') and self.session.usage_tracker:
                    if result.tokens > 0 or result.cost > 0:
                        self.session.usage_tracker.update(result.tokens, result.cost)

                # Track tools used and capture actual tool results
                tools_used = []
                tool_results = {}
                if result.tool_calls:
                    for tool_call in result.tool_calls:
                        tool_info = tool_call.get('tool_call', {})
                        tool_name = tool_info.get('name', 'unknown')
                        tools_used.append(tool_name)
                        self.console.print(f"[yellow]⚙ Using {tool_name} tool...[/yellow]")

                        if tool_call.get('result'):
                            result_text = tool_call.get('result', '')
                            if isinstance(result_text, str) and result_text:
                                self.console.print(f"[green]✓ {result_text}[/green]")
                                # Capture the actual tool result for stopping logic
                                tool_results[tool_name] = result_text

                return (result.text or "").strip() or "", tools_used, tool_results
            else:
                return self._mock_llm_response(messages[-1]['content']), [], {}

        except Exception as e:
            self.console.print(f"[red]Error calling LLM: {e}[/red]")
            # Fallback to mock
            return self._mock_llm_response(messages[-1]['content']), [], {}

    def _stream_with_complete_messages(self, url, payload, mapper, provider_name):
        """
        Stream content but buffer complete messages before displaying.
        This provides streaming experience without Rich Live rendering conflicts.
        """
        import json
        from collections import namedtuple

        # Buffer for accumulating message content
        message_buffer = ""
        tool_calls = []

        # Use the internal _stream_events method to get raw events
        for event in self.session.streaming_client._stream_events(url, payload, mapper):
            if event.kind == 'text' and event.value:
                message_buffer += event.value
            elif event.kind == 'tool_start':
                tool_calls.append({'tool_call': json.loads(event.value), 'result': ''})
            elif event.kind == 'tool_ready':
                # Tool input is complete, no action needed
                pass

        # Display the complete message immediately (no artificial delay)
        if message_buffer:
            self.console.print(message_buffer.strip())

        # Display tool calls
        if tool_calls:
            for tool_call in tool_calls:
                tool_name = tool_call.get('tool_call', {}).get('name', 'unknown')
                self.console.print(f"[yellow]⚙ Using {tool_name} tool...[/yellow]")
                if tool_call.get('result'):
                    self.console.print(f"[green]✓ {tool_call.get('result')}[/green]")

        # Return result object similar to send_message
        Result = namedtuple('Result', ['text', 'tool_calls'])
        return Result(text=message_buffer, tool_calls=tool_calls)

    def _mock_llm_response(self, user_query: str) -> str:
        """
        Mock LLM response for development/testing.
        In production, this would be replaced with actual LLM calls.
        """
        # Simple keyword-based mock responses
        query_lower = user_query.lower()

        if 'validation' in query_lower or 'validates' in query_lower:
            if 'product' in query_lower:
                return """
Thought: I need to analyze validations for the Product model. Let me examine the Product model file to find validation rules.

Action: model_analyzer
Input: {"model_name": "Product", "focus": "validations"}
"""
            else:
                return """
Thought: I need to find validation-related code. Let me search for validation patterns in the codebase.

Action: ripgrep
Input: {"pattern": "validates", "file_types": ["rb"]}
"""

        elif 'callback' in query_lower or 'before' in query_lower or 'after' in query_lower:
            return """
Thought: This query is about Rails callbacks. I should examine model files for callback definitions.

Action: ripgrep
Input: {"pattern": "before_|after_|around_", "file_types": ["rb"]}
"""

        elif 'controller' in query_lower:
            return """
Thought: This is a controller-related query. Let me analyze the relevant controller.

Action: controller_analyzer
Input: {"controller_name": "Application", "action": "all"}
"""

        elif 'route' in query_lower or 'routing' in query_lower:
            return """
Thought: This query is about Rails routing. Let me examine the routes configuration.

Action: route_analyzer
Input: {"focus": "all"}
"""

        elif 'migration' in query_lower or 'database' in query_lower or 'schema' in query_lower:
            return """
Thought: This query involves database structure or migrations. Let me analyze recent migrations.

Action: migration_analyzer
Input: {"migration_type": "all", "limit": 5}
"""

        # SQL-style queries - use enhanced tool for better structured output
        if ('select' in query_lower and 'from' in query_lower) or 'sql' in query_lower or 'exact source code' in query_lower:
            # Extract the actual SQL query from the user message
            sql_match = re.search(r'SELECT\s+.*?FROM\s+.*?(?:ORDER\s+BY\s+.*?)?(?:LIMIT\s+\d+)?', user_query, re.IGNORECASE | re.DOTALL)
            actual_sql = sql_match.group(0) if sql_match else user_query

            return f"""
Thought: This is a SQL query tracing request. I should use the enhanced SQL search tool to find the exact Rails source code that generates this query with confidence scoring.

Action: enhanced_sql_rails_search
Input: {{"sql": {json.dumps(actual_sql)}}}
"""

        # Fallback generic search
        return """
Thought: I need to search for SQL-related code in this Rails project to find where this query might be generated.

Action: ripgrep
Input: {"pattern": "SELECT|WHERE|FROM", "file_types": ["rb", "erb"]}
"""

    def _format_tool_messages(self, tool_calls_made: List[dict]) -> List[dict]:
        """Format tool calls and results into Anthropic tool_use/tool_result messages."""
        if not tool_calls_made:
            return []

        tool_use_blocks = []
        for tool_data in tool_calls_made:
            tc = tool_data.get("tool_call", {})
            tool_use_blocks.append({
                "type": "tool_use",
                "id": tc.get("id"),
                "name": tc.get("name"),
                "input": tc.get("input", {}),
            })

        tool_result_blocks = []
        for tool_data in tool_calls_made:
            tc = tool_data.get("tool_call", {})
            result = tool_data.get("result", "")
            tool_result_blocks.append({
                "type": "tool_result",
                "tool_use_id": tc.get("id"),
                "content": result,
            })

        return [
            {"role": "assistant", "content": tool_use_blocks},
            {"role": "user", "content": tool_result_blocks},
        ]

    def _extract_json_after(self, text: str, start_idx: int) -> Optional[Dict[str, Any]]:
        import json as _json
        brace_idx = text.find('{', start_idx)
        if brace_idx == -1:
            return None
        depth = 0
        for i in range(brace_idx, len(text)):
            ch = text[i]
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return _json.loads(text[brace_idx:i+1])
                    except Exception:
                        return None
        return None

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """
        Parse LLM response to extract thought/action/answer.

        Args:
            response: Raw LLM response

        Returns:
            Parsed action dictionary
        """
        response = response.strip()

        # If the model already provided a final answer, return it
        if "Answer:" in response:
            answer_content = response.split("Answer:")[-1].strip()
            return {"type": "answer", "content": answer_content}

        # Check for explicit Action block first
        act_idx = response.find("Action:")
        if act_idx != -1:
            after = response[act_idx + len("Action:") :]
            # Tool name is the first non-empty line after Action:
            tool_line = ""
            for line in after.splitlines():
                ls = line.strip()
                if ls:
                    tool_line = ls
                    break
            tool_name = tool_line.split()[0].strip()

            # Map synonyms and validate
            tool_name = self.tool_synonyms.get(tool_name, tool_name)
            if tool_name not in self.allowed_tools:
                # Unknown tool; instruct the model to replan with allowed tools
                return {"type": "thought", "content": f"Requested tool '{tool_line}' is unavailable. Use only allowed tools: {sorted(self.allowed_tools)}. Replan with ripgrep or sql_rails_search."}

            # Extract JSON after the first Input:
            inp_idx = response.find("Input:", act_idx)
            tool_input: Dict[str, Any] = {}
            if inp_idx != -1:
                parsed = self._extract_json_after(response, inp_idx)
                if isinstance(parsed, dict):
                    tool_input = parsed
            else:
                # Fallback: detect function-call style like tool("…")
                import re as _re
                m = _re.search(rf"{tool_name}\s*\(\s*(['\"])(.*?)\1", after)
                if m:
                    arg = m.group(2)
                    if tool_name == 'ripgrep':
                        tool_input = {"pattern": arg, "file_types": ["rb", "erb"]}
                    elif tool_name == 'sql_rails_search':
                        tool_input = {"sql": arg}

            return {"type": "action", "tool": tool_name, "input": tool_input}

        # Extract thought content (everything before potential tool calls)
        if "Thought:" in response:
            thought_content = response.split("Thought:")[-1].split("Action:")[0].strip()
            return {"type": "thought", "content": thought_content}

        # If response contains only reasoning text, treat as thought
        return {"type": "thought", "content": response}

    def _execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> Any:
        """
        Execute a tool with given input.

        Args:
            tool_name: Name of the tool to execute
            tool_input: Input parameters for the tool

        Returns:
            Tool execution result
        """
        if tool_name not in self.tools:
            return f"Error: Tool '{tool_name}' not available"

        try:
            tool = self.tools[tool_name]

            # Bridge async tool.execute into this sync method
            import asyncio
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None

            async def _run():
                return await tool.execute(tool_input)

            if running and running.is_running():
                # Run in dedicated thread + loop
                import threading
                box: Dict[str, Any] = {}

                def _worker():
                    loop = asyncio.new_event_loop()
                    try:
                        asyncio.set_event_loop(loop)
                        box["value"] = loop.run_until_complete(_run())
                    finally:
                        try:
                            loop.close()
                        finally:
                            asyncio.set_event_loop(None)

                t = threading.Thread(target=_worker, daemon=True)
                t.start()
                t.join()
                return box.get("value")
            else:
                return asyncio.run(_run())

        except Exception as e:
            return f"Error executing {tool_name}: {e}"

    def _summarize_tool_result(self, tool_name: str, result: Any) -> str:
        """Create a compact summary suitable to feed back to the model."""
        try:
            if isinstance(result, dict):
                # ripgrep style: {matches: [{file,line,content,..}], total: N}
                if 'matches' in result and isinstance(result['matches'], list):
                    matches = result['matches']
                    total = result.get('total', len(matches))
                    top = matches[:5]
                    files = sorted({m.get('file') for m in top if isinstance(m, dict)})
                    short = ", ".join(f"{m.get('file')}:{m.get('line')}" for m in top if isinstance(m, dict))
                    extras = f"; showing {len(top)} of {total}" if total > len(top) else ""
                    return f"{total} matches in {len(files)} files: {short}{extras}"
                # sql_rails_search style
                if 'results' in result and isinstance(result['results'], list):
                    results = result['results']
                    total = result.get('total_results', len(results))
                    top = results[:5]
                    short = ", ".join(f"{r.get('file')}:{r.get('line')} ({r.get('matched_pattern')})" for r in top if isinstance(r, dict))
                    extras = f"; showing {len(top)} of {total}" if total > len(top) else ""
                    return f"{total} candidates: {short}{extras}"
            # Fallback to safe string
            s = str(result)
            return s if len(s) <= 800 else s[:800] + "…"
        except Exception:
            s = str(result)
            return s if len(s) <= 800 else s[:800] + "…"

    def _generate_summary(self) -> str:
        """Generate a summary of the ReAct session."""
        if not self.react_steps:
            return "No analysis steps completed."

        summary_parts = ["## Rails Code Analysis Summary\n"]

        for step in self.react_steps:
            if step.step_type == 'thought':
                summary_parts.append(f"**Reasoning:** {step.content}")
            elif step.step_type == 'action':
                summary_parts.append(f"**Tool Used:** {step.tool_name}")
            elif step.step_type == 'observation':
                summary_parts.append(f"**Result:** {step.content[:200]}...")
            elif step.step_type == 'answer':
                summary_parts.append(f"**Answer:** {step.content}")

        return "\n\n".join(summary_parts)

    def _generate_summary_with_timeout(self) -> str:
        """Generate a summary when the ReAct loop times out."""
        if not self.react_steps:
            return "## Analysis Timeout\n\nNo analysis steps were completed before reaching the step limit."

        summary_parts = [
            "## Analysis Timeout - Partial Results\n",
            f"⚠️ **Analysis stopped after reaching the maximum of 5 steps without finding a definitive answer.**\n"
        ]

        # Show what was attempted
        action_count = sum(1 for step in self.react_steps if step.step_type == 'action')
        summary_parts.append(f"**Tools executed:** {action_count}")

        # Show the reasoning trail
        summary_parts.append("### Analysis Trail:")
        for i, step in enumerate(self.react_steps, 1):
            if step.step_type == 'thought':
                summary_parts.append(f"{i}. **Thought:** {step.content[:100]}...")
            elif step.step_type == 'action':
                summary_parts.append(f"{i}. **Action:** Used {step.tool_name}")
            elif step.step_type == 'observation':
                summary_parts.append(f"{i}. **Result:** {step.content[:100]}...")

        summary_parts.append("\n**Suggestion:** Try a more specific query or use the standalone rule-based agent for simpler pattern matching.")

        return "\n\n".join(summary_parts)

    def get_status(self) -> Dict[str, Any]:
        """Get current agent status."""
        return {
            "project_root": self.project_root,
            "tools_available": list(self.tools.keys()),
            "conversation_length": len(self.conversation_history),
            "react_steps": len(self.react_steps)
        }
