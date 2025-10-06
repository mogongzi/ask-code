"""
Tests for agent.tool_registry.ToolRegistry
"""
import pytest
from unittest.mock import Mock, patch, MagicMock

from agent.tool_registry import ToolRegistry, ToolInitializationError
from tools.base_tool import BaseTool


class MockTool(BaseTool):
    """Mock tool for testing."""

    def __init__(self, project_root=None, debug=False, should_fail=False):
        if should_fail:
            raise Exception("Initialization failed")
        super().__init__(project_root, debug)

    @property
    def name(self):
        return "mock_tool"

    @property
    def description(self):
        return "Mock tool for testing"

    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {
                "test_param": {"type": "string"}
            }
        }

    def execute(self, input_params):
        return {"result": "mock_result"}


class TestToolRegistry:
    """Test suite for ToolRegistry."""

    def test_initialization_with_defaults(self, temp_project_root):
        """Test registry initialization with default values."""
        registry = ToolRegistry(temp_project_root)

        assert registry.project_root == temp_project_root
        assert registry.debug is False
        assert isinstance(registry.tools, dict)
        assert isinstance(registry.initialization_errors, list)
        assert len(registry.allowed_tools) > 0

    def test_initialization_with_debug(self, temp_project_root):
        """Test registry initialization with debug enabled."""
        registry = ToolRegistry(temp_project_root, debug=True)

        assert registry.debug is True

    @patch('agent.tool_registry.ToolRegistry.CORE_TOOLS', {'mock_tool': MockTool})
    def test_successful_tool_initialization(self, temp_project_root):
        """Test successful tool initialization."""
        registry = ToolRegistry(temp_project_root, debug=True)

        assert 'mock_tool' in registry.tools
        assert isinstance(registry.tools['mock_tool'], MockTool)
        assert registry.tools['mock_tool'].debug_enabled is True
        assert len(registry.initialization_errors) == 0

    @patch('agent.tool_registry.ToolRegistry.CORE_TOOLS', {'failing_tool': lambda pr, debug: MockTool(pr, debug, should_fail=True)})
    def test_failed_tool_initialization(self, temp_project_root):
        """Test handling of failed tool initialization."""
        registry = ToolRegistry(temp_project_root)

        assert 'failing_tool' not in registry.tools
        assert len(registry.initialization_errors) == 1

        error = registry.initialization_errors[0]
        assert error.name == 'failing_tool'
        assert "Initialization failed" in error.error
        assert error.exception_type == "Exception"

    def test_get_tool_existing(self, temp_project_root):
        """Test getting an existing tool."""
        registry = ToolRegistry(temp_project_root)

        # Assume ripgrep tool exists in actual registry
        if 'ripgrep' in registry.tools:
            tool = registry.get_tool('ripgrep')
            assert tool is not None
            assert tool.name == 'ripgrep'

    def test_get_tool_non_existing(self, temp_project_root):
        """Test getting a non-existing tool."""
        registry = ToolRegistry(temp_project_root)
        tool = registry.get_tool('non_existing_tool')
        assert tool is None

    def test_get_tool_with_synonym(self, temp_project_root):
        """Test getting a tool using a synonym."""
        registry = ToolRegistry(temp_project_root)

        # Test with a known synonym
        if 'ripgrep' in registry.tools:
            tool_by_name = registry.get_tool('ripgrep')
            tool_by_synonym = registry.get_tool('grep')  # 'grep' is a synonym for 'ripgrep'

            assert tool_by_name is tool_by_synonym

    def test_get_available_tools(self, temp_project_root):
        """Test getting available tools."""
        registry = ToolRegistry(temp_project_root)
        tools = registry.get_available_tools()

        assert isinstance(tools, dict)
        assert len(tools) > 0

        # Each tool should be a BaseTool instance
        for tool_name, tool_instance in tools.items():
            assert isinstance(tool_name, str)
            assert isinstance(tool_instance, BaseTool)

    def test_get_available_tools_with_errors(self, temp_project_root):
        """Test getting tools when some failed to initialize."""
        with patch('agent.tool_registry.ToolRegistry.CORE_TOOLS', {
            'working_tool': MockTool,
            'failing_tool': lambda pr, debug: MockTool(pr, debug, should_fail=True)
        }):
            registry = ToolRegistry(temp_project_root)
            tools = registry.get_available_tools()
            failed_tools = registry.get_failed_tools()

            assert len(tools) == 1
            assert len(failed_tools) == 1
            assert 'working_tool' in tools
            assert failed_tools[0].name == 'failing_tool'

    def test_build_tool_schemas(self, temp_project_root):
        """Test building tool schemas for LLM."""
        registry = ToolRegistry(temp_project_root)
        schemas = registry.build_tool_schemas()

        assert isinstance(schemas, list)
        assert len(schemas) > 0

        # Each schema should have required format
        for schema in schemas:
            assert 'name' in schema
            assert 'description' in schema
            assert 'input_schema' in schema
            assert schema['input_schema']['type'] == 'object'

    @patch('agent.tool_registry.ToolRegistry.CORE_TOOLS', {'mock_tool': MockTool})
    def test_build_tool_schemas_with_mock(self, temp_project_root):
        """Test tool schema generation with mock tool."""
        registry = ToolRegistry(temp_project_root)
        schemas = registry.build_tool_schemas()

        mock_schema = next((s for s in schemas if s['name'] == 'mock_tool'), None)
        assert mock_schema is not None
        assert mock_schema['description'] == "Mock tool for testing"
        assert 'test_param' in mock_schema['input_schema']['properties']

    def test_get_failed_tools(self, temp_project_root):
        """Test getting initialization errors."""
        with patch('agent.tool_registry.ToolRegistry.CORE_TOOLS', {
            'failing_tool': lambda pr, debug: MockTool(pr, debug, should_fail=True)
        }):
            registry = ToolRegistry(temp_project_root)
            errors = registry.get_failed_tools()

            assert len(errors) == 1
            assert errors[0].name == 'failing_tool'

    def test_tool_synonyms_mapping(self, temp_project_root):
        """Test that tool synonyms are properly mapped."""
        registry = ToolRegistry(temp_project_root)

        # Test known synonyms
        synonyms_to_test = [
            ('grep', 'ripgrep'),
            ('sql_search', 'enhanced_sql_rails_search'),
            ('astgrep', 'ast_grep')
        ]

        for synonym, actual_name in synonyms_to_test:
            if actual_name in registry.tools:
                tool_by_synonym = registry.get_tool(synonym)
                tool_by_name = registry.get_tool(actual_name)
                assert tool_by_synonym is tool_by_name

    def test_allowed_tools_filtering(self, temp_project_root):
        """Test that only allowed tools are initialized."""
        # This test verifies that the registry respects the allowed_tools set
        registry = ToolRegistry(temp_project_root)

        for tool_name in registry.tools.keys():
            assert tool_name in registry.allowed_tools

    def test_project_root_passed_to_tools(self, temp_project_root):
        """Test that project root is passed to tools during initialization."""
        with patch('agent.tool_registry.ToolRegistry.CORE_TOOLS', {'mock_tool': MockTool}):
            registry = ToolRegistry(temp_project_root, debug=False)

            mock_tool = registry.get_tool('mock_tool')
            assert mock_tool.project_root == temp_project_root

    def test_debug_flag_passed_to_tools(self, temp_project_root):
        """Test that debug flag is passed to tools during initialization."""
        with patch('agent.tool_registry.ToolRegistry.CORE_TOOLS', {'mock_tool': MockTool}):
            registry = ToolRegistry(temp_project_root, debug=True)

            mock_tool = registry.get_tool('mock_tool')
            assert mock_tool.debug_enabled is True

    def test_registry_statistics(self, temp_project_root):
        """Test getting registry statistics."""
        registry = ToolRegistry(temp_project_root)

        total_tools = len(registry.CORE_TOOLS)
        initialized_tools = len(registry.tools)
        failed_tools = len(registry.initialization_errors)

        assert initialized_tools + failed_tools == total_tools
        assert initialized_tools >= 0
        assert failed_tools >= 0

    def test_tool_registry_is_singleton_like(self, temp_project_root):
        """Test that multiple registries with same config behave consistently."""
        registry1 = ToolRegistry(temp_project_root, debug=False)
        registry2 = ToolRegistry(temp_project_root, debug=False)

        # Should have same tools available (though different instances)
        assert set(registry1.tools.keys()) == set(registry2.tools.keys())
        assert len(registry1.initialization_errors) == len(registry2.initialization_errors)
