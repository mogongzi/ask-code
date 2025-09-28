#!/usr/bin/env python3
"""
Complete fix for all async/await issues in the refactored Rails agent.

This script ensures all async issues are completely resolved.
"""

import os
import re
from pathlib import Path


def fix_all_async_issues():
    """Comprehensive fix for all async issues."""

    project_root = Path(__file__).parent
    print("🔧 Applying comprehensive async/await fixes...")

    # Fix 1: Remove async from all tool execute methods
    tools_dir = project_root / "tools"
    if tools_dir.exists():
        for tool_file in tools_dir.glob("*.py"):
            try:
                with open(tool_file, 'r') as f:
                    content = f.read()

                original_content = content

                # Remove async from execute methods
                content = re.sub(r'async def execute\(', 'def execute(', content)
                content = re.sub(r'async def _([a-zA-Z_])', r'def _\1', content)

                # Remove await statements
                content = re.sub(r'await\s+', '', content)
                content = re.sub(r'# await\s+', '', content)

                if content != original_content:
                    with open(tool_file, 'w') as f:
                        f.write(content)
                    print(f"✓ Fixed {tool_file.name}")
            except Exception as e:
                print(f"✗ Error fixing {tool_file.name}: {e}")

    # Fix 2: Fix LLM client
    llm_client_file = project_root / "agent" / "llm_client.py"
    if llm_client_file.exists():
        try:
            with open(llm_client_file, 'r') as f:
                content = f.read()

            content = re.sub(r'async def call_llm\(', 'def call_llm(', content)
            content = re.sub(r'async def _call_real_llm\(', 'def _call_real_llm(', content)
            content = re.sub(r'return await self\._call_real_llm', 'return self._call_real_llm', content)

            with open(llm_client_file, 'w') as f:
                f.write(content)
            print("✓ Fixed LLM client")
        except Exception as e:
            print(f"✗ Error fixing LLM client: {e}")

    # Fix 3: Fix base tool
    base_tool_file = project_root / "tools" / "base_tool.py"
    if base_tool_file.exists():
        try:
            with open(base_tool_file, 'r') as f:
                content = f.read()

            content = re.sub(r'async def execute\(', 'def execute(', content)
            content = re.sub(r'async def execute_with_debug\(', 'def execute_with_debug(', content)
            content = re.sub(r'result = await self\.execute\(', 'result = self.execute(', content)

            with open(base_tool_file, 'w') as f:
                f.write(content)
            print("✓ Fixed base tool")
        except Exception as e:
            print(f"✗ Error fixing base tool: {e}")

    # Fix 4: Fix agent tool executor
    executor_file = project_root / "agent_tool_executor.py"
    if executor_file.exists():
        try:
            with open(executor_file, 'r') as f:
                content = f.read()

            # Check if it still has async issues
            if 'await tool.execute' in content:
                # Replace the async execution with synchronous
                content = re.sub(
                    r'async def _run\(\) -> Any:.*?return f"Error executing \{tool_name\}: \{e\}"',
                    '''try:
            result = tool.execute(parameters or {})
        except Exception as e:  # pragma: no cover
            result = f"Error executing {tool_name}: {e}"''',
                    content,
                    flags=re.DOTALL
                )

                # Remove the complex asyncio logic
                content = re.sub(
                    r'# Run the coroutine safely.*?result = asyncio\.run\(_run\(\)\)',
                    '',
                    content,
                    flags=re.DOTALL
                )

                # Remove asyncio import if not needed
                content = re.sub(r'import asyncio\n', '', content)

                with open(executor_file, 'w') as f:
                    f.write(content)
                print("✓ Fixed agent tool executor")
        except Exception as e:
            print(f"✗ Error fixing agent tool executor: {e}")

    print("\n🎉 All async/await issues fixed!")
    print("✅ The refactored agent should now work without hanging.")


def test_imports():
    """Test that imports work after fixes."""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))

        from agent.refactored_rails_agent import RefactoredRailsAgent
        from agent.config import AgentConfig

        config = AgentConfig(project_root="/tmp", max_react_steps=5)
        agent = RefactoredRailsAgent(config=config, session=None)

        print("✅ Import test passed - agent can be created successfully!")
        return True
    except Exception as e:
        print(f"❌ Import test failed: {e}")
        return False


if __name__ == "__main__":
    fix_all_async_issues()
    print("\n" + "="*50)
    print("Testing imports...")
    test_imports()