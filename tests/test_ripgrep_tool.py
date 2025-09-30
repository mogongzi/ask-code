"""
Tests for tools.ripgrep_tool.RipgrepTool
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import subprocess
from pathlib import Path

from tools.ripgrep_tool import RipgrepTool


class TestRipgrepTool:
    """Test suite for RipgrepTool."""

    def test_initialization(self, temp_project_root):
        """Test tool initialization."""
        tool = RipgrepTool(temp_project_root, debug=False)

        assert tool.name == "ripgrep"
        assert tool.project_root == temp_project_root
        assert tool.debug_enabled is False

    def test_tool_properties(self):
        """Test tool properties."""
        tool = RipgrepTool()

        assert tool.name == "ripgrep"
        assert "Fast text search" in tool.description
        assert isinstance(tool.parameters, dict)
        assert tool.parameters["type"] == "object"

    def test_parameters_schema(self):
        """Test parameter schema is correctly defined."""
        tool = RipgrepTool()
        params = tool.parameters

        assert "properties" in params
        assert "pattern" in params["properties"]
        assert "file_types" in params["properties"]
        assert "context" in params["properties"]
        assert "max_results" in params["properties"]
        assert "case_insensitive" in params["properties"]

        # Check required fields
        assert "required" in params
        assert "pattern" in params["required"]

        # Check defaults
        assert params["properties"]["file_types"]["default"] == ["rb"]
        assert params["properties"]["context"]["default"] == 2
        assert params["properties"]["max_results"]["default"] == 20
        assert params["properties"]["case_insensitive"]["default"] is True

    def test_validate_input_valid(self):
        """Test input validation with valid parameters."""
        tool = RipgrepTool()

        # Minimal valid input
        assert tool.validate_input({"pattern": "test"}) is True

        # Full valid input
        assert tool.validate_input({
            "pattern": "test",
            "file_types": ["rb", "py"],
            "context": 3,
            "max_results": 50,
            "case_insensitive": False
        }) is True

    def test_validate_input_invalid(self):
        """Test input validation with invalid parameters."""
        tool = RipgrepTool()

        # Missing pattern
        assert tool.validate_input({}) is False
        assert tool.validate_input({"file_types": ["rb"]}) is False

        # Invalid pattern type
        assert tool.validate_input({"pattern": None}) is False
        assert tool.validate_input({"pattern": 123}) is False

        # Invalid file_types type
        assert tool.validate_input({"pattern": "test", "file_types": "rb"}) is False

    def test_execute_no_project_root(self):
        """Test execution without project root."""
        tool = RipgrepTool()
        result = tool.execute({"pattern": "test"})

        assert "error" in result
        assert "Project root not found" in result["error"]

    def test_execute_invalid_project_root(self):
        """Test execution with invalid project root."""
        tool = RipgrepTool("/nonexistent/path")
        result = tool.execute({"pattern": "test"})

        assert "error" in result
        assert "Project root not found" in result["error"]

    def test_execute_missing_pattern(self, temp_project_root):
        """Test execution with missing pattern."""
        tool = RipgrepTool(temp_project_root)
        result = tool.execute({})

        assert "error" in result
        assert "Pattern is required" in result["error"]

    @patch('subprocess.run')
    def test_execute_successful_search(self, mock_run, temp_project_root):
        """Test successful ripgrep execution."""
        # Mock successful ripgrep output
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "app/models/user.rb:5:  validates :email, presence: true\napp/models/user.rb:6:  has_many :posts"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        tool = RipgrepTool(temp_project_root)
        result = tool.execute({
            "pattern": "validates",
            "file_types": ["rb"],
            "context": 1
        })

        assert "matches" in result
        assert "total" in result
        assert result["total"] == 2
        assert len(result["matches"]) == 2

        # Check first match
        first_match = result["matches"][0]
        assert first_match["file"].endswith("user.rb")
        assert first_match["line"] == 5
        assert "validates :email" in first_match["content"]

    @patch('subprocess.run')
    def test_execute_no_matches(self, mock_run, temp_project_root):
        """Test ripgrep execution with no matches."""
        # Mock no matches (return code 1)
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        tool = RipgrepTool(temp_project_root)
        result = tool.execute({"pattern": "nonexistent_pattern"})

        assert "matches" in result
        assert result["matches"] == []
        assert result["total"] == 0
        assert "No matches found" in result["message"]

    @patch('subprocess.run')
    def test_execute_ripgrep_error(self, mock_run, temp_project_root):
        """Test ripgrep execution with error."""
        # Mock ripgrep error (return code 2)
        mock_result = Mock()
        mock_result.returncode = 2
        mock_result.stdout = ""
        mock_result.stderr = "Error: Invalid regex pattern"
        mock_run.return_value = mock_result

        tool = RipgrepTool(temp_project_root)
        result = tool.execute({"pattern": "[invalid"})

        assert "error" in result
        assert "Ripgrep error" in result["error"]

    @patch('subprocess.run')
    def test_execute_timeout(self, mock_run, temp_project_root):
        """Test ripgrep execution timeout."""
        # Mock timeout exception
        mock_run.side_effect = subprocess.TimeoutExpired("rg", 10)

        tool = RipgrepTool(temp_project_root)
        result = tool.execute({"pattern": "test"})

        assert "error" in result
        assert "Search timed out" in result["error"]

    @patch('subprocess.run')
    def test_execute_with_context(self, mock_run, temp_project_root):
        """Test ripgrep execution with context lines."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "app/models/user.rb:5:  validates :email, presence: true"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        tool = RipgrepTool(temp_project_root)
        tool.execute({
            "pattern": "validates",
            "context": 3
        })

        # Verify ripgrep was called with correct context parameter
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "-C" in args
        assert "3" in args

    @patch('subprocess.run')
    def test_execute_case_sensitive(self, mock_run, temp_project_root):
        """Test ripgrep execution with case sensitivity."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        tool = RipgrepTool(temp_project_root)
        tool.execute({
            "pattern": "Test",
            "case_insensitive": False
        })

        # Verify ripgrep was called without -i flag
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "-i" not in args

    @patch('subprocess.run')
    def test_execute_case_insensitive(self, mock_run, temp_project_root):
        """Test ripgrep execution with case insensitivity."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        tool = RipgrepTool(temp_project_root)
        tool.execute({
            "pattern": "test",
            "case_insensitive": True
        })

        # Verify ripgrep was called with -i flag
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "-i" in args

    @patch('subprocess.run')
    def test_execute_multiple_file_types(self, mock_run, temp_project_root):
        """Test ripgrep execution with multiple file types."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        tool = RipgrepTool(temp_project_root)
        tool.execute({
            "pattern": "test",
            "file_types": ["rb", "py", "js"]
        })

        # Verify ripgrep was called with correct file type filters
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]

        # Should have type-add and type for each file type
        assert args.count("--type-add") == 3
        assert args.count("--type") == 3
        assert "target:*.rb" in " ".join(args)
        assert "target:*.py" in " ".join(args)
        assert "target:*.js" in " ".join(args)

    def test_parse_ripgrep_output(self, temp_project_root):
        """Test parsing of ripgrep output."""
        tool = RipgrepTool(temp_project_root)

        output = """app/models/user.rb:5:  validates :email, presence: true
