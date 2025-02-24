import re
from typing import Dict, Any, List, Optional
import logging
from pathlib import Path

from agents.base_agent import BaseAgent
from core.config import OPENAI_API_KEY, ANTHROPIC_API_KEY

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GrantScout(BaseAgent):
    """
    Agent for analyzing grant RFPs and extracting requirements.
    
    This agent is responsible for:
    1. Parsing RFP documents (PDF, DOCX, TXT)
    2. Identifying key requirements and eligibility criteria
    3. Extracting deadlines and important dates
    4. Determining scoring criteria and priorities
    """
    
    def __init__(self):
        super().__init__(
            name="GrantScout",
            description="Analyzes RFPs to extract requirements and scoring criteria"
        )
        self.supported_file_types = ['.pdf', '.docx', '.txt']
        
    async def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """
        Validate that the input contains necessary information.
        
        Required:
        - file_path OR content: Path to RFP file or raw content
        
        Optional:
        - file_type: Type of file (for raw content)
        - sections_of_interest: List of specific sections to focus on
        """
        if not input_data:
            logger.error("Input data is empty")
            return False
            
        # Check if either file_path or content is provided
        if 'file_path' not in input_data and 'content' not in input_data:
            logger.error("Either file_path or content must be provided")
            return False
            
        # If file_path is provided, verify it exists and is supported
        if 'file_path' in input_data:
            file_path = Path(input_data['file_path'])
            if not file_path.exists():
                logger.error(f"File not found: {file_path}")
                return False
                
            if file_path.suffix.lower() not in self.supported_file_types:
                logger.error(f"Unsupported file type: {file_path.suffix}")
                return False
                
        return True
        
    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process RFP and extract requirements.
        """
        # Validate input
        if not await self.validate_input(input_data):
            return {"error": "Invalid input", "success": False}
            
        try:
            # Extract text from document
            document_text = await self._extract_text(input_data)
            
            # Process the document
            results = await self._analyze_document(document_text, input_data.get('sections_of_interest'))
            
            return {
                "success": True,
                "requirements": results.get("requirements", []),
                "eligibility": results.get("eligibility", []),
                "deadlines": results.get("deadlines", []),
                "scoring_criteria": results.get("scoring_criteria", [])
            }
        except Exception as e:
            logger.error(f"Error processing RFP: {str(e)}")
            return {"error": str(e), "success": False}
            
    async def _extract_text(self, input_data: Dict[str, Any]) -> str:
        """
        Extract text from RFP document.
        """
        # If raw content is provided, return it directly
        if 'content' in input_data:
            return input_data['content']
            
        # If file path is provided, extract content based on file type
        file_path = Path(input_data['file_path'])
        suffix = file_path.suffix.lower()
        
        if suffix == '.txt':
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
                
        elif suffix == '.pdf':
            # Placeholder for PDF extraction
            # In a real implementation, we'd use PyPDF2 or similar
            logger.info("PDF extraction not yet implemented")
            return "PDF CONTENT PLACEHOLDER"
            
        elif suffix == '.docx':
            # Placeholder for DOCX extraction
            # In a real implementation, we'd use python-docx
            logger.info("DOCX extraction not yet implemented")
            return "DOCX CONTENT PLACEHOLDER"
            
        return ""
        
    async def _analyze_document(self, text: str, sections_of_interest: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Analyze document text to extract requirements, eligibility, deadlines, and scoring criteria.
        """
        # This is a placeholder for the actual AI-powered analysis
        # In a real implementation, we'd use LangChain or direct API calls to process the text
        
        # Sample identification of requirements (very basic regex patterns)
        requirements = []
        eligibility = []
        deadlines = []
        scoring_criteria = []
        
        # Simple pattern matching for demonstration
        req_patterns = [
            r"(?:must|should|shall|required to) ([^\.]+)",
            r"requirement[s]?:?\s*([^\.]+)",
            r"applicants must ([^\.]+)"
        ]
        
        for pattern in req_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                requirements.append(match.group(0).strip())
                
        # In a real implementation, we would use LLM to extract structured information
        
        return {
            "requirements": requirements[:10],  # Limit for demonstration
            "eligibility": eligibility,
            "deadlines": deadlines,
            "scoring_criteria": scoring_criteria
        }
