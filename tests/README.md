# Tests for ride_rails

This directory contains comprehensive unit tests for the core components of the ride_rails Rails analysis agent.

## Test Structure

### Core Component Tests

- **`test_agent_config.py`** - Tests for `agent.config.AgentConfig`
  - Configuration loading and validation
  - Environment variable handling
  - Default and custom configurations

- **`test_tool_registry.py`** - Tests for `agent.tool_registry.ToolRegistry`
  - Tool initialization and management
  - Error handling for failed tools
  - Tool schema generation for LLMs

- **`test_base_tool.py`** - Tests for `tools.base_tool.BaseTool`
  - Abstract base class functionality
  - Debug logging and validation
  - Tool execution patterns

- **`test_ripgrep_tool.py`** - Tests for `tools.ripgrep_tool.RipgrepTool`
  - Ripgrep command construction
  - Output parsing and error handling
  - File type filtering and search options

- **`test_state_machine.py`** - Tests for `agent.state_machine.ReActStateMachine`
  - Step tracking and tool usage statistics
  - Search attempt recording
  - State management and reset functionality

- **`test_response_analyzer.py`** - Tests for `agent.response_analyzer.ResponseAnalyzer`
  - Response analysis and finalization decisions
  - Reasoning extraction and action detection
  - Confidence scoring and step progression

### Test Fixtures and Utilities

- **`conftest.py`** - Shared pytest fixtures and test utilities
  - Temporary Rails project structure
  - Mock objects for testing
  - Common test data and helpers

## Running Tests

### Quick Start

```bash
# Run all tests
python tests/run_tests.py

# Run with verbose output
python tests/run_tests.py -v

# Run specific test file
python tests/run_tests.py test_agent_config.py

# Run with coverage
python tests/run_tests.py -c
```

### Direct pytest Usage

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_agent_config.py

# Run with coverage
pytest tests/ --cov=agent --cov=tools --cov-report=term-missing

# Run specific test method
pytest tests/test_agent_config.py::TestAgentConfig::test_default_configuration
```

### Test Categories

```bash
# Run only configuration tests
pytest tests/test_agent_config.py tests/test_tool_registry.py

# Run only tool tests
pytest tests/test_base_tool.py tests/test_ripgrep_tool.py

# Run with specific markers (if added)
pytest -m "unit" tests/
```

## Test Requirements

The tests require these packages (typically available in the project environment):

- `pytest` - Test framework
- `pytest-cov` - Coverage reporting (optional)
- Standard library `unittest.mock` for mocking

## Test Coverage

The test suite covers:

- ✅ **Configuration Management** - Environment variables, validation, defaults
- ✅ **Tool System** - Registration, initialization, execution patterns
- ✅ **Search Tools** - Ripgrep integration, output parsing, error handling
- ✅ **State Management** - Step tracking, tool usage statistics
- ✅ **Response Analysis** - Finalization logic, reasoning extraction
- ✅ **Error Handling** - Graceful failure handling across components
- ✅ **Debug Features** - Debug logging and diagnostic capabilities

## Writing New Tests

### Test File Naming

- Test files: `test_<component_name>.py`
- Test classes: `Test<ComponentName>`
- Test methods: `test_<specific_behavior>`

### Using Fixtures

```python
def test_with_project_root(temp_project_root):
    """Test using temporary Rails project structure."""
    tool = SomeTool(temp_project_root)
    # Test with real file structure
```

### Mocking External Dependencies

```python
@patch('subprocess.run')
def test_external_command(mock_run):
    """Test tool that uses external commands."""
    mock_run.return_value = Mock(returncode=0, stdout="output")
    # Test without actually running external commands
```

### Testing Error Conditions

```python
def test_error_handling():
    """Test proper error handling."""
    tool = SomeTool()
    with pytest.raises(ValueError, match="Expected error message"):
        tool.execute(invalid_params)
```

## Continuous Integration

These tests are designed to run in CI environments:

- No external dependencies (Rails, ripgrep mocked)
- Fast execution (under 30 seconds for full suite)
- Deterministic results (no flaky tests)
- Clear failure messages

## Coverage Reports

When running with coverage (`-c` flag), reports are generated:

- Terminal output with missing lines
- HTML report in `tests/coverage_html/` (if pytest-cov installed)

## Debugging Tests

### Running Single Tests

```bash
# Run one specific test
pytest tests/test_agent_config.py::TestAgentConfig::test_default_configuration -v
```

### Adding Debug Output

```python
def test_with_debug(capfd):
    """Test with captured output."""
    tool = SomeTool(debug=True)
    result = tool.execute(params)

    captured = capfd.readouterr()
    assert "debug message" in captured.out
```

### Test Isolation

Each test runs in isolation:
- Fresh instances of components
- Temporary directories cleaned up automatically
- Mocks reset between tests

## Best Practices

1. **Test Independence** - Each test should run independently
2. **Clear Names** - Test names should describe what they test
3. **Single Responsibility** - One test per behavior/scenario
4. **Mock External Dependencies** - Don't rely on external tools
5. **Use Fixtures** - Reuse common setup via fixtures
6. **Test Edge Cases** - Include error conditions and edge cases
7. **Fast Execution** - Keep tests fast for developer productivity