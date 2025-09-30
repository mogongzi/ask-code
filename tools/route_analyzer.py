"""
Route analyzer tool for examining Rails routes and routing configuration.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_tool import BaseTool


class RouteAnalyzer(BaseTool):
    """Tool for analyzing Rails routes and routing configuration."""

    @property
    def name(self) -> str:
        return "route_analyzer"

    @property
    def description(self) -> str:
        return "Analyze Rails routes.rb file and routing configuration to understand URL patterns and controller mappings."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "focus": {
                    "type": "string",
                    "description": "Specific aspect to focus on: 'resources', 'namespaces', 'custom', or 'all'",
                    "default": "all"
                },
                "controller": {
                    "type": "string",
                    "description": "Filter routes for specific controller (optional)"
                }
            },
            "required": []
        }

    def execute(self, input_params: Dict[str, Any]) -> Any:
        """
        Analyze Rails routes configuration.

        Args:
            input_params: Route analysis parameters

        Returns:
            Route analysis results
        """
        if not self.validate_input(input_params):
            return {"error": "Invalid input parameters"}

        if not self.project_root or not Path(self.project_root).exists():
            return {"error": "Project root not found"}

        focus = input_params.get("focus", "all")
        controller_filter = input_params.get("controller")

        # Find routes file
        routes_file = Path(self.project_root) / "config" / "routes.rb"
        if not routes_file.exists():
            return {"error": f"Routes file not found: {routes_file}"}

        try:
            content = routes_file.read_text(encoding='utf-8')
            analysis = self._analyze_routes_content(content, focus, controller_filter)

            analysis["file_path"] = str(routes_file.relative_to(self.project_root))

            return analysis

        except Exception as e:
            return {"error": f"Error analyzing routes: {e}"}

    def _analyze_routes_content(self, content: str, focus: str, controller_filter: Optional[str]) -> Dict[str, Any]:
        """
        Analyze routes file content.

        Args:
            content: Routes file content
            focus: Analysis focus area
            controller_filter: Filter for specific controller

        Returns:
            Analysis results
        """
        lines = content.split('\n')
        analysis = {
            "resources": [],
            "namespaces": [],
            "custom_routes": [],
            "root_route": None
        }

        for i, line in enumerate(lines, 1):
            line_stripped = line.strip()

            if not line_stripped or line_stripped.startswith('#'):
                continue

            # Focus-specific analysis
            if focus in ["all", "resources"]:
                resource = self._extract_resource(line_stripped, i)
                if resource:
                    analysis["resources"].append(resource)

            if focus in ["all", "namespaces"]:
                namespace = self._extract_namespace(line_stripped, i)
                if namespace:
                    analysis["namespaces"].append(namespace)

            if focus in ["all", "custom"]:
                custom_route = self._extract_custom_route(line_stripped, i)
                if custom_route:
                    analysis["custom_routes"].append(custom_route)

            # Root route
            if "root" in line_stripped and "=>" in line_stripped:
                analysis["root_route"] = {
                    "line": i,
                    "content": line_stripped
                }

        # Filter by controller if specified
        if controller_filter:
            analysis = self._filter_by_controller(analysis, controller_filter)

        return analysis

    def _extract_resource(self, line: str, line_number: int) -> Optional[Dict[str, Any]]:
        """Extract resource route from line."""
        resource_patterns = [
            r'resources?\s+:(\\w+)',
            r'resources?\s+["\'](\w+)["\']'
        ]

        for pattern in resource_patterns:
            match = re.search(pattern, line)
            if match:
                resource_name = match.group(1)
                route_type = "resources" if line.strip().startswith("resources") else "resource"

                return {
                    "line": line_number,
                    "content": line,
                    "type": route_type,
                    "name": resource_name,
                    "controller": f"{resource_name}_controller"
                }
        return None

    def _extract_namespace(self, line: str, line_number: int) -> Optional[Dict[str, Any]]:
        """Extract namespace from line."""
        namespace_patterns = [
            r'namespace\s+:(\\w+)',
            r'namespace\s+["\'](\w+)["\']'
        ]

        for pattern in namespace_patterns:
            match = re.search(pattern, line)
            if match:
                return {
                    "line": line_number,
                    "content": line,
                    "name": match.group(1)
                }
        return None

    def _extract_custom_route(self, line: str, line_number: int) -> Optional[Dict[str, Any]]:
        """Extract custom route from line."""
        custom_patterns = [
            r'(get|post|put|patch|delete)\s+["\']([^"\']+)["\'].*=>\s*["\']?([^"\'\\s,]+)',
            r'(match)\s+["\']([^"\']+)["\'].*=>\s*["\']?([^"\'\\s,]+)'
        ]

        for pattern in custom_patterns:
            match = re.search(pattern, line)
            if match:
                return {
                    "line": line_number,
                    "content": line,
                    "method": match.group(1),
                    "path": match.group(2),
                    "target": match.group(3)
                }
        return None

    def _filter_by_controller(self, analysis: Dict[str, Any], controller_filter: str) -> Dict[str, Any]:
        """Filter analysis results by controller."""
        filtered = {
            "resources": [],
            "namespaces": analysis["namespaces"],  # Keep all namespaces
            "custom_routes": [],
            "root_route": analysis["root_route"]
        }

        # Filter resources
        for resource in analysis["resources"]:
            if controller_filter.lower() in resource.get("controller", "").lower():
                filtered["resources"].append(resource)

        # Filter custom routes
        for route in analysis["custom_routes"]:
            if controller_filter.lower() in route.get("target", "").lower():
                filtered["custom_routes"].append(route)

        return filtered

    def validate_input(self, input_params: Dict[str, Any]) -> bool:
        """Validate route analyzer input parameters."""
        if not super().validate_input(input_params):
            return False

        focus = input_params.get("focus", "all")
        valid_focus = ["all", "resources", "namespaces", "custom"]
        if focus not in valid_focus:
            return False

        return True