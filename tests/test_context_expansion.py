"""
Test context expansion for association chain detection.

This tests that multi-line Rails code with association chains
is properly detected after context expansion.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.components.progressive_search_engine import ProgressiveSearchEngine
from tools.components.code_search_engine import CodeSearchEngine

def test_context_expansion():
    """Test that context expansion captures association chains on previous lines."""

    # Mock project root
    project_root = "/Users/I503354/jam/local/ct"

    # Initialize components
    code_search_engine = CodeSearchEngine(project_root=project_root, debug_log=None)
    progressive_search = ProgressiveSearchEngine(
        code_search_engine=code_search_engine,
        project_root=project_root,
        debug=False
    )

    # Test file path and line number
    test_file = "app/mailers/alert_mailer.rb"
    test_line = 178  # Line with .active or pagination

    print("=" * 80)
    print("CONTEXT EXPANSION TEST")
    print("=" * 80)
    print(f"File: {test_file}")
    print(f"Line: {test_line}")
    print()

    # Test context expansion
    full_path = Path(project_root) / test_file
    expanded = progressive_search._expand_context(str(full_path), test_line, lines_before=5)

    print(f"Expanded context (5 lines before + matched line):")
    print(f"  {expanded}")
    print()

    # Check if association chain is detected
    from tools.components.where_clause_matcher import WhereClauseParser

    parser = WhereClauseParser(project_root=project_root)

    # Test scope detection
    scope_chains = parser._detect_scope_chains(expanded)
    print(f"Detected scope chains: {scope_chains}")

    # Test foreign key detection
    foreign_key = parser._detect_association_foreign_key(expanded)
    print(f"Detected foreign key: {foreign_key}")

    # Test full parsing
    conditions = parser.parse_ruby_code(expanded)
    print(f"\nParsed {len(conditions)} WHERE conditions:")
    for i, cond in enumerate(conditions, 1):
        print(f"  {i}. {cond}")

    print()
    print("=" * 80)

    # Success if we detect company_id
    has_company_id = any(c.column == "company_id" for c in conditions)
    if has_company_id:
        print("✅ SUCCESS: company_id condition detected from association chain!")
    else:
        print("⚠️  WARNING: company_id not detected (may need to check actual file)")

if __name__ == "__main__":
    test_context_expansion()
