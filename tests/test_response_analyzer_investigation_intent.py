"""
Test ResponseAnalyzer's ability to distinguish investigation intent from final answers.

This addresses the bug where responses like "I found X, let me examine it"
were incorrectly classified as final answers, causing premature agent termination.
"""
import pytest
from agent.response_analyzer import ResponseAnalyzer
from agent.state_machine import ReActState


@pytest.fixture
def analyzer():
    return ResponseAnalyzer()


@pytest.fixture
def react_state():
    state = ReActState()
    state.record_tool_usage("transaction_analyzer")
    return state


def test_investigation_intent_not_final(analyzer, react_state):
    """Test that 'let me examine' responses are NOT treated as final."""
    response = """
    I found a high-confidence match! Let me examine the lib/page_view_helper.rb file
    which was identified as the main source.
    """

    result = analyzer.analyze_response(response, react_state, step=2)

    assert not result.is_final, "Response with 'let me examine' should NOT be final"
    assert "investigate further" in result.reason.lower()


def test_various_investigation_patterns_not_final(analyzer, react_state):
    """Test various investigation intent patterns."""
    investigation_responses = [
        "I found the file. Let me read it to get the full context.",
        "The transaction analyzer identified the source. I'll examine it now.",
        "Found a match! I will check the file contents.",
        "Located the code. Let's analyze the specific implementation.",
        "I'm going to investigate the PageViewHelper module.",
        "Need to examine the callback chain more closely.",
        "Should look at the model associations next.",
        "The file which was identified as the primary source needs review.",
    ]

    for response in investigation_responses:
        result = analyzer.analyze_response(response, react_state, step=2)
        assert not result.is_final, f"Should NOT be final: {response[:50]}..."
        assert "investigate further" in result.reason.lower()


def test_true_final_answer_detected(analyzer, react_state):
    """Test that actual final answers ARE detected."""
    final_response = """
    ## 🎯 EXACT MATCH FOUND

    **File**: `lib/page_view_helper.rb`
    **Line**: 4
    **Code**: `ActiveRecord::Base.transaction do`

    ### Analysis Details

    This transaction wraps the page view creation with audit logging callbacks.

    ### Execution Flow

    1. User views a LayoutPage (ID: 415024)
    2. WorkPagesController#show_as_tab executes
    3. Line 4: PageViewHelper.log_page_view creates transaction
    4. PageView.create triggers after_save callbacks
    5. Audit trail INSERTs cascade through callbacks

    **Confidence**: Very High (6/8 column match)
    """

    result = analyzer.analyze_response(final_response, react_state, step=3)

    assert result.is_final, "Comprehensive answer with code should be final"
    assert result.has_concrete_results


def test_found_without_intent_is_final(analyzer, react_state):
    """Test that 'found' without investigation intent IS final."""
    response = """
    I found the exact source code at lib/page_view_helper.rb:4

    The code shows:
    ```ruby
    ActiveRecord::Base.transaction do
      page_view = PageView.new(...)
    end
    ```

    This matches the transaction in the SQL log.
    """

    result = analyzer.analyze_response(response, react_state, step=3)

    # This should be final because it has "I found the source code at"
    # and concrete results without investigation intent
    assert result.is_final, "Complete answer with code location should be final"


def test_partial_match_with_intent_not_final(analyzer, react_state):
    """Test edge case: partial 'found' match with investigation intent."""
    response = """
    I found several potential matches. Let me examine each one to determine
    which is the actual source of this SQL query.
    """

    result = analyzer.analyze_response(response, react_state, step=2)

    assert not result.is_final, "Partial findings requiring investigation should NOT be final"


def test_emoji_found_with_intent_not_final(analyzer, react_state):
    """Test that emoji + FOUND + investigation intent is NOT final."""
    response = """
    🎯 FOUND potential source!

    Let me examine the file to confirm this is the right match.
    """

    result = analyzer.analyze_response(response, react_state, step=2)

    assert not result.is_final, "Emoji + FOUND with investigation intent should NOT be final"


def test_emoji_found_without_intent_is_final(analyzer, react_state):
    """Test that emoji + FOUND + concrete results IS final."""
    response = """
    🎯 FOUND: lib/page_view_helper.rb:4

    The exact code:
    ```ruby
    ActiveRecord::Base.transaction do
      PageView.create(...)
    end
    ```

    Confidence: High
    """

    result = analyzer.analyze_response(response, react_state, step=3)

    assert result.is_final, "Emoji + FOUND with concrete results should be final"


def test_case_insensitive_investigation_detection(analyzer, react_state):
    """Test that investigation intent detection is case-insensitive."""
    responses = [
        "I FOUND it! LET ME EXAMINE the file.",
        "Found match. Will CHECK the implementation.",
        "Located source. Going To ANALYZE it now.",
    ]

    for response in responses:
        result = analyzer.analyze_response(response, react_state, step=2)
        assert not result.is_final, f"Case variations should be detected: {response}"


def test_no_false_negatives(analyzer, react_state):
    """Test that we don't incorrectly keep going when we should stop."""
    # These should all be final
    final_responses = [
        "I found the source code at lib/foo.rb:10. The code is...",
        "The exact code that generates this SQL is in app/models/user.rb",
        "Located the Rails code in app/controllers/users_controller.rb",
        "## Final Answer\n\nThe source is...",
        "## Conclusion\n\nBased on my analysis...",
    ]

    for response in final_responses:
        result = analyzer.analyze_response(response, react_state, step=3)
        assert result.is_final, f"Should be final: {response[:50]}..."


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
