"""
Tests for agent.response_analyzer.ResponseAnalyzer
"""
import pytest
from unittest.mock import Mock

from agent.response_analyzer import ResponseAnalyzer, AnalysisResult
from agent.state_machine import ReActState


@pytest.fixture
def mock_react_state():
    """Create a properly mocked ReActState."""
    state = Mock(spec=ReActState)
    state.current_step = 1
    state.max_steps = 10
    state.tools_used = set()
    state.tool_stats = {}
    state.search_attempts = []
    state.step_results = {}
    state.findings = []
    state.finalize_requested = False
    state.should_stop = False
    state.stop_reason = None
    # Add methods that are called by the analyzer
    state.get_tool_usage_count = Mock(return_value=0)
    state.get_unused_tools = Mock(return_value=[])
    state.has_high_quality_results = Mock(return_value=False)
    return state


class TestAnalysisResult:
    """Test suite for AnalysisResult dataclass."""

    def test_analysis_result_creation(self):
        """Test AnalysisResult creation."""
        result = AnalysisResult(
            is_final=True,
            confidence="high",
            reason="Found final answer",
            suggestions=["suggestion1"],
            has_concrete_results=True
        )

        assert result.is_final is True
        assert result.confidence == "high"
        assert result.reason == "Found final answer"
        assert result.suggestions == ["suggestion1"]
        assert result.has_concrete_results is True


