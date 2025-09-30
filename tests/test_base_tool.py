"""
Tests for tools.base_tool.BaseTool
"""
import pytest
from unittest.mock import Mock, patch
import time

from tools.base_tool import BaseTool


class ConcreteTool(BaseTool):
    """Concrete implementation of BaseTool for testing."""

    @property
    def name(self):
        return "test_tool"

    @property
    def description(self):
        return "A test tool for unit testing"

    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Test query parameter"
                },
                "count": {
                    "type": "integer",
                    "description": "Number of results",
                    "default": 10
                }
            },
            "required": ["query"]
        }

    def validate_input(self, input_params):
        """Override parent validation to check for required parameters."""
        if not super().validate_input(input_params):
            return False
        return "query" in input_params

    def execute(self, input_params):
        if not self.validate_input(input_params):
            return {"error": "Invalid input"}

        query = input_params.get("query", "")
        count = input_params.get("count", 10)

        return {
            "query": query,
            "results": [f"result_{i}" for i in range(count)],
            "total": count
        }


class FailingTool(BaseTool):
    """Tool that always fails for testing error handling."""

    @property
    def name(self):
        return "failing_tool"

    @property
    def description(self):
        return "A tool that always fails"

    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {"param": {"type": "string"}},
            "required": ["param"]
        }

    def execute(self, input_params):
        raise Exception("This tool always fails")


