import pytest
import os
from pathlib import Path
import asyncio

from agents.grant_scout import GrantScout

# Path to sample data
SAMPLE_DIR = Path(__file__).parent.parent / "data" / "samples"

@pytest.fixture
def grant_scout():
    """Create a GrantScout instance for testing."""
    return GrantScout()

@pytest.fixture
def sample_rfp_text():
    """Load sample RFP text content."""
    sample_path = SAMPLE_DIR / "sample_rfp.txt"
    with open(sample_path, 'r', encoding='utf-8') as f:
        return f.read()

def test_init():
    """Test GrantScout initialization."""
    agent = GrantScout()
    assert agent.name == "GrantScout"
    assert agent.description == "Analyzes RFPs to extract requirements and scoring criteria"
    assert '.txt' in agent.supported_file_types

@pytest.mark.asyncio
async def test_validate_input_with_content(grant_scout):
    """Test input validation with raw content."""
    valid_input = {"content": "Sample RFP content"}
    assert await grant_scout.validate_input(valid_input) == True

@pytest.mark.asyncio
async def test_validate_input_with_file(grant_scout, tmp_path):
    """Test input validation with file path."""
    # Create a temporary text file
    test_file = tmp_path / "test_rfp.txt"
    test_file.write_text("Sample RFP content")
    
    valid_input = {"file_path": str(test_file)}
    assert await grant_scout.validate_input(valid_input) == True

@pytest.mark.asyncio
async def test_validate_input_invalid(grant_scout):
    """Test input validation with invalid input."""
    invalid_input = {}
    assert await grant_scout.validate_input(invalid_input) == False

@pytest.mark.asyncio
async def test_process_with_content(grant_scout, sample_rfp_text):
    """Test processing RFP content."""
    input_data = {"content": sample_rfp_text}
    result = await grant_scout.process(input_data)
    
    assert result["success"] == True
    assert "requirements" in result
    assert len(result["requirements"]) > 0

@pytest.mark.asyncio
async def test_analyze_document(grant_scout, sample_rfp_text):
    """Test document analysis functionality."""
    result = await grant_scout._analyze_document(sample_rfp_text)
    
    assert "requirements" in result
    # Our sample contains several requirements patterns
    assert len(result["requirements"]) > 0
