"""
Tests for Rails inflection helpers (singularization and table-to-model conversion).

Verifies that our implementation matches Rails ActiveSupport inflection rules.
"""
import pytest
from tools.components.rails_inflection import singularize, table_to_model


class TestSingularize:
    """Test singularize() function with Rails inflection rules."""

    def test_regular_plurals(self):
        """Test basic -s plurals."""
        assert singularize("users") == "user"
        assert singularize("posts") == "post"
        assert singularize("comments") == "comment"
        assert singularize("tags") == "tag"

    def test_irregular_plurals(self):
        """Test irregular plural forms."""
        assert singularize("people") == "person"
        assert singularize("men") == "man"
        assert singularize("children") == "child"
        assert singularize("sexes") == "sex"
        assert singularize("moves") == "move"
        assert singularize("zombies") == "zombie"

    def test_consonant_y_plurals(self):
        """Test consonant + y -> ies pattern."""
        assert singularize("categories") == "category"
        assert singularize("companies") == "company"
        assert singularize("stories") == "story"
        assert singularize("queries") == "query"

    def test_special_endings(self):
        """Test special endings (x, ch, ss, sh, o)."""
        assert singularize("boxes") == "box"
        assert singularize("churches") == "church"
        assert singularize("classes") == "class"
        assert singularize("dishes") == "dish"
        assert singularize("tomatoes") == "tomato"
        assert singularize("heroes") == "hero"

    def test_f_fe_plurals(self):
        """Test f/fe -> ves plurals."""
        assert singularize("knives") == "knife"
        assert singularize("wives") == "wife"
        assert singularize("lives") == "life"
        assert singularize("wolves") == "wolf"
        assert singularize("shelves") == "shelf"

    def test_mouse_mice(self):
        """Test mouse/mice irregular pattern."""
        assert singularize("mice") == "mouse"
        assert singularize("lice") == "louse"

    def test_us_i_plurals(self):
        """Test -us -> -i plurals (Latin)."""
        assert singularize("octopi") == "octopus"
        assert singularize("octopus") == "octopus"
        assert singularize("viri") == "virus"
        assert singularize("virus") == "virus"

    def test_is_es_plurals(self):
        """Test -is -> -es plurals (Greek)."""
        assert singularize("analyses") == "analysis"
        assert singularize("analysis") == "analysis"
        assert singularize("bases") == "basis"
        assert singularize("crises") == "crisis"
        assert singularize("diagnoses") == "diagnosis"
        assert singularize("theses") == "thesis"

    def test_ix_ex_plurals(self):
        """Test -ix/-ex -> -ices plurals."""
        assert singularize("matrices") == "matrix"
        assert singularize("vertices") == "vertex"
        assert singularize("indices") == "index"

    def test_um_a_plurals(self):
        """Test -um -> -a plurals (Latin)."""
        # Note: "data" is treated as uncountable in modern Rails
        assert singularize("criteria") == "criterium"

    def test_on_a_plurals(self):
        """Test -on -> -a plurals."""
        assert singularize("phenomena") == "phenomenon"

    def test_special_cases(self):
        """Test special edge cases."""
        assert singularize("oxen") == "ox"
        assert singularize("quizzes") == "quiz"
        assert singularize("buses") == "bus"
        assert singularize("aliases") == "alias"
        assert singularize("statuses") == "status"
        assert singularize("axes") == "axis"
        assert singularize("testes") == "testis"
        assert singularize("shoes") == "shoe"
        assert singularize("movies") == "movie"
        assert singularize("databases") == "database"

    def test_uncountables(self):
        """Test uncountable words (no change)."""
        assert singularize("equipment") == "equipment"
        assert singularize("information") == "information"
        assert singularize("rice") == "rice"
        assert singularize("money") == "money"
        assert singularize("species") == "species"
        assert singularize("series") == "series"
        assert singularize("fish") == "fish"
        assert singularize("sheep") == "sheep"
        assert singularize("jeans") == "jeans"
        assert singularize("police") == "police"

    def test_already_singular(self):
        """Test words that are already singular."""
        assert singularize("user") == "user"
        assert singularize("post") == "post"
        assert singularize("news") == "news"

    def test_empty_string(self):
        """Test empty string handling."""
        assert singularize("") == ""


class TestTableToModel:
    """Test table_to_model() function."""

    def test_basic_conversion(self):
        """Test basic table name to model conversion."""
        assert table_to_model("users") == "User"
        assert table_to_model("posts") == "Post"
        assert table_to_model("comments") == "Comment"

    def test_irregular_plurals(self):
        """Test irregular plurals in table names."""
        assert table_to_model("people") == "Person"
        assert table_to_model("children") == "Child"

    def test_complex_plurals(self):
        """Test complex plural patterns."""
        assert table_to_model("categories") == "Category"
        assert table_to_model("analyses") == "Analysis"
        assert table_to_model("mice") == "Mouse"
        assert table_to_model("octopi") == "Octopus"

    def test_underscore_names(self):
        """Test multi-word table names with underscores."""
        assert table_to_model("user_profiles") == "UserProfile"
        assert table_to_model("blog_posts") == "BlogPost"
        assert table_to_model("comment_replies") == "CommentReply"
        assert table_to_model("order_items") == "OrderItem"

    def test_schema_prefix(self):
        """Test table names with schema prefix."""
        assert table_to_model("public.users") == "User"
        assert table_to_model("myschema.categories") == "Category"
        assert table_to_model("dbo.people") == "Person"

    def test_uncountables(self):
        """Test uncountable table names."""
        assert table_to_model("equipment") == "Equipment"
        assert table_to_model("information") == "Information"
        assert table_to_model("series") == "Series"

    def test_special_cases(self):
        """Test special Rails table naming cases."""
        assert table_to_model("statuses") == "Status"
        assert table_to_model("aliases") == "Alias"
        assert table_to_model("databases") == "Database"

    def test_empty_string(self):
        """Test empty string handling."""
        assert table_to_model("") == ""

    def test_case_insensitive(self):
        """Test that input case doesn't matter."""
        assert table_to_model("USERS") == "User"
        assert table_to_model("Users") == "User"
        assert table_to_model("user_PROFILES") == "UserProfile"

    def test_real_world_examples(self):
        """Test real-world Rails table names."""
        assert table_to_model("active_storage_blobs") == "ActiveStorageBlob"
        assert table_to_model("action_text_rich_texts") == "ActionTextRichText"
        # metadata is uncountable in Rails
        assert table_to_model("ar_internal_metadata") == "ArInternalMetadata"
        assert table_to_model("schema_migrations") == "SchemaMigration"

    def test_uncountable_data_metadata(self):
        """Test that data/metadata are treated as uncountable."""
        assert singularize("data") == "data"
        assert singularize("metadata") == "metadata"
