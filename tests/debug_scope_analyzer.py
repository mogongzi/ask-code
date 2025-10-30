#!/usr/bin/env python3
"""
Debug ModelScopeAnalyzer to understand why scope resolution is failing.
"""
import sys
from pathlib import Path

# Add tools directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.components.model_scope_analyzer import ModelScopeAnalyzer

# Rails project and model paths
RAILS_PROJECT = "/Users/I503354/jam/local/ct"
MEMBER_MODEL = Path(RAILS_PROJECT) / "app" / "models" / "member.rb"


def main():
    print("=" * 80)
    print("  🔍 Scope Analyzer Diagnostic")
    print("=" * 80)

    # Check if model file exists
    print(f"\n1. Checking model file path:")
    print(f"   Path: {MEMBER_MODEL}")
    print(f"   Exists: {MEMBER_MODEL.exists()}")

    if not MEMBER_MODEL.exists():
        print(f"\n❌ ERROR: Model file not found!")
        return

    # Test scope analyzer
    print(f"\n2. Initializing ModelScopeAnalyzer...")
    analyzer = ModelScopeAnalyzer(debug=True)

    print(f"\n3. Analyzing Member model...")
    scopes = analyzer.analyze_model(str(MEMBER_MODEL))

    print(f"\n4. Results:")
    print(f"   Total scopes extracted: {len(scopes)}")

    if scopes:
        print(f"\n5. Scope details:")
        for name in ["all_canonical", "not_disabled", "active"]:
            if name in scopes:
                scope = scopes[name]
                print(f"\n   📍 {name}:")
                print(f"      WHERE clauses: {len(scope.where_clauses)}")
                if scope.where_clauses:
                    for clause in scope.where_clauses:
                        print(f"        - {clause.column} {clause.operator}")
                else:
                    print(f"        (no WHERE clauses)")
            else:
                print(f"\n   ❌ {name}: NOT FOUND")
    else:
        print(f"\n   ❌ No scopes extracted!")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
