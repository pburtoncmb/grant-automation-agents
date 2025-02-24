import pytest
from core.config import validate_env, OPENAI_API_KEY, ANTHROPIC_API_KEY

def test_environment_variables():
    """Test that required environment variables are loaded."""
    assert OPENAI_API_KEY is not None, "OpenAI API key not found"
    assert ANTHROPIC_API_KEY is not None, "Anthropic API key not found"
    
def test_validate_env():
    """Test that environment validation works."""
    validate_env()  # Should not raise an error if .env is properly configured
