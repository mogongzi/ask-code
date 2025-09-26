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

    async def execute(self, input_params: Dict[str, Any]) -> Any:
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

        # Find model file
        model_file = Path(self.project_root) / "app" / "models" / f"{model_name.lower()}.rb"
        if not model_file.exists():
            return f"Error: Model file not found: {model_file}"

        try:
            content = model_file.read_text(encoding='utf-8')
            analysis = self._analyze_model_content(content, focus)

            analysis["model_name"] = model_name
            analysis["file_path"] = str(model_file.relative_to(self.project_root))

            self._debug_output(analysis)
            return analysis

        except Exception as e:
            error_result = {"error": f"Error analyzing model {model_name}: {e}"}
            self._debug_output(error_result)
            return error_result

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
        """Extract method definition from line."""
        method_pattern = r'def\s+(\w+)'
        match = re.search(method_pattern, line)

        if match:
            method_name = match.group(1)
            is_class_method = line.strip().startswith('def self.')

            return {
                "line": line_number,
                "content": line,
                "name": method_name,
                "type": "class_method" if is_class_method else "instance_method"
            }
        return None

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