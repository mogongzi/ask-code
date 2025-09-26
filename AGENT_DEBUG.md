# Agent Tools Debug Logging System

## Overview

The agent tools now include comprehensive debug logging to help troubleshoot issues with the ReAct Rails agent. This system provides detailed visibility into:

- **Input parameters** received by each tool
- **Internal processing steps** and decision making
- **External command execution** (like ripgrep searches)
- **Output results** and execution timing
- **Error handling** and failure modes

## How to Enable Debug Logging

### Method 1: Environment Variable
```bash
export AGENT_TOOL_DEBUG=1
# or
AGENT_TOOL_DEBUG=true python ask_code.py --project /path/to/rails/project
```

### Method 2: Set in Shell
```bash
AGENT_TOOL_DEBUG=1 python ask_code.py --project /path/to/rails/project
```

## Debug Output Format

Each debug message follows this format:
```
🔧 [tool_name] 📥 INPUT
{
  "parameter": "value",
  "another_param": 123
}

🔧 [tool_name] 🔍 Internal Step
Processing information...

🔧 [tool_name] 📤 OUTPUT (123.5ms)
{
  "result": "data"
}
```

### Icons and Their Meanings

- 🔧 **Tool identifier** - Shows which tool is executing
- 📥 **INPUT** - Parameters received by the tool
- 📤 **OUTPUT** - Final results with execution time
- 🔍 **Processing** - Internal search/analysis steps
- 🧠 **Analysis** - Semantic analysis results
- 🔑 **Key data** - Important intermediate results
- 🚀 **Execution** - External command execution
- 📊 **Results** - Search results and statistics
- ❌ **Error** - Error conditions and failures
- ⏰ **Timeout** - Timeout conditions

## Tools with Debug Support

### Enhanced SQL Rails Search (`enhanced_sql_rails_search`)
- Shows SQL query analysis and intent detection
- Displays generated Rails patterns
- Traces ripgrep command execution
- Shows search strategy results and ranking

### Ripgrep Tool (`ripgrep`)
- Shows search parameters and command construction
- Displays actual ripgrep command executed
- Shows return codes and match counts
- Traces result parsing

### Controller Analyzer (`controller_analyzer`)
- Shows controller file location and parsing
- Displays extracted actions and methods
- Shows analysis focus and results

### Model Analyzer (`model_analyzer`)
- Shows model file analysis parameters
- Displays extracted validations, associations, callbacks
- Shows method categorization

### Base Tool Features
All tools inherit these debug capabilities:
- Input parameter logging with validation
- Execution time measurement
- Error handling and logging
- Result truncation for large outputs

## Example Debug Session

```bash
AGENT_TOOL_DEBUG=1 python -c "
import asyncio
from agents.tools.enhanced_sql_rails_search import EnhancedSQLRailsSearch

async def debug_test():
    tool = EnhancedSQLRailsSearch(project_root='/path/to/rails/project')
    await tool.execute({'sql': 'SELECT * FROM users WHERE active = true'})

asyncio.run(debug_test())
"
```

This will show:
1. **Input validation** and parameter processing
2. **SQL analysis** with intent detection and pattern generation
3. **Search strategies** being executed in sequence
4. **Ripgrep commands** with patterns and results
5. **Result ranking** and final output generation
6. **Execution timing** for performance analysis

## Troubleshooting Common Issues

### 1. "No matches found" Issues
Look for:
- 🔍 **Generated patterns** - Are they correct for your query?
- 🚀 **Ripgrep commands** - Are the patterns and paths correct?
- 📊 **Return codes** - Check if ripgrep is finding anything

### 2. "Project root not found" Errors
Check:
- 📥 **INPUT** - Is the project_root parameter set?
- The path exists and is a valid Rails project

### 3. Slow Performance
Look for:
- 📤 **Execution times** - Which tools are taking longest?
- 🚀 **Command execution** - Are external tools responding quickly?
- Multiple repeated searches that could be optimized

### 4. Pattern Generation Issues
Check:
- 🧠 **SQL Analysis** - Is the intent correctly detected?
- 🔑 **Rails patterns** - Are the generated patterns realistic?
- 🔍 **Search strategies** - Are appropriate strategies being used?

## Debug Output Management

### Large Output Handling
- Results are automatically **truncated at 500 characters**
- Large data structures show **summary information**
- Use **jq** or similar tools to process JSON debug output

### Filtering Debug Output
```bash
# Only show errors
AGENT_TOOL_DEBUG=1 python script.py 2>&1 | grep "❌"

# Only show execution times
AGENT_TOOL_DEBUG=1 python script.py 2>&1 | grep "OUTPUT.*ms"

# Only show specific tool
AGENT_TOOL_DEBUG=1 python script.py 2>&1 | grep "\[ripgrep\]"
```

## Performance Impact

Debug logging adds minimal overhead:
- **Text processing**: ~1-2ms per tool execution
- **JSON serialization**: ~0.5ms for typical results
- **Console output**: Dependent on terminal speed

Disable debug logging in production for optimal performance.

## Contributing Debug Information

When reporting agent issues, include:
1. **Full debug output** with `AGENT_TOOL_DEBUG=1`
2. **SQL query** or prompt that caused the issue
3. **Expected vs actual results**
4. **Rails project structure** (Gemfile, app/ directory contents)

This debug information helps quickly identify whether issues are in:
- Query analysis and pattern generation
- External tool execution (ripgrep, etc.)
- Result parsing and ranking
- File system access and permissions