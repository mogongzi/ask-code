"""
Model analyzer tool for examining Rails model structure and relationships.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_tool import BaseTool


class ModelAnalyzer(BaseTool):
    """Tool for analyzing Rails model files."""

    @property
    def name(self) -> str:
        return "model_analyzer"

    @property
    def description(self) -> str:
        return "Analyze Rails model files to extract validations, associations, callbacks, and methods."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "model_name": {
                    "type": "string",
                    "description": "Name of the model to analyze (e.g., 'User', 'Product')"
                },
                "focus": {
                    "type": "string",
                    "description": "Specific aspect to focus on: 'validations', 'associations', 'callbacks', 'methods', or 'all'",
                    "default": "all"
                }
            },
            "required": ["model_name"]
        }

    def execute(self, input_params: Dict[str, Any]) -> Any:
        """
        Analyze a Rails model file.

        Args:
            input_params: Model analysis parameters

        Returns:
            Model analysis results
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

        model_name = input_params.get("model_name", "")
        focus = input_params.get("focus", "all")

        self._debug_log("📊 Model analysis", {
            "model_name": model_name,
            "focus": focus
        })

        # Find model file - convert PascalCase to snake_case
        file_name = self._model_name_to_file_name(model_name)
        model_file = Path(self.project_root) / "app" / "models" / f"{file_name}.rb"
        if not model_file.exists():
            error_result = {"error": f"Model file not found: {model_file}"}
            self._debug_output(error_result)
            return error_result

        try:
            content = model_file.read_text(encoding='utf-8')
            analysis = self._analyze_model_content(content, focus)

            analysis["model_name"] = model_name
            analysis["file_path"] = str(model_file.relative_to(self.project_root))

            # Add summary
            analysis["summary"] = self._generate_summary(analysis)

            self._debug_output(analysis)
            return analysis

        except Exception as e:
            error_result = {"error": f"Error analyzing model {model_name}: {e}"}
            self._debug_output(error_result)
            return error_result

    def _model_name_to_file_name(self, model_name: str) -> str:
        """
        Convert PascalCase model name to snake_case file name.

        Examples:
            PageView -> page_view
            User -> user
            APIKey -> api_key
            HTTPRequest -> http_request
        """
        import re
        # Insert underscore between lowercase and uppercase, or between letter and uppercase followed by lowercase
        snake_case = re.sub(r'([a-z\d])([A-Z])', r'\1_\2', model_name)
        snake_case = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', snake_case)
        return snake_case.lower()

    def _analyze_model_content(self, content: str, focus: str) -> Dict[str, Any]:
        """
        Analyze model file content.

        Args:
            content: Model file content
            focus: Analysis focus area

        Returns:
            Analysis results
        """
        lines = content.split('\n')
        analysis = {
            "validations": [],
            "associations": [],
            "callbacks": [],
            "methods": [],
            "concerns": [],
            "class_definition": None
        }

        for i, line in enumerate(lines, 1):
            line_stripped = line.strip()

            if not line_stripped or line_stripped.startswith('#'):
                continue

            # Class definition
            if line_stripped.startswith('class ') and '<' in line_stripped:
                analysis["class_definition"] = {
                    "line": i,
                    "content": line_stripped
                }

            # Focus-specific analysis
            if focus in ["all", "validations"]:
                validation = self._extract_validation(line_stripped, i)
                if validation:
                    analysis["validations"].append(validation)

            if focus in ["all", "associations"]:
                association = self._extract_association(line_stripped, i)
                if association:
                    analysis["associations"].append(association)

            if focus in ["all", "callbacks"]:
                callback = self._extract_callback(line_stripped, i)
                if callback:
                    analysis["callbacks"].append(callback)

            if focus in ["all", "methods"]:
                method = self._extract_method(line_stripped, i)
                if method:
                    analysis["methods"].append(method)

            # Concerns/includes
            if line_stripped.startswith('include '):
                analysis["concerns"].append({
                    "line": i,
                    "content": line_stripped,
                    "concern": line_stripped.replace('include ', '')
                })

        return analysis

    def _extract_validation(self, line: str, line_number: int) -> Optional[Dict[str, Any]]:
        """Extract validation from line."""
        validation_patterns = [
            r'validates?\s+([^,]+)',
            r'validate\s+:(\w+)'
        ]

        for pattern in validation_patterns:
            match = re.search(pattern, line)
            if match:
                return {
                    "line": line_number,
                    "content": line,
                    "field": match.group(1),
                    "type": "validates" if "validates" in line else "validate"
                }
        return None

    def _extract_association(self, line: str, line_number: int) -> Optional[Dict[str, Any]]:
        """Extract association from line."""
        association_patterns = [
            r'(belongs_to|has_one|has_many|has_and_belongs_to_many)\s+:(\w+)',
        ]

        for pattern in association_patterns:
            match = re.search(pattern, line)
            if match:
                return {
                    "line": line_number,
                    "content": line,
                    "type": match.group(1),
                    "target": match.group(2)
                }
        return None

    def _extract_callback(self, line: str, line_number: int) -> Optional[Dict[str, Any]]:
        """Extract callback from line."""
        callback_patterns = [
            r'(before_|after_|around_)(\w+)\s+:(\w+)',
            r'(before_|after_|around_)(\w+)\s+(.+)'
        ]

        for pattern in callback_patterns:
            match = re.search(pattern, line)
            if match:
                return {
                    "line": line_number,
                    "content": line,
                    "timing": match.group(1).rstrip('_'),
                    "event": match.group(2),
                    "method": match.group(3) if len(match.groups()) >= 3 else None
                }
        return None

    def _extract_method(self, line: str, line_number: int) -> Optional[Dict[str, Any]]:
        """Extract method definition from line (signature only, not full body)."""
        method_pattern = r'def\s+(self\.)?(\w+)(\(.*?\))?'
        match = re.search(method_pattern, line)

        if match:
            is_class_method = bool(match.group(1))
            method_name = match.group(2)
            parameters = match.group(3) or "()"

            return {
                "line": line_number,
                "signature": line,  # Just the 'def ...' line
                "name": method_name,
                "parameters": parameters,
                "type": "class_method" if is_class_method else "instance_method"
            }
        return None

    def _generate_summary(self, analysis: Dict[str, Any]) -> str:
        """Generate concise summary of model analysis."""
        parts = []

        if analysis["associations"]:
            assoc_types = {}
            for a in analysis["associations"]:
                assoc_types.setdefault(a["type"], []).append(a["target"])
            assoc_str = ", ".join([f"{k}: {len(v)}" for k, v in assoc_types.items()])
            parts.append(f"Associations: {assoc_str}")

        if analysis["validations"]:
            parts.append(f"Validations: {len(analysis['validations'])}")

        if analysis["callbacks"]:
            parts.append(f"Callbacks: {len(analysis['callbacks'])}")

        if analysis["methods"]:
            method_count = len(analysis["methods"])
            parts.append(f"Methods: {method_count}")

        return " | ".join(parts) if parts else "Empty model"

    def format_result(self, result: Any) -> str:
        """Format model analysis result - compact summary instead of full JSON."""
        if isinstance(result, str):
            return result  # Error message

        if not isinstance(result, dict):
            return str(result)

        # Build compact text summary
        lines = []
        lines.append(f"## Model: {result.get('model_name', 'Unknown')}")
        lines.append(f"**File**: `{result.get('file_path', 'Unknown')}`\n")

        if result.get("summary"):
            lines.append(f"**Summary**: {result['summary']}\n")

        # Associations
        if result.get("associations"):
            lines.append(f"### Associations ({len(result['associations'])})")
            for assoc in result["associations"][:10]:
                lines.append(f"- Line {assoc['line']}: `{assoc['type']} :{assoc['target']}`")
            if len(result["associations"]) > 10:
                lines.append(f"  ... +{len(result['associations']) - 10} more\n")

        # Validations
        if result.get("validations"):
            lines.append(f"\n### Validations ({len(result['validations'])})")
            for val in result["validations"][:10]:
                lines.append(f"- Line {val['line']}: `{val['type']}` on {val['field']}")
            if len(result["validations"]) > 10:
                lines.append(f"  ... +{len(result['validations']) - 10} more")

        # Callbacks
        if result.get("callbacks"):
            lines.append(f"\n### Callbacks ({len(result['callbacks'])})")
            for cb in result["callbacks"][:10]:
                method = cb.get('method', 'block')
                lines.append(f"- Line {cb['line']}: `{cb['timing']}_{cb['event']}` → {method}")
            if len(result["callbacks"]) > 10:
                lines.append(f"  ... +{len(result['callbacks']) - 10} more")

        # Methods (just names and line numbers)
        if result.get("methods"):
            lines.append(f"\n### Methods ({len(result['methods'])})")
            for method in result["methods"][:10]:
                method_type = "class" if method.get("type") == "class_method" else "instance"
                lines.append(f"- Line {method['line']}: `{method['name']}` ({method_type})")
            if len(result["methods"]) > 10:
                lines.append(f"  ... +{len(result['methods']) - 10} more")

        return "\n".join(lines)

    def validate_input(self, input_params: Dict[str, Any]) -> bool:
        """Validate model analyzer input parameters."""
        if not super().validate_input(input_params):
            return False

        model_name = input_params.get("model_name")
        if not model_name or not isinstance(model_name, str):
            return False

        focus = input_params.get("focus", "all")
        valid_focus = ["all", "validations", "associations", "callbacks", "methods"]
        if focus not in valid_focus:
            return False

        return True