"""
Custom Finder Method Detector - Auto-detects Rails custom finder methods.

Analyzes model files to identify custom instance methods that return ActiveRecord relations,
eliminating the need for hardcoded naming patterns (find_*, get_*, all_*).

Used by WhereClauseParser to generalize custom finder method parsing across different Rails projects.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Optional, Set
from dataclasses import dataclass


@dataclass
class MethodInfo:
    """Information about a detected custom finder method."""
    name: str
    body: str
    returns_relation: bool  # True if method returns ActiveRecord relation
    file_path: str


class CustomFinderDetector:
    """
    Detects custom finder methods in Rails models by analyzing method bodies.

    Auto-detects methods that return ActiveRecord relations without relying on
    naming conventions like find_*, get_*, all_*.
    """

    # Standard ActiveRecord methods that should NOT be treated as custom finders
    STANDARD_AR_METHODS = {
        # Query methods
        'where', 'not', 'order', 'limit', 'offset', 'select', 'joins', 'includes',
        'group', 'having', 'distinct', 'readonly', 'lock', 'references', 'eager_load',
        'preload', 'from', 'unscope', 'only', 'except', 'extending',
        # Finder methods
        'find', 'find_by', 'find_by!', 'find_or_create_by', 'find_or_initialize_by',
        'all', 'first', 'first!', 'last', 'last!', 'take', 'take!',
        # Existence checks
        'exists?', 'any?', 'many?', 'none?', 'one?',
        # Calculations
        'count', 'sum', 'average', 'minimum', 'maximum', 'calculate',
        # Pluck methods
        'pluck', 'ids', 'pick',
        # CRUD
        'create', 'create!', 'new', 'build',
        'update', 'update!', 'update_all', 'update_column', 'update_columns',
        'destroy', 'destroy!', 'destroy_all', 'delete', 'delete_all',
        # Batch processing
        'find_each', 'find_in_batches', 'in_batches',
        # Scopes (these are method calls, not custom methods)
        'scope', 'default_scope',
    }

    # Patterns that indicate a method returns an ActiveRecord relation
    RELATION_INDICATORS = [
        # Direct Model queries
        r'\b[A-Z]\w+\.\s*(?:where|joins|includes|select|order|limit|offset|group|having|distinct)',
        # Association chains
        r'\b\w+\.\s*(?:where|joins|includes|select|order|limit|offset|group|having|distinct)',
        # Scope calls on models
        r'\b[A-Z]\w+\.\w+\.',  # e.g., Member.active.where
        # Association references followed by query
        r'(?:members|posts|users|items|orders|tasks)\s*\.\s*\w+',
    ]

    def __init__(self, project_root: Optional[str] = None, debug: bool = False):
        """
        Initialize detector with Rails project root.

        Args:
            project_root: Path to Rails project root (enables model scanning)
            debug: Enable debug output
        """
        self.project_root = Path(project_root) if project_root else None
        self.debug = debug
        self._method_cache: Dict[str, Dict[str, MethodInfo]] = {}  # model_name -> {method_name -> MethodInfo}

    def get_method_body(self, model_name: str, method_name: str) -> Optional[str]:
        """
        Get method body for a custom finder method.

        Args:
            model_name: Model class name (e.g., "Company", "Member")
            method_name: Method name (e.g., "find_all_active", "fetch_published")

        Returns:
            Method body as string, or None if not found or not a custom finder
        """
        if not self.project_root:
            return None

        # Normalize model name to lowercase for file lookup
        model_file_name = model_name.lower()

        # Check cache first
        if model_name in self._method_cache:
            methods = self._method_cache[model_name]
            if method_name in methods:
                method_info = methods[method_name]
                if method_info.returns_relation:
                    return method_info.body
                else:
                    return None  # Found but doesn't return relation

        # Analyze model file
        model_file = self.project_root / "app" / "models" / f"{model_file_name}.rb"
        if not model_file.exists():
            return None

        methods = self.analyze_model(str(model_file))

        # Cache results
        self._method_cache[model_name] = methods

        # Return method body if it's a custom finder
        if method_name in methods:
            method_info = methods[method_name]
            if method_info.returns_relation:
                return method_info.body

        return None

    def analyze_model(self, model_file_path: str) -> Dict[str, MethodInfo]:
        """
        Analyze a model file to extract all instance methods and detect custom finders.

        Args:
            model_file_path: Absolute path to model file

        Returns:
            Dictionary mapping method names to MethodInfo objects
        """
        try:
            with open(model_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            if self.debug:
                print(f"Error reading {model_file_path}: {e}")
            return {}

        methods = self._extract_instance_methods(content)

        # Analyze each method to determine if it returns a relation
        method_infos = {}
        for name, body in methods.items():
            # Skip standard ActiveRecord methods
            if name in self.STANDARD_AR_METHODS:
                continue

            is_finder = self._is_custom_finder_method(body)

            method_infos[name] = MethodInfo(
                name=name,
                body=body,
                returns_relation=is_finder,
                file_path=model_file_path
            )

            if self.debug and is_finder:
                print(f"Detected custom finder: {name}")

        return method_infos

    def _extract_instance_methods(self, file_content: str) -> Dict[str, str]:
        """
        Extract all instance method definitions from Ruby file.

        Args:
            file_content: Ruby file content as string

        Returns:
            Dictionary mapping method names to method bodies
        """
        methods = {}

        # Pattern to match method definitions
        # Matches: def method_name ... end
        # Handles optional parameters: def method_name(arg1, arg2) ... end
        method_pattern = re.compile(
            r'^\s*def\s+(\w+)\s*(?:\(.*?\))?\s*\n(.*?)^\s*end',
            re.MULTILINE | re.DOTALL
        )

        for match in method_pattern.finditer(file_content):
            method_name = match.group(1)
            method_body = match.group(2).strip()

            # Skip private/protected methods (basic check)
            # A more sophisticated parser would track visibility modifiers
            if method_name.startswith('_'):
                continue

            methods[method_name] = method_body

        return methods

    def _is_custom_finder_method(self, method_body: str) -> bool:
        """
        Determine if a method body returns an ActiveRecord relation.

        Detection heuristics:
        1. Contains ActiveRecord query methods (where, joins, includes, etc.)
        2. Contains scope chains (Model.active, model.published, etc.)
        3. Contains association chains (members., posts., etc.)
        4. Returns a variable assigned from a query

        Excludes:
        - Calculation methods (sum, count, average, etc.) - these return values, not relations
        - Methods ending with terminal operations

        Args:
            method_body: Method body as string

        Returns:
            True if method likely returns an ActiveRecord relation
        """
        # Terminal methods that return values, not relations
        terminal_methods = r'\b(?:sum|count|average|minimum|maximum|calculate|pluck|ids|pick|exists?|any?|many?|none?|one?)\b'

        # Check last line (implicit return in Ruby)
        lines = [line.strip() for line in method_body.split('\n')
                 if line.strip() and not line.strip().startswith('#')]

        if lines:
            last_line = lines[-1]

            # EXCLUDE: If last line ends with a terminal/calculation method
            # Examples: members.sum(:revenue), members.count, posts.average(:rating)
            if re.search(terminal_methods, last_line, re.IGNORECASE):
                return False

        # Check for explicit query patterns
        for pattern in self.RELATION_INDICATORS:
            if re.search(pattern, method_body, re.IGNORECASE):
                return True

        # Check for explicit return of scope chain
        # Pattern: return <something>.<scope_or_query>
        if re.search(r'\breturn\s+\w+\.\w+', method_body):
            return True

        if lines:
            last_line = lines[-1]

            # Last line contains scope/query method call
            if re.search(r'\.\s*(?:where|joins|includes|select|order|limit|offset|group|having|distinct)', last_line):
                return True

            # Last line is a chained method call (likely scope)
            # But make sure it's not a simple method call on a string/value
            if re.search(r'\w+\.\w+\.\w+', last_line):
                return True

        return False


# Singleton instance for global access (lazy initialization)
_detector_instance: Optional[CustomFinderDetector] = None


def get_detector(project_root: Optional[str] = None, debug: bool = False) -> CustomFinderDetector:
    """
    Get or create singleton CustomFinderDetector instance.

    Args:
        project_root: Path to Rails project root
        debug: Enable debug output

    Returns:
        CustomFinderDetector instance
    """
    global _detector_instance

    if _detector_instance is None:
        _detector_instance = CustomFinderDetector(project_root=project_root, debug=debug)
    elif project_root and _detector_instance.project_root != Path(project_root):
        # Project root changed, create new instance
        _detector_instance = CustomFinderDetector(project_root=project_root, debug=debug)

    return _detector_instance
