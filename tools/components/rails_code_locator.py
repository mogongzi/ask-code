"""
Rails Code Locator Utility

Centralized logic for locating Rails code (controllers, callbacks, methods).
Eliminates duplication of controller/callback verification logic.
"""
from __future__ import annotations

from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from .code_search_engine import CodeSearchEngine


@dataclass
class ControllerLocation:
    """Location information for a controller action."""
    file: str
    line: int
    controller: str
    action: str
    confidence: str


@dataclass
class CallbackLocation:
    """Location information for a callback declaration."""
    file: str
    line: int
    callback_type: str
    method_name: str
    model_name: str


class RailsCodeLocator:
    """
    Utility for locating Rails code elements (controllers, callbacks, methods).

    Provides caching and consistent search logic for both tools.
    """

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.search_engine = CodeSearchEngine(project_root=project_root)

        # Cache to avoid re-searching same locations
        self._controller_cache: Dict[str, Optional[ControllerLocation]] = {}
        self._callback_cache: Dict[str, Optional[CallbackLocation]] = {}

    def find_controller_action(
        self, controller: str, action: str
    ) -> Optional[ControllerLocation]:
        """
        Find and verify a controller action exists.

        Args:
            controller: Controller name in snake_case (e.g., 'work_pages')
            action: Action method name (e.g., 'show_as_tab')

        Returns:
            ControllerLocation with file and line number, or None if not found
        """
        cache_key = f"{controller}#{action}"

        # Check cache first
        if cache_key in self._controller_cache:
            return self._controller_cache[cache_key]

        # Find controller file
        controller_info = self.search_engine.find_controller_file(controller)

        if not controller_info:
            self._controller_cache[cache_key] = None
            return None

        # Find action method in controller file
        line_num = self.search_engine.find_method_definition(
            controller_info["file"], action
        )

        if not line_num:
            self._controller_cache[cache_key] = None
            return None

        location = ControllerLocation(
            file=controller_info["file"],
            line=line_num,
            controller=controller,
            action=action,
            confidence="verified (found in actual controller file)"
        )

        self._controller_cache[cache_key] = location
        return location

    def find_callback(
        self, model_file: str, callback_type: str, method_name: str, model_name: str
    ) -> Optional[CallbackLocation]:
        """
        Find callback declaration in a model file.

        Args:
            model_file: Path to model file (relative to project_root)
            callback_type: Callback type (e.g., 'after_save', 'after_create')
            method_name: Method name referenced by callback
            model_name: Model class name (for caching)

        Returns:
            CallbackLocation with file and line number, or None if not found
        """
        cache_key = f"{model_name}::{callback_type}::{method_name}"

        # Check cache first
        if cache_key in self._callback_cache:
            return self._callback_cache[cache_key]

        # Search for callback declaration
        line_num = self.search_engine.find_callback_declaration(
            model_file, callback_type, method_name
        )

        if not line_num:
            self._callback_cache[cache_key] = None
            return None

        location = CallbackLocation(
            file=model_file,
            line=line_num,
            callback_type=callback_type,
            method_name=method_name,
            model_name=model_name
        )

        self._callback_cache[cache_key] = location
        return location

    def batch_find_callbacks(
        self, callback_requests: List[Dict[str, str]]
    ) -> List[Optional[CallbackLocation]]:
        """
        Find multiple callbacks in batch (for transaction analysis).

        Args:
            callback_requests: List of dicts with keys:
                - model_file: str
                - callback_type: str
                - method_name: str
                - model_name: str

        Returns:
            List of CallbackLocation objects (None for not found)
        """
        results = []

        for request in callback_requests:
            location = self.find_callback(
                model_file=request["model_file"],
                callback_type=request["callback_type"],
                method_name=request["method_name"],
                model_name=request["model_name"]
            )
            results.append(location)

        return results

    def clear_cache(self):
        """Clear all cached locations (useful for testing or long-running processes)."""
        self._controller_cache.clear()
        self._callback_cache.clear()

    def get_cache_stats(self) -> Dict[str, int]:
        """Get statistics about cached entries (for debugging)."""
        return {
            "controllers_cached": len(self._controller_cache),
            "callbacks_cached": len(self._callback_cache),
            "total_entries": len(self._controller_cache) + len(self._callback_cache)
        }
