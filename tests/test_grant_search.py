import pytest
from agents.grant_scout import GrantScout

def test_init():
    """Test GrantScout initialization."""
    agent = GrantScout()
    assert agent.name == "GrantScout"
    assert agent.description == "Analyzes RFPs and finds grant opportunities matching organization profiles"