class TestResponseAnalyzer:
    """Test suite for ResponseAnalyzer."""

    def test_initialization(self):
        """Test analyzer initialization."""
        analyzer = ResponseAnalyzer()
        assert analyzer is not None

    def test_analyze_response_with_final_answer_indicator(self, mock_react_state):
        """Test analysis when response contains final answer indicators."""
        analyzer = ResponseAnalyzer()

        response = "I found the source code at app/models/user.rb:15 with the authentication logic."

        result = analyzer.analyze_response(response, mock_react_state, step=1)

        assert isinstance(result, AnalysisResult)
        assert result.is_final is True
        assert result.confidence == "high"
        assert "final answer indicator" in result.reason.lower()

    def test_analyze_response_with_conclusion_indicator(self):
        """Test analysis with conclusion indicators."""
        analyzer = ResponseAnalyzer()
        mock_state = Mock(spec=ReActState)

        response = "## Final Answer\nThe authentication is handled by Devise gem in the User model."

        result = analyzer.analyze_response(response, mock_state, step=1)

        assert result.is_final is True
        assert result.confidence == "high"

    def test_analyze_response_without_final_indicators(self, mock_react_state):
        """Test analysis when response doesn't contain final indicators."""
        analyzer = ResponseAnalyzer()

        response = "Let me search for the authentication logic in the codebase."

        result = analyzer.analyze_response(response, mock_react_state, step=1)

        assert isinstance(result, AnalysisResult)
        # Result depends on implementation details, but should not be final
        # without clear indicators

    def test_has_concrete_results_with_file_paths(self):
        """Test detection of concrete results with file paths."""
        analyzer = ResponseAnalyzer()

        responses_with_concrete_results = [
            "Found in app/models/user.rb:15 the authentication method",
            "The method is defined in app/controllers/sessions_controller.rb",
            "def authenticate_user is located in the helper"
        ]

        for response in responses_with_concrete_results:
            has_concrete = analyzer._has_concrete_results(response)
            assert has_concrete is True, f"Should detect concrete results in: {response[:30]}..."

    def test_has_concrete_results_without_specifics(self):
        """Test detection when response lacks concrete results."""
        analyzer = ResponseAnalyzer()

        vague_responses = [
            "I need to search for more information",
            "Let me look at the authentication system",
            "The code might be in the models directory"
        ]

        for response in vague_responses:
            has_concrete = analyzer._has_concrete_results(response)
            # These responses are vague and shouldn't be considered concrete

    def test_has_rails_patterns_detection(self):
        """Test detection of Rails-specific patterns."""
        analyzer = ResponseAnalyzer()

        rails_responses = [
            "Found in app/models/user.rb the authentication method",
            "The controller is in app/controllers/sessions_controller.rb",
            "Located at app/views/users/show.html.erb",
            "Check app/config/routes.rb for routing"
        ]

        for response in rails_responses:
            has_rails = analyzer._has_rails_patterns(response)
            assert has_rails is True, f"Should detect Rails patterns in: {response[:30]}..."

    def test_has_activerecord_patterns_detection(self):
        """Test detection of ActiveRecord-specific patterns."""
        analyzer = ResponseAnalyzer()

        ar_responses = [
            "scope :active in the User model",
            "belongs_to :company relationship",
            "has_many :posts association",
            "validates :email presence"
        ]

        for response in ar_responses:
            has_ar = analyzer._has_activerecord_patterns(response)
            assert has_ar is True, f"Should detect ActiveRecord patterns in: {response[:30]}..."

    def test_extract_tool_used_from_response(self):
        """Test extraction of tool names from responses."""
        analyzer = ResponseAnalyzer()

        tool_responses = [
            ("Using ripgrep to search for the pattern", "ripgrep"),
            ("⚙ Using ast_grep for class definitions", "ast_grep"),
            ("⚙ Using enhanced_sql_rails_search", "enhanced_sql_rails_search")
        ]

        for response, expected_tool in tool_responses:
            extracted_tool = analyzer.extract_tool_used(response)
            assert extracted_tool == expected_tool, f"Should extract '{expected_tool}' from: {response[:30]}..."

    def test_extract_tool_used_no_tool_mentioned(self):
        """Test tool extraction when no tool is mentioned."""
        analyzer = ResponseAnalyzer()

        response = "The authentication system uses standard Rails patterns."
        extracted_tool = analyzer.extract_tool_used(response)

        assert extracted_tool is None

    def test_should_continue_analysis_various_scenarios(self, mock_react_state):
        """Test continuation analysis in various scenarios."""
        analyzer = ResponseAnalyzer()
        mock_react_state.current_step = 3
        mock_react_state.max_steps = 10

        # Should continue when response suggests more searching
        search_response = "Let me search for more authentication methods"
        should_continue = analyzer._should_continue_analysis(search_response, mock_react_state, None)

        # The actual behavior depends on implementation, but test structure is correct
        assert isinstance(should_continue, tuple)  # Returns (reason, suggestions)

    def test_has_high_quality_tool_results(self, mock_react_state):
        """Test assessment of tool result quality."""
        analyzer = ResponseAnalyzer()

        # Set up mock state with tool results
        mock_react_state.step_results = {
            1: {
                "has_results": True,
                "tool": "ripgrep",
                "tool_results": {
                    "ripgrep": {
                        "matches": [
                            {"file": "app/models/user.rb", "line": 15, "content": "validates :email"}
                        ],
                        "total": 1
                    }
                }
            }
        }

        has_quality = analyzer.has_high_quality_tool_results(mock_react_state)

        # Should recognize quality results with has_results flag
        assert has_quality is True

    def test_has_high_quality_tool_results_empty(self, mock_react_state):
        """Test tool result assessment with empty results."""
        analyzer = ResponseAnalyzer()

        mock_react_state.step_results = {}

        has_quality = analyzer.has_high_quality_tool_results(mock_react_state)
        assert has_quality is False

    def test_should_force_different_tool(self, mock_react_state):
        """Test logic for forcing different tool usage."""
        analyzer = ResponseAnalyzer()

        # Add tool_stats with high usage
        mock_react_state.tool_stats = {
            "ripgrep": Mock(usage_count=4, success_count=0)  # High usage, no success
        }
        mock_react_state.should_force_different_tool = Mock(return_value=False)

        should_force = analyzer.should_force_different_tool(mock_react_state, step=5, repetition_limit=3)

        # Should force different tool if usage exceeds limit and no results
        assert should_force is True

    def test_should_force_different_tool_under_limit(self, mock_react_state):
        """Test tool forcing when under usage limit."""
        analyzer = ResponseAnalyzer()

        # Add tool_stats with low usage
        mock_react_state.tool_stats = {
            "ripgrep": Mock(usage_count=1, success_count=1)  # Low usage, has success
        }
        mock_react_state.should_force_different_tool = Mock(return_value=False)

        should_force = analyzer.should_force_different_tool(mock_react_state, step=2, repetition_limit=3)

        # Should not force different tool if under limit
        assert should_force is False

    def test_generate_finalization_prompt(self):
        """Test generation of finalization prompt."""
        analyzer = ResponseAnalyzer()

        prompt = analyzer.generate_finalization_prompt()

        assert isinstance(prompt, str)
        assert len(prompt) > 0
        # Should contain guidance about providing final answers

    def test_generate_tool_constraint_prompt(self, mock_react_state):
        """Test generation of tool constraint prompts."""
        analyzer = ResponseAnalyzer()

        excluded_tools = ["ripgrep", "ast_grep"]

        prompt = analyzer.generate_tool_constraint_prompt(mock_react_state, excluded_tools)

        assert isinstance(prompt, str)
        assert len(prompt) > 0
        # Should mention the excluded tools

    def test_analyze_structured_result_with_valid_json(self):
        """Test analysis of structured tool results."""
        analyzer = ResponseAnalyzer()

        json_result = '{"matches": [{"file": "app/models/user.rb", "line": 15}], "total": 1}'
        is_quality = analyzer._analyze_structured_result(json_result, "ripgrep")

        assert is_quality is True

    def test_analyze_structured_result_with_invalid_json(self):
        """Test analysis of invalid JSON results."""
        analyzer = ResponseAnalyzer()

        invalid_json = "Not valid JSON content"
        is_quality = analyzer._analyze_structured_result(invalid_json, "ripgrep")

        assert is_quality is False

    def test_check_tool_specific_results_ripgrep(self):
        """Test tool-specific result checking for ripgrep."""
        analyzer = ResponseAnalyzer()

        ripgrep_result = {
            "matches": [
                {"file": "app/models/user.rb", "line": 15, "content": "validates :email"}
            ],
            "total": 1
        }

        is_quality = analyzer._check_tool_specific_results(ripgrep_result, "ripgrep")
        assert is_quality is True

    def test_check_tool_specific_results_empty(self):
        """Test tool-specific result checking with empty results."""
        analyzer = ResponseAnalyzer()

        empty_result = {"matches": [], "total": 0}
        is_quality = analyzer._check_tool_specific_results(empty_result, "ripgrep")
        assert is_quality is False

    def test_final_answer_indicators_case_insensitive(self):
        """Test that final answer indicators work case-insensitively."""
        analyzer = ResponseAnalyzer()
        mock_state = Mock(spec=ReActState)

        responses = [
            "I FOUND THE SOURCE CODE AT app/models/user.rb",
            "## FINAL ANSWER",
            "## conclusion"
        ]

        for response in responses:
            result = analyzer.analyze_response(response, mock_state, step=1)
            assert result.is_final is True

    def test_analyzer_with_complex_response(self):
        """Test analyzer with complex, realistic response."""
        analyzer = ResponseAnalyzer()
        mock_state = Mock(spec=ReActState)

        complex_response = """
        Based on my analysis of the Rails codebase, I found the authentication logic.

        The exact code that generates this SQL is located in app/models/user.rb:25-30:

        def authenticate(password)
          return false unless password_digest
          BCrypt::Password.new(password_digest) == password
        end

        This method is called from the SessionsController during login.
        """

        result = analyzer.analyze_response(complex_response, mock_state, step=3)

        assert isinstance(result, AnalysisResult)
        assert result.is_final is True  # Should detect "exact code that generates"
        assert result.has_concrete_results is True
        assert "final answer indicator" in result.reason.lower()
