"""
Tests for FileReaderTool.
"""
import pytest
import tempfile
from pathlib import Path
from tools.file_reader_tool import FileReaderTool


class TestFileReaderTool:
    """Test FileReaderTool functionality."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project with test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create test files
            test_file = project_root / "test.rb"
            test_file.write_text(
                "# Test file\n"
                "class User\n"
                "  def initialize(name)\n"
                "    @name = name\n"
                "  end\n"
                "\n"
                "  def greet\n"
                "    puts \"Hello, #{@name}\"\n"
                "  end\n"
                "end\n"
            )

            # Create nested file
            subdir = project_root / "app" / "models"
            subdir.mkdir(parents=True)
            nested_file = subdir / "product.rb"
            nested_file.write_text("class Product\nend\n")

            yield project_root

    def test_initialization(self, temp_project):
        """Test FileReaderTool initialization."""
        tool = FileReaderTool(str(temp_project))
        assert tool.name == "file_reader"
        assert tool.project_root == str(temp_project)

    def test_tool_properties(self, temp_project):
        """Test tool has required properties."""
        tool = FileReaderTool(str(temp_project))
        assert tool.name
        assert tool.description
        assert tool.parameters
        assert "properties" in tool.parameters
        assert "file_path" in tool.parameters["properties"]

    def test_read_entire_file(self, temp_project):
        """Test reading an entire file."""
        tool = FileReaderTool(str(temp_project))
        result = tool.execute({"file_path": "test.rb"})

        assert "content" in result
        assert "total_lines" in result
        assert result["total_lines"] == 10
        assert "class User" in result["content"]
        assert "def greet" in result["content"]

    def test_read_line_range(self, temp_project):
        """Test reading a specific line range."""
        tool = FileReaderTool(str(temp_project))
        result = tool.execute({
            "file_path": "test.rb",
            "line_start": 2,
            "line_end": 5
        })

        assert "content" in result
        assert result["lines_shown"] == 4
        assert result["line_range"] == [2, 5]
        assert "class User" in result["content"]
        assert "greet" not in result["content"]  # Line 7, outside range

    def test_read_from_line_start(self, temp_project):
        """Test reading from a specific line to end."""
        tool = FileReaderTool(str(temp_project))
        result = tool.execute({
            "file_path": "test.rb",
            "line_start": 7
        })

        assert "content" in result
        assert result["line_range"][0] == 7
        assert "def greet" in result["content"]

    def test_read_nested_file(self, temp_project):
        """Test reading a file in subdirectory."""
        tool = FileReaderTool(str(temp_project))
        result = tool.execute({"file_path": "app/models/product.rb"})

        assert "content" in result
        assert "class Product" in result["content"]

    def test_file_not_found(self, temp_project):
        """Test error when file doesn't exist."""
        tool = FileReaderTool(str(temp_project))
        result = tool.execute({"file_path": "nonexistent.rb"})

        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_path_outside_project(self, temp_project):
        """Test security: reject paths outside project root."""
        tool = FileReaderTool(str(temp_project))
        result = tool.execute({"file_path": "../../../etc/passwd"})

        assert "error" in result
        assert "outside project root" in result["error"].lower()

    def test_invalid_line_range(self, temp_project):
        """Test error when line_end < line_start."""
        tool = FileReaderTool(str(temp_project))
        result = tool.execute({
            "file_path": "test.rb",
            "line_start": 5,
            "line_end": 2
        })

        assert "error" in result
        assert "invalid range" in result["error"].lower()

    def test_line_start_exceeds_file_length(self, temp_project):
        """Test error when starting line is beyond file length."""
        tool = FileReaderTool(str(temp_project))
        result = tool.execute({
            "file_path": "test.rb",
            "line_start": 100
        })

        assert "error" in result
        assert "exceeds file length" in result["error"].lower()

    def test_validate_input_valid(self, temp_project):
        """Test input validation with valid parameters."""
        tool = FileReaderTool(str(temp_project))
        assert tool.validate_input({"file_path": "test.rb"})
        assert tool.validate_input({
            "file_path": "test.rb",
            "line_start": 1,
            "line_end": 10
        })

    def test_validate_input_invalid(self, temp_project):
        """Test input validation with invalid parameters."""
        tool = FileReaderTool(str(temp_project))
        assert not tool.validate_input({})  # Missing file_path
        assert not tool.validate_input({"file_path": ""})  # Empty path
        assert not tool.validate_input({
            "file_path": "test.rb",
            "line_start": 0  # Invalid: must be >= 1
        })
        assert not tool.validate_input({
            "file_path": "test.rb",
            "line_start": "not a number"
        })

    def test_format_result(self, temp_project):
        """Test result formatting for LLM."""
        tool = FileReaderTool(str(temp_project))
        result = tool.execute({"file_path": "test.rb"})
        formatted = tool.format_result(result)

        assert isinstance(formatted, str)
        assert "## File:" in formatted
        assert "test.rb" in formatted
        assert "```ruby" in formatted
        assert "class User" in formatted

    def test_format_error_result(self, temp_project):
        """Test formatting of error results."""
        tool = FileReaderTool(str(temp_project))
        result = {"error": "File not found"}
        formatted = tool.format_result(result)

        assert "Error:" in formatted
        assert "File not found" in formatted

    def test_max_lines_truncation(self, temp_project):
        """Test that large files are truncated to MAX_LINES."""
        # Create file with more than MAX_LINES lines
        large_file = temp_project / "large.rb"
        lines = [f"# Line {i}\n" for i in range(1000)]
        large_file.write_text("".join(lines))

        tool = FileReaderTool(str(temp_project))
        result = tool.execute({"file_path": "large.rb"})

        assert result["truncated"] is True
        assert result["lines_shown"] == tool.MAX_LINES
        assert "message" in result

    def test_directory_path_rejected(self, temp_project):
        """Test that directory paths are rejected."""
        tool = FileReaderTool(str(temp_project))
        result = tool.execute({"file_path": "app"})

        assert "error" in result
        assert "not a file" in result["error"].lower()

    def test_debug_mode(self, temp_project):
        """Test tool works with debug mode enabled."""
        tool = FileReaderTool(str(temp_project), debug=True)
        result = tool.execute({"file_path": "test.rb"})

        assert "content" in result
        # Debug output goes to console, not return value

    def test_line_numbers_in_output(self, temp_project):
        """Test that output includes line numbers."""
        tool = FileReaderTool(str(temp_project))
        result = tool.execute({"file_path": "test.rb"})

        content = result["content"]
        assert "1 |" in content or "    1 |" in content  # Line number format
        assert "2 |" in content or "    2 |" in content

    def test_auto_load_small_file(self, temp_project):
        """Test that small files are auto-loaded entirely without truncation."""
        # Create a file under AUTO_LOAD_THRESHOLD (300 lines)
        small_file = temp_project / "small.rb"
        lines = [f"# Line {i}\n" for i in range(200)]
        small_file.write_text("".join(lines))

        tool = FileReaderTool(str(temp_project))
        result = tool.execute({"file_path": "small.rb"})

        # Should load entire file without truncation
        assert result["truncated"] is False
        assert result["total_lines"] == 200
        assert result["lines_shown"] == 200
        assert result["line_range"] == [1, 200]

    def test_auto_load_threshold_boundary(self, temp_project):
        """Test auto-load at exactly AUTO_LOAD_THRESHOLD lines."""
        # Create file at exactly 300 lines (the threshold)
        boundary_file = temp_project / "boundary.rb"
        lines = [f"# Line {i}\n" for i in range(300)]
        boundary_file.write_text("".join(lines))

        tool = FileReaderTool(str(temp_project))
        result = tool.execute({"file_path": "boundary.rb"})

        # Should load entire file (threshold is inclusive)
        assert result["truncated"] is False
        assert result["lines_shown"] == 300

    def test_no_auto_load_over_threshold(self, temp_project):
        """Test files over AUTO_LOAD_THRESHOLD use MAX_LINES limit."""
        # Create file just over AUTO_LOAD_THRESHOLD but under MAX_LINES
        # This verifies the threshold check works (not auto-loaded)
        medium_file = temp_project / "medium.rb"
        lines = [f"# Line {i}\n" for i in range(350)]
        medium_file.write_text("".join(lines))

        tool = FileReaderTool(str(temp_project))
        result = tool.execute({"file_path": "medium.rb"})

        # File is 350 lines, over threshold (300) but under MAX_LINES (500)
        # So it reads all 350 lines via MAX_LINES path, not auto-load
        assert result["total_lines"] == 350
        assert result["lines_shown"] == 350  # All lines since < MAX_LINES
        assert result["truncated"] is False  # Not truncated since < MAX_LINES

    def test_auto_load_disabled_with_line_range(self, temp_project):
        """Test that auto-load doesn't apply when line range is specified."""
        # Create a small file
        small_file = temp_project / "small_range.rb"
        lines = [f"# Line {i}\n" for i in range(100)]
        small_file.write_text("".join(lines))

        tool = FileReaderTool(str(temp_project))
        # Specify a line range - should only read that range
        result = tool.execute({
            "file_path": "small_range.rb",
            "line_start": 10,
            "line_end": 20
        })

        assert result["lines_shown"] == 11  # Lines 10-20 inclusive
        assert result["line_range"] == [10, 20]