#!/usr/bin/env python3
"""
Quick fix for the async/await issue in the refactored agent.

This script fixes the hanging issue caused by async methods being called synchronously.
"""

import os
import glob
from pathlib import Path


def fix_async_issues():
    """Fix async issues in the refactored agent."""

    project_root = Path(__file__).parent

    # Fix tools - remove async from execute methods
    tools_dir = project_root / "tools"
    if tools_dir.exists():
        for tool_file in tools_dir.glob("*.py"):
            try:
                with open(tool_file, 'r') as f:
                    content = f.read()

                # Replace async def execute with def execute
                if "async def execute(" in content:
                    content = content.replace("async def execute(", "def execute(")

                    with open(tool_file, 'w') as f:
                        f.write(content)

                    print(f"✓ Fixed {tool_file.name}")
            except Exception as e:
                print(f"✗ Error fixing {tool_file.name}: {e}")

    # Fix LLM client - remove async from call_llm methods
    llm_client_file = project_root / "agent" / "llm_client.py"
    if llm_client_file.exists():
        try:
            with open(llm_client_file, 'r') as f:
                content = f.read()

            # Remove async from methods
            content = content.replace("async def call_llm(", "def call_llm(")
            content = content.replace("async def _call_real_llm(", "def _call_real_llm(")
            content = content.replace("return await self._call_real_llm", "return self._call_real_llm")

            with open(llm_client_file, 'w') as f:
                f.write(content)

            print("✓ Fixed LLM client async issues")
        except Exception as e:
            print(f"✗ Error fixing LLM client: {e}")

    # Fix base tool - remove async from execute methods
    base_tool_file = project_root / "tools" / "base_tool.py"
    if base_tool_file.exists():
        try:
            with open(base_tool_file, 'r') as f:
                content = f.read()

            # Remove async from abstract method
            content = content.replace("async def execute(", "def execute(")
            content = content.replace("async def execute_with_debug(", "def execute_with_debug(")
            content = content.replace("result = await self.execute(", "result = self.execute(")

            with open(base_tool_file, 'w') as f:
                f.write(content)

            print("✓ Fixed base tool async issues")
        except Exception as e:
            print(f"✗ Error fixing base tool: {e}")

    print("\n🎉 Async issues should now be fixed!")
    print("You can now run the refactored agent without hanging.")


if __name__ == "__main__":
    print("🔧 Fixing async/await issues in refactored agent...")
    fix_async_issues()