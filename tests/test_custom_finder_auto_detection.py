"""
Tests for CustomFinderDetector - Auto-detection of custom finder methods.

Validates that the detector can identify custom finder methods without relying on
hardcoded naming patterns (find_*, get_*, all_*).
"""
import pytest
import tempfile
from pathlib import Path
from tools.components.custom_finder_detector import CustomFinderDetector, MethodInfo
from tools.components.where_clause_matcher import WhereClauseParser


@pytest.fixture
def temp_rails_project():
    """Create a temporary Rails project structure with test models."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        models_dir = project_root / "app" / "models"
        models_dir.mkdir(parents=True, exist_ok=True)

        # Create a test model with various custom finder methods
        company_model = models_dir / "company.rb"
        company_model.write_text('''
class Company < ApplicationRecord
  has_many :members

  # Traditional naming (find_*, get_*, all_*)
  def find_all_active
    members.active
  end

  # Non-traditional naming (fetch_*, load_*, retrieve_*)
  def fetch_published_members
    members.where(published: true)
  end

  def load_recent_items
    items.where("created_at > ?", 1.week.ago).order(created_at: :desc)
  end

  def retrieve_pending_tasks
    tasks.where(status: 'pending')
  end

  # Custom naming without common prefixes
  def active_members_list
    members.active.order(id: :asc)
  end

  def published_posts
    posts.where(published: true)
  end

  # Method that does NOT return a relation (should be ignored)
  def calculate_total
    members.sum(:revenue)
  end

  def member_count
    members.count
  end

  # Standard ActiveRecord method override (should be ignored)
  def all
    super.where(archived: false)
  end
end
''')

        # Create another test model
        user_model = models_dir / "user.rb"
        user_model.write_text('''
class User < ApplicationRecord
  has_many :posts

  def get_published_posts
    posts.where(published: true)
  end

  def fetch_drafts
    posts.where(status: 'draft')
  end
end
''')

        yield project_root


class TestCustomFinderDetector:
    """Test CustomFinderDetector class."""

    def test_detect_traditional_find_naming(self, temp_rails_project):
        """Detect custom finders with traditional find_* naming."""
        detector = CustomFinderDetector(project_root=str(temp_rails_project))

        method_body = detector.get_method_body("Company", "find_all_active")
        assert method_body is not None
        assert "members.active" in method_body

    def test_detect_fetch_naming(self, temp_rails_project):
        """Detect custom finders with fetch_* naming."""
        detector = CustomFinderDetector(project_root=str(temp_rails_project))

        method_body = detector.get_method_body("Company", "fetch_published_members")
        assert method_body is not None
        assert "where(published: true)" in method_body

    def test_detect_load_naming(self, temp_rails_project):
        """Detect custom finders with load_* naming."""
        detector = CustomFinderDetector(project_root=str(temp_rails_project))

        method_body = detector.get_method_body("Company", "load_recent_items")
        assert method_body is not None
        assert "items.where" in method_body

    def test_detect_retrieve_naming(self, temp_rails_project):
        """Detect custom finders with retrieve_* naming."""
        detector = CustomFinderDetector(project_root=str(temp_rails_project))

        method_body = detector.get_method_body("Company", "retrieve_pending_tasks")
        assert method_body is not None
        assert "tasks.where" in method_body

    def test_detect_custom_naming_without_prefix(self, temp_rails_project):
        """Detect custom finders with arbitrary naming (no standard prefix)."""
        detector = CustomFinderDetector(project_root=str(temp_rails_project))

        # active_members_list
        method_body = detector.get_method_body("Company", "active_members_list")
        assert method_body is not None
        assert "members.active" in method_body

        # published_posts
        method_body = detector.get_method_body("Company", "published_posts")
        assert method_body is not None
        assert "posts.where" in method_body

    def test_ignore_calculation_methods(self, temp_rails_project):
        """Should NOT detect methods that return calculations (sum, count, etc.)."""
        detector = CustomFinderDetector(project_root=str(temp_rails_project))

        # calculate_total returns a number, not a relation
        method_body = detector.get_method_body("Company", "calculate_total")
        assert method_body is None  # Should NOT be detected as custom finder

        # member_count returns a number, not a relation
        method_body = detector.get_method_body("Company", "member_count")
        assert method_body is None  # Should NOT be detected as custom finder

    def test_ignore_standard_activerecord_methods(self, temp_rails_project):
        """Should NOT detect standard ActiveRecord methods even if overridden."""
        detector = CustomFinderDetector(project_root=str(temp_rails_project))

        # 'all' is a standard ActiveRecord method
        method_body = detector.get_method_body("Company", "all")
        assert method_body is None  # Should be skipped

    def test_caching_works(self, temp_rails_project):
        """Should cache results to avoid re-parsing files."""
        detector = CustomFinderDetector(project_root=str(temp_rails_project))

        # First call - parses file
        method_body_1 = detector.get_method_body("Company", "find_all_active")

        # Second call - should use cache
        method_body_2 = detector.get_method_body("Company", "find_all_active")

        assert method_body_1 == method_body_2
        assert "Company" in detector._method_cache

    def test_analyze_model_returns_all_methods(self, temp_rails_project):
        """analyze_model should return all detected custom finders."""
        detector = CustomFinderDetector(project_root=str(temp_rails_project))

        model_file = temp_rails_project / "app" / "models" / "company.rb"
        methods = detector.analyze_model(str(model_file))

        # Should detect all custom finders
        assert "find_all_active" in methods
        assert "fetch_published_members" in methods
        assert "load_recent_items" in methods
        assert "retrieve_pending_tasks" in methods
        assert "active_members_list" in methods
        assert "published_posts" in methods

        # Should NOT include calculation methods
        assert "calculate_total" not in methods or not methods["calculate_total"].returns_relation
        assert "member_count" not in methods or not methods["member_count"].returns_relation


class TestWhereClauseParserIntegration:
    """Test WhereClauseParser integration with CustomFinderDetector."""

    def test_parse_traditional_find_naming(self, temp_rails_project):
        """Should parse custom finders with traditional find_* naming."""
        parser = WhereClauseParser(project_root=str(temp_rails_project))

        code = "company.find_all_active.offset(10).limit(20)"
        conditions = parser.parse_ruby_code(code)

        # Should extract: company_id (from association) + conditions from 'active' scope
        assert len(conditions) >= 1  # At least company_id
        assert any(c.column == "company_id" for c in conditions)

    def test_parse_fetch_naming(self, temp_rails_project):
        """Should parse custom finders with fetch_* naming."""
        parser = WhereClauseParser(project_root=str(temp_rails_project))

        code = "company.fetch_published_members.offset(10).limit(20)"
        conditions = parser.parse_ruby_code(code)

        # Should extract: company_id + published condition
        assert len(conditions) >= 1
        assert any(c.column == "company_id" for c in conditions)

    def test_parse_load_naming(self, temp_rails_project):
        """Should parse custom finders with load_* naming."""
        parser = WhereClauseParser(project_root=str(temp_rails_project))

        code = "company.load_recent_items.offset(10).limit(20)"
        conditions = parser.parse_ruby_code(code)

        # Should extract: company_id (from association)
        assert len(conditions) >= 1
        assert any(c.column == "company_id" for c in conditions)

    def test_parse_custom_naming_without_prefix(self, temp_rails_project):
        """Should parse custom finders with arbitrary naming (no standard prefix)."""
        parser = WhereClauseParser(project_root=str(temp_rails_project))

        code = "company.active_members_list.offset(10).limit(20)"
        conditions = parser.parse_ruby_code(code)

        # Should extract: company_id + conditions from 'active' scope
        assert len(conditions) >= 1
        assert any(c.column == "company_id" for c in conditions)

    def test_parse_preserves_method_chain(self, temp_rails_project):
        """Should preserve the rest of the method chain after custom finder."""
        parser = WhereClauseParser(project_root=str(temp_rails_project))

        # Complex chain with offset, limit, order
        code = "company.find_all_active.offset((page-1)*page_size).limit(page_size).order(id: :asc)"
        conditions = parser.parse_ruby_code(code)

        # Should still extract conditions (method chain should be preserved during expansion)
        assert len(conditions) >= 1
        assert any(c.column == "company_id" for c in conditions)

    def test_parse_stops_at_comment(self, temp_rails_project):
        """Should stop parsing at inline comments."""
        parser = WhereClauseParser(project_root=str(temp_rails_project))

        code = "company.find_all_active.offset(10) # pagination"
        conditions = parser.parse_ruby_code(code)

        # Should extract conditions without including comment
        assert len(conditions) >= 1
        assert any(c.column == "company_id" for c in conditions)

    def test_parse_stops_at_block(self, temp_rails_project):
        """Should stop parsing at block syntax."""
        parser = WhereClauseParser(project_root=str(temp_rails_project))

        code = "company.find_all_active.map { |m| m.id }"
        conditions = parser.parse_ruby_code(code)

        # Should extract conditions without including block
        assert len(conditions) >= 1
        assert any(c.column == "company_id" for c in conditions)

    def test_ignore_standard_activerecord_methods(self, temp_rails_project):
        """Should NOT treat standard ActiveRecord methods as custom finders."""
        parser = WhereClauseParser(project_root=str(temp_rails_project))

        # Standard AR methods should NOT be expanded
        code = "Company.where(active: true).limit(10)"
        conditions = parser.parse_ruby_code(code)

        # Should only extract the where condition, not try to expand 'where' as a custom finder
        assert any(c.column == "active" for c in conditions)

    def test_backward_compatibility_with_existing_code(self, temp_rails_project):
        """Existing code with find_* methods should still work."""
        parser = WhereClauseParser(project_root=str(temp_rails_project))

        # This is the exact code from alert_mailer.rb:180
        code = "company.find_all_active.offset((page-1)*page_size).limit(page_size).order(id: :asc)"
        conditions = parser.parse_ruby_code(code)

        # Should extract: company_id + conditions from 'active' scope
        # Expected: 5 conditions (1 company_id + 4 from Member.active scope)
        assert len(conditions) >= 1
        assert any(c.column == "company_id" for c in conditions)


class TestMethodBodyAnalysis:
    """Test method body analysis heuristics."""

    def test_detect_where_clause(self, temp_rails_project):
        """Should detect methods with .where() calls."""
        detector = CustomFinderDetector(project_root=str(temp_rails_project))

        method_body = "members.where(published: true)"
        assert detector._is_custom_finder_method(method_body) is True

    def test_detect_joins_clause(self, temp_rails_project):
        """Should detect methods with .joins() calls."""
        detector = CustomFinderDetector(project_root=str(temp_rails_project))

        method_body = "posts.joins(:author).where(authors: {active: true})"
        assert detector._is_custom_finder_method(method_body) is True

    def test_detect_scope_chain(self, temp_rails_project):
        """Should detect scope chains."""
        detector = CustomFinderDetector(project_root=str(temp_rails_project))

        method_body = "members.active.published"
        assert detector._is_custom_finder_method(method_body) is True

    def test_detect_model_query(self, temp_rails_project):
        """Should detect direct Model queries."""
        detector = CustomFinderDetector(project_root=str(temp_rails_project))

        method_body = "Member.where(active: true)"
        assert detector._is_custom_finder_method(method_body) is True

    def test_ignore_calculation_methods(self, temp_rails_project):
        """Should NOT detect calculation methods."""
        detector = CustomFinderDetector(project_root=str(temp_rails_project))

        # Just a sum/count - not a relation
        assert detector._is_custom_finder_method("members.sum(:revenue)") is False
        assert detector._is_custom_finder_method("members.count") is False

        # Pure computation
        assert detector._is_custom_finder_method("revenue * 0.1") is False
        assert detector._is_custom_finder_method("name.upcase") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
