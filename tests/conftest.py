"""
Test configuration and fixtures for ride_rails tests.
"""
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock

# Add parent directory to Python path for imports
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def temp_project_root():
    """Create a temporary directory structure for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir)

        # Create basic Rails structure
        (project_root / "app" / "models").mkdir(parents=True)
        (project_root / "app" / "controllers").mkdir(parents=True)
        (project_root / "app" / "views").mkdir(parents=True)
        (project_root / "config").mkdir()
        (project_root / "db").mkdir()

        # Create some sample files
        (project_root / "app" / "models" / "user.rb").write_text("""
class User < ApplicationRecord
  has_many :posts
  validates :email, presence: true
end
""")

        (project_root / "app" / "controllers" / "users_controller.rb").write_text("""
class UsersController < ApplicationController
  def index
    @users = User.all
  end

  def show
    @user = User.find(params[:id])
  end
end
""")

        (project_root / "config" / "routes.rb").write_text("""
Rails.application.routes.draw do
  resources :users
end
""")

        yield str(project_root)


@pytest.fixture
def mock_console():
    """Mock console for testing."""
    return Mock()


@pytest.fixture
def mock_session():
    """Mock session for testing."""
    session = Mock()
    session.usage_tracker = Mock()
    session.streaming_client = Mock()
    return session


@pytest.fixture
def sample_config():
    """Sample agent configuration for testing."""
    from agent.config import AgentConfig
    return AgentConfig(
        project_root="/test/project",
        max_react_steps=5,
        debug_enabled=True,
        log_level="DEBUG"
    )


@pytest.fixture
def mock_ripgrep_output():
    """Sample ripgrep output for testing."""
    return """app/models/user.rb:5:  validates :email, presence: true
app/models/user.rb:6:  has_many :posts
app/controllers/users_controller.rb:10:    @user = User.find(params[:id])"""


class MockSubprocessResult:
    """Mock subprocess result for testing."""
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def mock_subprocess_success():
    """Mock successful subprocess result."""
    return MockSubprocessResult(
        returncode=0,
        stdout="app/models/user.rb:5:  validates :email, presence: true\n"
    )


@pytest.fixture
def mock_subprocess_no_matches():
    """Mock subprocess result with no matches."""
    return MockSubprocessResult(returncode=1, stdout="", stderr="")


@pytest.fixture
def mock_subprocess_error():
    """Mock subprocess result with error."""
    return MockSubprocessResult(
        returncode=2,
        stdout="",
        stderr="Error: Invalid pattern"
    )