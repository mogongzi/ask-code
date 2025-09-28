"""
Controller analyzer tool for examining Rails controller structure and actions.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_tool import BaseTool


class ControllerAnalyzer(BaseTool):
    """Tool for analyzing Rails controller files."""

    @property
    def name(self) -> str:
        return "controller_analyzer"

    @property
    def description(self) -> str:
        return "Analyze Rails controller files to extract actions, filters, and method definitions."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "controller_name": {
                    "type": "string",
                    "description": "Name of the controller to analyze (e.g., 'Users', 'Products', 'Application')"
                },
                "action": {
                    "type": "string",
                    "description": "Specific action to focus on, or 'all' for all actions",
                    "default": "all"
                }
            },
            "required": ["controller_name"]
        }

    def execute(self, input_params: Dict[str, Any]) -> Any:
        """
        Analyze a Rails controller file.

        Args:
            input_params: Controller analysis parameters

        Returns:
            Controller analysis results
        """
        self._debug_input(input_params)

        if not self.validate_input(input_params):
            error_result = {"error": "Invalid input parameters"}
            self._debug_output(error_result)
            return error_result

        if not self.project_root or not Path(self.project_root).exists():
            error_result = {"error": "Project root not found"}
            self._debug_output(error_result)
            return error_result

        controller_name = input_params.get("controller_name", "")
        action = input_params.get("action", "all")

        self._debug_log("🎮 Controller analysis", {
            "controller_name": controller_name,
            "action": action
        })

        # Find controller file
        controller_file = Path(self.project_root) / "app" / "controllers" / f"{controller_name.lower()}_controller.rb"
        if not controller_file.exists():
            return f"Error: Controller file not found: {controller_file}"

        try:
            content = controller_file.read_text(encoding='utf-8')
            analysis = self._analyze_controller_content(content, action)

            analysis["controller_name"] = controller_name
            analysis["file_path"] = str(controller_file.relative_to(self.project_root))

            self._debug_output(analysis)
            return analysis

        except Exception as e:
            error_result = {"error": f"Error analyzing controller {controller_name}: {e}"}
            self._debug_output(error_result)
            return error_result

    def _analyze_controller_content(self, content: str, action_filter: str) -> Dict[str, Any]:
        """
        Analyze controller file content.

        Args:
            content: Controller file content
            action_filter: Specific action to analyze or 'all'

        Returns:
            Analysis results
        """
        lines = content.split('\n')
        analysis = {
            "actions": [],
            "filters": [],
            "private_methods": [],
            "protected_methods": [],
            "concerns": [],
            "class_definition": None
        }

        current_method = None
        method_content = []
        in_private = False
        in_protected = False

        for i, line in enumerate(lines, 1):
            line_stripped = line.strip()

            if not line_stripped or line_stripped.startswith('#'):
                continue

            # Track visibility sections
            if line_stripped == 'private':
                in_private = True
                in_protected = False
                continue
            elif line_stripped == 'protected':
                in_protected = True
                in_private = False
                continue
            elif line_stripped.startswith('def '):
                # Reset visibility when encountering a new method
                pass

            # Class definition
            if line_stripped.startswith('class ') and 'Controller' in line_stripped:
                analysis["class_definition"] = {
                    "line": i,
                    "content": line_stripped
                }

            # Filters
            filter_match = self._extract_filter(line_stripped, i)
            if filter_match:
                analysis["filters"].append(filter_match)

            # Concerns/includes
            if line_stripped.startswith('include '):
                analysis["concerns"].append({
                    "line": i,
                    "content": line_stripped,
                    "concern": line_stripped.replace('include ', '')
                })

            # Method definitions
            method_match = self._extract_method(line_stripped, i)
            if method_match:
                # Finish previous method
                if current_method:
                    current_method["content"] = method_content
                    self._categorize_method(current_method, analysis, in_private, in_protected)

                # Start new method
                current_method = method_match
                method_content = [line_stripped]
            elif current_method:
                # Add line to current method
                method_content.append(line_stripped)

        # Finish last method
        if current_method:
            current_method["content"] = method_content
            self._categorize_method(current_method, analysis, in_private, in_protected)

        # Filter by specific action if requested
        if action_filter != "all":
            analysis["actions"] = [
                action for action in analysis["actions"]
                if action["name"] == action_filter
            ]

        return analysis

    def _extract_filter(self, line: str, line_number: int) -> Optional[Dict[str, Any]]:
        """Extract filter from line."""
        filter_patterns = [
            r'(before_action|after_action|around_action)\s+:(\w+)',
            r'(before_filter|after_filter|around_filter)\s+:(\w+)'
        ]

        for pattern in filter_patterns:
            match = re.search(pattern, line)
            if match:
                return {
                    "line": line_number,
                    "content": line,
                    "type": match.group(1),
                    "method": match.group(2)
                }
        return None

    def _extract_method(self, line: str, line_number: int) -> Optional[Dict[str, Any]]:
        """Extract method definition from line."""
        method_pattern = r'def\s+(\w+)'
        match = re.search(method_pattern, line)

        if match:
            method_name = match.group(1)

            return {
                "line": line_number,
                "name": method_name,
                "definition": line
            }
        return None

    def _categorize_method(self, method: Dict[str, Any], analysis: Dict[str, Any],
                          in_private: bool, in_protected: bool) -> None:
        """Categorize method based on visibility and Rails conventions."""
        method_name = method["name"]

        # Standard Rails actions
        rails_actions = [
            "index", "show", "new", "create", "edit", "update", "destroy"
        ]

        if in_private:
            analysis["private_methods"].append(method)
        elif in_protected:
            analysis["protected_methods"].append(method)
        elif method_name in rails_actions or not method_name.startswith('_'):
            # Public method - likely an action
            analysis["actions"].append(method)
        else:
            # Other public methods
            analysis["actions"].append(method)

    def validate_input(self, input_params: Dict[str, Any]) -> bool:
        """Validate controller analyzer input parameters."""
        if not super().validate_input(input_params):
            return False

        controller_name = input_params.get("controller_name")
        if not controller_name or not isinstance(controller_name, str):
            return False

        return True