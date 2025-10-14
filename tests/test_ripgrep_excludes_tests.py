"""
Test that ripgrep tool excludes test directories.

This ensures production code searches don't return test files.
"""
import tempfile
import os
from pathlib import Path
from tools.ripgrep_tool import RipgrepTool


def test_ripgrep_excludes_test_directories():
    """Test that ripgrep excludes test/, spec/, and test files."""
    # Create temporary project structure
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)

        # Create production code
        app_dir = project_root / "app" / "controllers"
        app_dir.mkdir(parents=True)
        (app_dir / "users_controller.rb").write_text("""
class UsersController < ApplicationController
  def create
    User.create(params)
  end
end
""")

        # Create test code (should be excluded)
        test_dir = project_root / "test" / "controllers"
        test_dir.mkdir(parents=True)
        (test_dir / "users_controller_test.rb").write_text("""
class UsersControllerTest < ActionController::TestCase
  def test_create
    User.create(params)
  end
end
""")

        # Create spec code (should be excluded)
        spec_dir = project_root / "spec" / "controllers"
        spec_dir.mkdir(parents=True)
        (spec_dir / "users_controller_spec.rb").write_text("""
RSpec.describe UsersController do
  it "creates user" do
    User.create(params)
  end
end
""")

        # Initialize ripgrep tool
        tool = RipgrepTool(project_root=str(project_root))

        # Search for "User.create"
        result = tool.execute({
            "pattern": "User.create",
            "file_types": ["rb"],
            "case_insensitive": True
        })

        # Should find matches
        assert result.get("total", 0) > 0, "Should find at least one match"

        matches = result.get("matches", [])

        # Verify NO test files in results
        for match in matches:
            file_path = match.get("file", "")

            # Should NOT contain test directories
            assert "test/" not in file_path, f"Found test file in results: {file_path}"
            assert "spec/" not in file_path, f"Found spec file in results: {file_path}"
            assert "tests/" not in file_path, f"Found tests file in results: {file_path}"

            # Should NOT end with _test.rb or _spec.rb
            assert not file_path.endswith("_test.rb"), f"Found _test.rb file: {file_path}"
            assert not file_path.endswith("_spec.rb"), f"Found _spec.rb file: {file_path}"

            # Should be production code (app/)
            assert "app/" in file_path, f"Should find production code: {file_path}"

        print(f"✓ Ripgrep correctly excluded test files")
        print(f"  Found {len(matches)} match(es) in production code only")
        print(f"  Files: {[m['file'] for m in matches]}")


def test_ripgrep_production_focus():
    """Test that ripgrep description clearly indicates production-only search."""
    tool = RipgrepTool(project_root="/tmp")

    description = tool.description

    # Should mention excluding tests
    assert "production code only" in description.lower() or "excludes test" in description.lower(), \
        "Description should mention that tests are excluded"

    print(f"✓ Ripgrep description indicates production-only search")
    print(f"  Description: {description}")


if __name__ == "__main__":
    test_ripgrep_excludes_test_directories()
    test_ripgrep_production_focus()

    print("\n" + "="*50)
    print("All ripgrep test exclusion tests passed! ✓")
    print("="*50)