app/controllers/users_controller.rb:10:    @user = User.find(params[:id])
lib/helpers/auth.rb:15:  def authenticate_user"""

        matches = tool._parse_ripgrep_output(output, max_results=10)

        assert len(matches) == 3

        # Check first match
        assert matches[0]["file"] == "app/models/user.rb"
        assert matches[0]["line"] == 5
        assert "validates :email" in matches[0]["content"]

        # Check second match
        assert matches[1]["file"] == "app/controllers/users_controller.rb"
        assert matches[1]["line"] == 10
        assert "@user = User.find" in matches[1]["content"]

    def test_parse_ripgrep_output_max_results(self, temp_project_root):
        """Test parsing with max results limit."""
        tool = RipgrepTool(temp_project_root)

        output = "\n".join([f"file{i}.rb:{i}:content{i}" for i in range(1, 11)])

        matches = tool._parse_ripgrep_output(output, max_results=5)

        assert len(matches) == 5
        assert matches[0]["file"] == "file1.rb"
        assert matches[4]["file"] == "file5.rb"

    def test_parse_ripgrep_output_invalid_lines(self, temp_project_root):
        """Test parsing with invalid lines in output."""
        tool = RipgrepTool(temp_project_root)

        output = """app/models/user.rb:5:  validates :email, presence: true
invalid line without colons
app/controllers/users_controller.rb:invalid_line_number:content
app/views/users/show.rb:10:  render :show"""

        matches = tool._parse_ripgrep_output(output, max_results=10)

        # Should only parse valid lines (first and last)
        assert len(matches) == 2
        assert matches[0]["file"] == "app/models/user.rb"
        assert matches[1]["file"] == "app/views/users/show.rb"

    @patch('subprocess.run')
    def test_debug_logging(self, mock_run, temp_project_root):
        """Test debug logging when debug is enabled."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "test output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        tool = RipgrepTool(temp_project_root, debug=True)

        with patch.object(tool, '_debug_log') as mock_debug:
            tool.execute({"pattern": "test"})

            # Should have debug logging calls
            assert mock_debug.called

    def test_relative_path_conversion(self, temp_project_root):
        """Test conversion of absolute paths to relative paths."""
        tool = RipgrepTool(temp_project_root)

        # Create a full path output
        full_path = str(Path(temp_project_root) / "app" / "models" / "user.rb")
        output = f"{full_path}:5:  validates :email"

        matches = tool._parse_ripgrep_output(output, max_results=10)

        assert len(matches) == 1
        # Should be converted to relative path
        assert matches[0]["file"] == "app/models/user.rb"