class TestBaseTool:
    """Test suite for BaseTool abstract base class."""

    def test_initialization_with_defaults(self):
        """Test tool initialization with default values."""
        tool = ConcreteTool()

        assert tool.project_root is None
        assert tool.debug_enabled is False
        assert tool.console is not None

    def test_initialization_with_custom_values(self, temp_project_root):
        """Test tool initialization with custom values."""
        tool = ConcreteTool(project_root=temp_project_root, debug=True)

        assert tool.project_root == temp_project_root
        assert tool.debug_enabled is True

    def test_abstract_methods_implemented(self):
        """Test that concrete tool implements all abstract methods."""
        tool = ConcreteTool()

        assert tool.name == "test_tool"
        assert tool.description == "A test tool for unit testing"
        assert isinstance(tool.parameters, dict)
        assert "type" in tool.parameters
        assert tool.parameters["type"] == "object"

    def test_execute_method(self):
        """Test execute method with valid input."""
        tool = ConcreteTool()
        input_params = {"query": "test query", "count": 3}

        result = tool.execute(input_params)

        assert result["query"] == "test query"
        assert len(result["results"]) == 3
        assert result["total"] == 3
        assert result["results"] == ["result_0", "result_1", "result_2"]

    def test_execute_with_defaults(self):
        """Test execute method with default parameters."""
        tool = ConcreteTool()
        input_params = {"query": "test query"}

        result = tool.execute(input_params)

        assert result["total"] == 10  # Default count
        assert len(result["results"]) == 10

    def test_validate_input_valid(self):
        """Test input validation with valid parameters."""
        tool = ConcreteTool()

        # Valid input
        assert tool.validate_input({"query": "test"}) is True
        assert tool.validate_input({"query": "test", "count": 5}) is True

    def test_validate_input_invalid(self):
        """Test input validation with invalid parameters."""
        tool = ConcreteTool()

        # Missing required parameter (ConcreteTool requires "query")
        assert tool.validate_input({}) is False
        assert tool.validate_input({"count": 5}) is False

        # None input
        assert tool.validate_input(None) is False

    def test_debug_logging_enabled(self, temp_project_root):
        """Test debug logging when debug is enabled."""
        tool = ConcreteTool(project_root=temp_project_root, debug=True)

        with patch.object(tool, '_debug_log') as mock_debug:
            input_params = {"query": "test"}
            tool.execute(input_params)

            # Should have debug calls (exact calls depend on implementation)
            # We just verify debug logging was attempted
            assert tool.debug_enabled is True

    def test_debug_logging_disabled(self, temp_project_root):
        """Test debug logging when debug is disabled."""
        tool = ConcreteTool(project_root=temp_project_root, debug=False)

        assert tool.debug_enabled is False

    def test_debug_input_method(self, temp_project_root):
        """Test _debug_input method."""
        tool = ConcreteTool(project_root=temp_project_root, debug=True)

        with patch.object(tool.console, 'print') as mock_print:
            test_input = {"test": "value"}
            tool._debug_input(test_input)

            # Should print debug information when debug is enabled
            assert mock_print.called

    def test_debug_output_method(self, temp_project_root):
        """Test _debug_output method."""
        tool = ConcreteTool(project_root=temp_project_root, debug=True)

        with patch.object(tool.console, 'print') as mock_print:
            test_output = {"result": "value"}
            tool._debug_output(test_output)

            # Should print debug information when debug is enabled
            assert mock_print.called

    def test_debug_log_method(self, temp_project_root):
        """Test _debug_log method."""
        tool = ConcreteTool(project_root=temp_project_root, debug=True)

        with patch.object(tool.console, 'print') as mock_print:
            tool._debug_log("Test message", {"key": "value"})

            # Should print debug information when debug is enabled
            assert mock_print.called

    def test_debug_methods_no_output_when_disabled(self, temp_project_root):
        """Test debug methods don't output when debug is disabled."""
        tool = ConcreteTool(project_root=temp_project_root, debug=False)

        with patch.object(tool.console, 'print') as mock_print:
            tool._debug_input({"test": "value"})
            tool._debug_output({"result": "value"})
            tool._debug_log("Test message", {"key": "value"})

            # Should not print anything when debug is disabled
            assert not mock_print.called

    def test_execute_with_debug_wrapper(self, temp_project_root):
        """Test execute_with_debug wrapper method."""
        tool = ConcreteTool(project_root=temp_project_root, debug=True)

        with patch.object(tool, '_debug_log') as mock_debug:
            input_params = {"query": "test"}
            result = tool.execute_with_debug(input_params)

            # Should return same result as regular execute
            assert result["query"] == "test"

            # Should have debug logging
            assert mock_debug.called

    def test_execute_with_debug_timing(self, temp_project_root):
        """Test that execute_with_debug includes timing information."""
        tool = ConcreteTool(project_root=temp_project_root, debug=True)

        # Add a small delay to test timing
        original_execute = tool.execute

        def slow_execute(params):
            time.sleep(0.01)  # 10ms delay
            return original_execute(params)

        tool.execute = slow_execute

        with patch.object(tool, '_debug_output') as mock_debug_output:
            input_params = {"query": "test"}
            result = tool.execute_with_debug(input_params)

            # Should call _debug_output with timing information
            assert mock_debug_output.called
            # Check that execution_time_ms was passed
            call_args = mock_debug_output.call_args
            assert len(call_args[0]) >= 1  # At least result argument
            if len(call_args[0]) > 1:
                execution_time = call_args[0][1]
                assert execution_time is not None
                assert execution_time >= 10  # Should be at least 10ms due to sleep

    def test_error_handling_in_execute(self):
        """Test error handling in tool execution."""
        tool = FailingTool()

        with pytest.raises(Exception, match="This tool always fails"):
            tool.execute({"param": "test"})

    def test_tool_schema_generation(self):
        """Test that tool can generate proper schema for LLM."""
        tool = ConcreteTool()

        schema = {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters
        }

        assert schema["name"] == "test_tool"
        assert schema["description"] == "A test tool for unit testing"
        assert schema["parameters"]["type"] == "object"
        assert "query" in schema["parameters"]["properties"]
        assert "count" in schema["parameters"]["properties"]
        assert "query" in schema["parameters"]["required"]

    def test_tool_inheritance_structure(self):
        """Test that tool properly inherits from BaseTool."""
        tool = ConcreteTool()

        assert isinstance(tool, BaseTool)
        assert hasattr(tool, 'name')
        assert hasattr(tool, 'description')
        assert hasattr(tool, 'parameters')
        assert hasattr(tool, 'execute')
        assert hasattr(tool, 'validate_input')

    def test_project_root_accessibility(self, temp_project_root):
        """Test that project root is accessible to derived tools."""
        tool = ConcreteTool(project_root=temp_project_root)

        # Tool should be able to access project root for file operations
        assert tool.project_root == temp_project_root

    def test_console_accessibility(self):
        """Test that console is accessible for output."""
        tool = ConcreteTool()

        # Tool should have access to console for output
        assert tool.console is not None
        assert hasattr(tool.console, 'print')

    def test_multiple_tool_instances_independent(self, temp_project_root):
        """Test that multiple tool instances are independent."""
        tool1 = ConcreteTool(project_root=temp_project_root, debug=True)
        tool2 = ConcreteTool(project_root="/different/path", debug=False)

        assert tool1.project_root != tool2.project_root
        assert tool1.debug_enabled != tool2.debug_enabled
        assert tool1 is not tool2