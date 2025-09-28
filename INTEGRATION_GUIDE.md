# Integration Guide: Using the Refactored Agent in ask_code.py

## Quick Start

You now have **three ways** to use the refactored Rails agent:

### 1. Updated Original ask_code.py (Modified)
The original `ask_code.py` has been updated to use the refactored agent:

```bash
python3 ask_code.py --project /path/to/rails/app --debug
```

### 2. Enhanced Version ask_code_refactored.py (Recommended)
A new enhanced version with better UI and debugging:

```bash
python3 ask_code_refactored.py --project /path/to/rails/app --debug
```

### 3. Direct Integration (For Custom Code)
Use the refactored agent directly in your own code:

```python
from agent.refactored_rails_agent import RefactoredRailsAgent
from agent.config import AgentConfig

config = AgentConfig(
    project_root="/path/to/rails",
    max_react_steps=15,
    debug_enabled=True
)

agent = RefactoredRailsAgent(config=config, session=session)
response = agent.process_message("Find user validation code")
```

## Key Changes Made to ask_code.py

### 1. Import Changes
```python
# OLD
from react_rails_agent import ReactRailsAgent

# NEW
from agent.refactored_rails_agent import RefactoredRailsAgent
from agent.config import AgentConfig
```

### 2. Agent Initialization
```python
# OLD
react_agent = ReactRailsAgent(project_root=project_root, session=session)

# NEW
agent_config = AgentConfig(
    project_root=project_root,
    max_react_steps=15,
    debug_enabled=debug,
    log_level="DEBUG" if debug else "INFO"
)
react_agent = RefactoredRailsAgent(config=agent_config, session=session)
```

### 3. Tool Access
```python
# OLD
agent_executor = AgentToolExecutor(react_agent.tools)

# NEW
available_tools = react_agent.tool_registry.get_available_tools()
agent_executor = AgentToolExecutor(available_tools)
```

### 4. State Management
```python
# OLD
if hasattr(react_agent, 'react_steps'):
    react_agent.react_steps.clear()

# NEW
if hasattr(react_agent, 'state_machine'):
    react_agent.state_machine.reset()
```

## New Features Available

### 1. Debug Mode
```bash
python3 ask_code.py --project /path/to/rails --debug
```

- Detailed logging output
- Performance metrics
- Tool usage statistics
- Error stack traces

### 2. Enhanced Status Command
```
/status
```

Shows:
- Project information
- Steps completed
- Tools used
- Configuration details

### 3. Better Error Handling

The refactored agent provides:
- Graceful error recovery
- Detailed error messages
- Automatic retry mechanisms
- Better user feedback

### 4. Configuration Options

```python
config = AgentConfig(
    project_root="/path/to/rails",
    max_react_steps=20,           # More analysis steps
    tool_repetition_limit=5,      # Prevent tool loops
    finalization_threshold=3,     # Request synthesis
    debug_enabled=True,
    log_level="DEBUG"
)
```

## Using the Enhanced Version

The new `ask_code_refactored.py` provides:

### Enhanced UI
- Better status indicators (🤖/🧠 for thinking mode)
- Colored output with Rich formatting
- Improved error messages
- Progress indicators

### Better Commands
- `/status` - Show detailed agent status
- `/clear` - Clear conversation and agent state
- `/think` - Toggle reasoning mode

### Debug Features
- Detailed configuration display
- Tool usage tracking
- Performance metrics
- Error stack traces

## Backward Compatibility

### For Existing Code
The refactored agent maintains the same public interface:

```python
# This still works
response = agent.process_message("Find user authentication")
status = agent.get_status()
summary = agent.get_step_summary()
```

### Migration Helper
Use the compatibility layer for gradual migration:

```python
from agent.compatibility import ReactRailsAgentCompatibility

# Drop-in replacement for old ReactRailsAgent
agent = ReactRailsAgentCompatibility(project_root, session)
```

## Configuration Options

### Environment Variables
```bash
export AGENT_MAX_STEPS=20
export AGENT_TOOL_DEBUG=1
export AGENT_LOG_LEVEL=DEBUG
```

### Code Configuration
```python
config = AgentConfig(
    project_root="/path/to/rails",
    max_react_steps=15,           # Maximum analysis steps
    tool_repetition_limit=4,      # Prevent infinite loops
    finalization_threshold=3,     # When to request final answer
    debug_enabled=True,           # Enable debug output
    log_level="DEBUG",            # Logging verbosity
    timeout=120.0                 # LLM timeout seconds
)
```

## Troubleshooting

### Common Issues

1. **Import Errors**
   ```bash
   # Make sure you're in the project directory
   cd /path/to/ask-repo-agent
   source .venv/bin/activate
   python3 ask_code.py --project /path/to/rails
   ```

2. **Tool Initialization Failures**
   ```bash
   # Use debug mode to see detailed error information
   python3 ask_code.py --project /path/to/rails --debug
   ```

3. **Agent Not Responding**
   ```
   # Check agent status
   /status

   # Clear state and try again
   /clear
   ```

### Debug Information

With `--debug` flag, you'll see:
- Tool initialization status
- Configuration details
- Step-by-step execution
- Performance metrics
- Error traces

## Performance Improvements

The refactored agent provides:

### Better Resource Management
- Reduced memory usage
- Faster tool initialization
- Optimized state tracking

### Improved Analysis
- Better loop detection
- Smarter tool selection
- Enhanced result synthesis

### Enhanced Debugging
- Detailed operation timing
- Tool usage statistics
- Error correlation

## Example Session

```bash
$ python3 ask_code_refactored.py --project /path/to/rails --debug

🚀 Enhanced Rails Analysis Agent (Refactored)
✓ Refactored Rails Agent initialized: /path/to/rails
Config: 15 max steps, debug=True, tools=10
Tool executor configured with 10 tools

🤖 Rails Analysis • myapp • 0 tokens
> Find user validation code

🤖 Agent analyzing...
[Step 1] Starting analysis of user validation request
[Tool] Using enhanced_sql_rails_search
[Result] Found 3 validation patterns in User model

Analysis Steps:
  1. thought: Need to find user validation code
  2. action: enhanced_sql_rails_search
  3. observation: Found User model validations
  4. answer: Located user validations in app/models/user.rb

Usage: 1,250 tokens • Session: 1 queries
Debug: Tools used: 1, Step: 4, Should stop: true
```

## Next Steps

1. **Try the enhanced version**: `python3 ask_code_refactored.py`
2. **Enable debug mode**: Add `--debug` flag
3. **Explore new commands**: Use `/status` and `/think`
4. **Customize configuration**: Modify `AgentConfig` parameters
5. **Integrate into your workflow**: Use the refactored agent in custom code

The refactored architecture provides a solid foundation for reliable, maintainable Rails code analysis with enhanced debugging and monitoring capabilities.