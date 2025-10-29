"""
Tool registry for managing Rails agent tools.

This module provides centralized tool management with lifecycle control,
schema generation, and error handling.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass

from tools.base_tool import BaseTool
from tools.ripgrep_tool import RipgrepTool
from tools.sql_rails_search import SQLRailsSearch
from tools.ast_grep_tool import AstGrepTool
from tools.model_analyzer import ModelAnalyzer
from tools.controller_analyzer import ControllerAnalyzer
from tools.route_analyzer import RouteAnalyzer
from tools.migration_analyzer import MigrationAnalyzer
from tools.file_reader_tool import FileReaderTool


logger = logging.getLogger(__name__)


@dataclass
class ToolInitializationError:
    """Represents a tool initialization failure."""
    name: str
    error: str
    exception_type: str


class ToolRegistry:
    """
    Registry for managing Rails agent tools.

    Provides centralized tool management with lifecycle control,
    schema generation, and graceful error handling.
    """

    # Core tool definitions with their classes
    CORE_TOOLS = {
        'ripgrep': RipgrepTool,
        'sql_rails_search': SQLRailsSearch,  # Unified SQL search with intelligent routing
        'ast_grep': AstGrepTool,
        'model_analyzer': ModelAnalyzer,
        'controller_analyzer': ControllerAnalyzer,
        'route_analyzer': RouteAnalyzer,
        'migration_analyzer': MigrationAnalyzer,
        'file_reader': FileReaderTool,
    }

    # Tool synonyms for user-friendly names
    TOOL_SYNONYMS = {
        'search_code_semantic': 'ripgrep',
        'search_codebase': 'ripgrep',
        'code_search': 'ripgrep',
        'grep': 'ripgrep',
        # SQL search tool synonyms
        'sql_search': 'sql_rails_search',
        'trace_sql': 'sql_rails_search',
        'find_sql_source': 'sql_rails_search',
        'find_sql': 'sql_rails_search',
        'sql_to_rails': 'sql_rails_search',
        # Other tool synonyms
        'astgrep': 'ast_grep',
        'read_file': 'file_reader',
        'show_file': 'file_reader',
        'cat': 'file_reader',
    }

    def __init__(self, project_root: Optional[str] = None, debug: bool = False):
        """
        Initialize the tool registry.

        Args:
            project_root: Root directory of the Rails project
            debug: Enable debug mode for tools
        """
        self.project_root = project_root
        self.debug = debug
        self.tools: Dict[str, BaseTool] = {}
        self.initialization_errors: List[ToolInitializationError] = []
        self.allowed_tools: Set[str] = set(self.CORE_TOOLS.keys())

        self._initialize_tools()

    def _initialize_tools(self) -> None:
        """Initialize all available tools with defensive error handling."""
        self.tools.clear()
        self.initialization_errors.clear()

        for tool_name, tool_class in self.CORE_TOOLS.items():
            try:
                logger.debug(f"Initializing tool: {tool_name}")
                self.tools[tool_name] = tool_class(self.project_root, debug=self.debug)
                logger.debug(f"Successfully initialized tool: {tool_name}")
            except Exception as e:
                error = ToolInitializationError(
                    name=tool_name,
                    error=str(e),
                    exception_type=type(e).__name__
                )
                self.initialization_errors.append(error)
                logger.warning(f"Failed to initialize tool {tool_name}: {e}")

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """
        Get a tool by name, supporting synonyms.

        Args:
            name: Tool name or synonym

        Returns:
            Tool instance or None if not found
        """
        # Resolve synonym to actual tool name
        actual_name = self.TOOL_SYNONYMS.get(name, name)
        return self.tools.get(actual_name)

    def has_tool(self, name: str) -> bool:
        """
        Check if a tool is available.

        Args:
            name: Tool name or synonym

        Returns:
            True if tool is available, False otherwise
        """
        return self.get_tool(name) is not None

    def get_available_tools(self) -> Dict[str, BaseTool]:
        """Get all successfully initialized tools."""
        return self.tools.copy()

    def get_tool_names(self) -> List[str]:
        """Get list of available tool names."""
        return list(self.tools.keys())

    def get_failed_tools(self) -> List[ToolInitializationError]:
        """Get list of tools that failed to initialize."""
        return self.initialization_errors.copy()

    def build_tool_schemas(self) -> List[Dict[str, Any]]:
        """
        Build tool schemas dynamically from available tools.

        Returns:
            List of tool schemas for LLM function calling
        """
        schemas = []
        for name, tool in self.tools.items():
            try:
                schema = {
                    "name": getattr(tool, 'name', name),
                    "description": getattr(tool, 'description', f"Tool {name}"),
                    "input_schema": getattr(
                        tool,
                        'parameters',
                        {"type": "object", "properties": {}, "required": []}
                    ),
                }
                schemas.append(schema)
                logger.debug(f"Built schema for tool: {name}")
            except Exception as e:
                logger.warning(f"Failed to build schema for tool {name}: {e}")
                continue
        return schemas

    def refresh(self, new_project_root: Optional[str] = None) -> None:
        """
        Refresh the tool registry with a new project root.

        Args:
            new_project_root: New project root directory
        """
        if new_project_root is not None:
            self.project_root = new_project_root

        logger.info(f"Refreshing tool registry with project root: {self.project_root}")
        self._initialize_tools()

    def get_status_summary(self) -> Dict[str, Any]:
        """
        Get a summary of registry status.

        Returns:
            Dictionary with registry status information
        """
        return {
            "project_root": self.project_root,
            "tools_available": list(self.tools.keys()),
            "tools_failed": [error.name for error in self.initialization_errors],
            "total_tools": len(self.CORE_TOOLS),
            "successful_tools": len(self.tools),
            "failed_tools": len(self.initialization_errors),
        }

    def print_initialization_summary(self, console) -> None:
        """
        Print a summary of tool initialization to console.

        Args:
            console: Rich console instance for printing
        """
        if self.initialization_errors:
            failed_list = ", ".join(
                f"{err.name} ({err.error})"
                for err in self.initialization_errors[:3]
            )
            more = f" … +{len(self.initialization_errors)-3} more" if len(self.initialization_errors) > 3 else ""
            console.print(f"[yellow]Some tools failed to initialize:[/yellow] {failed_list}{more}")

        console.print(f"[green]Successfully initialized {len(self.tools)} tools[/green]")

    def validate_tool_name(self, name: str) -> bool:
        """
        Validate if a tool name is allowed.

        Args:
            name: Tool name to validate

        Returns:
            True if tool name is valid, False otherwise
        """
        actual_name = self.TOOL_SYNONYMS.get(name, name)
        return actual_name in self.allowed_tools

    def get_unused_tools(self, used_tools: Set[str]) -> List[str]:
        """
        Get list of tools that haven't been used yet.

        Args:
            used_tools: Set of tool names that have been used

        Returns:
            List of unused tool names
        """
        available = set(self.tools.keys())
        unused = sorted(available - used_tools)
        return unused
