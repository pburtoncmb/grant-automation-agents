import re
import json
import logging
import aiohttp
from typing import Dict, Any, List, Optional
from pathlib import Path
from bs4 import BeautifulSoup

from agents.base_agent import BaseAgent
from core.config import OPENAI_API_KEY, ANTHROPIC_API_KEY

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GrantScout(BaseAgent):
    """
    Agent for analyzing grant RFPs and finding grant opportunities.
    
    This agent is responsible for:
    1. Parsing RFP documents (PDF, DOCX, TXT)
    2. Identifying key requirements and eligibility criteria
    3. Extracting deadlines and important dates
    4. Determining scoring criteria and priorities
    5. Searching for grants via Candid API
    6. Matching grants to organization profiles
    """
    
    def __init__(self):
        super().__init__(
            name="GrantScout",
            description="Analyzes RFPs and finds grant opportunities matching organization profiles"
        )
        self.supported_file_types = ['.pdf', '.docx', '.txt']
        
    async def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """
        Validate that the input contains necessary information.
        
        Required (for RFP analysis):
        - file_path OR content: Path to RFP file or raw content
        
        Required (for grant search):
        - search_criteria: Dict with search parameters
        
        Optional:
        - file_type: Type of file (for raw content)
        - sections_of_interest: List of specific sections to focus on
        - org_profile: Organization profile for matching
        """
        if not input_data:
            logger.error("Input data is empty")
            return False
            
        # Check for RFP analysis mode
        if 'file_path' in input_data or 'content' in input_data:
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
                    
        # Check for grant search mode
        if 'search_criteria' in input_data:
            search_criteria = input_data['search_criteria']
            # Require at least one search parameter
            if not any(key in search_criteria for key in 
                      ['keywords', 'api_key', 'url', 'subject_areas']):
                logger.error("Search criteria must include at least one search parameter")
                return False
            return True
            
        logger.error("Input must contain either file_path/content for RFP analysis or search_criteria for grant search")
        return False
        
    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process input based on mode (RFP analysis or grant search).
        """
        # Validate input
        if not await self.validate_input(input_data):
            return {"error": "Invalid input", "success": False}
            
        try:
            # Determine processing mode
            if 'search_criteria' in input_data:
                # Grant search mode
                search_criteria = input_data['search_criteria']
                org_profile = input_data.get('org_profile', {})
                return await self.search_grants(search_criteria, org_profile)
            else:
                # RFP analysis mode
                document_text = await self._extract_text(input_data)
                results = await self._analyze_document(document_text, input_data.get('sections_of_interest'))
                
                return {
                    "success": True,
                    "requirements": results.get("requirements", []),
                    "eligibility": results.get("eligibility", []),
                    "deadlines": results.get("deadlines", []),
                    "scoring_criteria": results.get("scoring_criteria", [])
                }
        except Exception as e:
            logger.error(f"Error processing input: {str(e)}")
            return {"error": str(e), "success": False}
    
    async def search_grants(self, search_criteria: Dict[str, Any], org_profile: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Search for grants using various sources including Candid API.
        
        Parameters:
        - search_criteria: Dict containing search parameters such as:
          - keywords: List of keywords to search for
          - subject_areas: List of subject areas
          - funder_types: Types of funders to include
          - geography: Geographic restrictions
          - min_amount: Minimum grant amount
          - max_amount: Maximum grant amount
          - api_key: Candid API key (if using API)
          - url: Specific URL to analyze (if direct source)
        - org_profile: Organization profile for matching score calculation
        """
        results = []
        
        # If API key is provided, search using Candid API
        if 'api_key' in search_criteria:
            api_results = await self._search_candid_api(search_criteria)
            results.extend(api_results)
        
        # If URL is provided, analyze specific grant page
        if 'url' in search_criteria:
            url_results = await self._analyze_grant_url(search_criteria['url'])
            results.extend(url_results)
        
        # If keywords are provided without API, perform web search
        if 'keywords' in search_criteria and 'api_key' not in search_criteria and 'url' not in search_criteria:
            web_results = await self._search_grants_web(search_criteria)
            results.extend(web_results)
        
        # Calculate match scores if organization profile is provided
        if org_profile:
            for grant in results:
                grant['match_score'] = self.calculate_match_score(grant, org_profile)
                
            # Sort by match score (highest first)
            results = sorted(results, key=lambda x: x.get('match_score', 0), reverse=True)
        
        return {
            "success": True,
            "grants_found": len(results),
            "results": results
        }
        
    async def _search_candid_api(self, criteria: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Search for grants using the Candid API.
        """
        api_key = criteria.get('api_key')
        if not api_key:
            logger.error("Candid API key not provided")
            return []
        
        # Base URL for Candid API
        api_url = "https://api.candid.org/v1/grants"
        
        # Construct API request parameters
        params = {
            'key': api_key,
            'q': ' '.join(criteria.get('keywords', [])),
            'subject': ','.join(criteria.get('subject_areas', [])),
            'funder_type': ','.join(criteria.get('funder_types', [])),
            'min_amount': criteria.get('min_amount'),
            'max_amount': criteria.get('max_amount'),
            'geography': ','.join(criteria.get('geography', [])),
            'limit': criteria.get('limit', 20)
        }
        
        # Remove None values and empty strings
        params = {k: v for k, v in params.items() if v is not None and v != ''}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params) as response:
                    if response.status != 200:
                        logger.error(f"Candid API error: {response.status} - {await response.text()}")
                        return []
                    
                    data = await response.json()
                    
                    # Transform API response to our standard grant format
                    grants = []
                    for item in data.get('grants', []):
                        grant = {
                            'title': item.get('title', 'Unknown Grant'),
                            'funder': item.get('funder', {}).get('name', 'Unknown Funder'),
                            'amount': item.get('amount', {}).get('amount', 0),
                            'deadline': item.get('application_deadline', 'Unknown'),
                            'description': item.get('description', ''),
                            'url': item.get('url', ''),
                            'eligibility': item.get('eligibility', []),
                            'requirements': item.get('requirements', []),
                            'focus_areas': item.get('subject_areas', []),
                            'geography': item.get('geography', []),
                            'source': 'candid_api'
                        }
                        grants.append(grant)
                    
                    return grants
        except Exception as e:
            logger.error(f"Error searching Candid API: {str(e)}")
            return []
            
    async def _analyze_grant_url(self, url: str) -> List[Dict[str, Any]]:
        """
        Analyze a specific grant opportunity URL.
        """
        try:
            # Fetch webpage content
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"Error fetching URL {url}: {response.status}")
                        return []
                    
                    html = await response.text()
            
            # Parse HTML content with BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract grant details (simplified example - would be more complex in practice)
            title = soup.find('h1')
            title_text = title.text.strip() if title else 'Unknown Grant'
            
            # This is a simplified extraction - real implementation would be more robust
            grant = {
                'title': title_text,
                'funder': self._extract_funder(soup),
                'amount': self._extract_amount(soup),
                'deadline': self._extract_deadline(soup),
                'description': self._extract_description(soup),
                'url': url,
                'eligibility': self._extract_eligibility(soup),
                'requirements': self._extract_requirements(soup),
                'focus_areas': self._extract_focus_areas(soup),
                'geography': [],
                'source': 'direct_url'
            }
            
            return [grant]
        except Exception as e:
            logger.error(f"Error analyzing URL {url}: {str(e)}")
            return []
            
    def _extract_funder(self, soup: BeautifulSoup) -> str:
        """Extract funder name from soup - placeholder implementation."""
        # In a real implementation, this would have more sophisticated extraction logic
        funder_elem = soup.find('meta', property='og:site_name')
        if funder_elem and funder_elem.get('content'):
            return funder_elem.get('content')
        return 'Unknown Funder'
    
    def _extract_amount(self, soup: BeautifulSoup) -> int:
        """Extract grant amount from soup - placeholder implementation."""
        # In a real implementation, this would use regex and more robust parsing
        amount = 0
        try:
            # Look for dollar amounts in the text
            text = soup.get_text()
            # Simple regex to find dollar amounts
            matches = re.findall(r'\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', text)
            if matches:
                # Convert first match to integer
                amount_str = matches[0].replace(',', '')
                amount = int(float(amount_str))
        except Exception as e:
            logger.warning(f"Error extracting amount: {str(e)}")
        return amount
    
    def _extract_deadline(self, soup: BeautifulSoup) -> str:
        """Extract application deadline from soup - placeholder implementation."""
        # Look for deadline indicators
        text = soup.get_text().lower()
        deadline_indicators = [
            'deadline', 'due date', 'submission date', 'applications due'
        ]
        
        for indicator in deadline_indicators:
            idx = text.find(indicator)
            if idx >= 0:
                # Extract text around the indicator
                context = text[idx:idx+100]
                # Look for date patterns (very simplified)
                date_matches = re.findall(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b', context)
                if date_matches:
                    return date_matches[0]
        
        return 'Unknown'
    
    def _extract_description(self, soup: BeautifulSoup) -> str:
        """Extract grant description from soup - placeholder implementation."""
        # Look for meta description first
        meta_desc = soup.find('meta', {'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            return meta_desc.get('content')
        
        # Fallback to first paragraph
        first_p = soup.find('p')
        if first_p:
            return first_p.get_text().strip()
        
        return 'No description available'
    
    def _extract_eligibility(self, soup: BeautifulSoup) -> List[str]:
        """Extract eligibility requirements from soup - placeholder implementation."""
        eligibility = []
        # Look for sections that might contain eligibility info
        keywords = ['eligibility', 'who can apply', 'eligible organizations']
        
        for keyword in keywords:
            elements = soup.find_all(string=re.compile(keyword, re.IGNORECASE))
            for element in elements:
                parent = element.parent
                if parent.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    # Found a heading about eligibility, extract the content after it
                    next_elem = parent.find_next(['p', 'ul', 'ol'])
                    if next_elem:
                        if next_elem.name == 'ul' or next_elem.name == 'ol':
                            # Extract list items
                            for li in next_elem.find_all('li'):
                                eligibility.append(li.get_text().strip())
                        else:
                            # Extract paragraph text
                            eligibility.append(next_elem.get_text().strip())
        
        return eligibility
    
    def _extract_requirements(self, soup: BeautifulSoup) -> List[str]:
        """Extract application requirements from soup - placeholder implementation."""
        # Similar approach to eligibility extraction
        requirements = []
        keywords = ['requirements', 'how to apply', 'application process']
        
        for keyword in keywords:
            elements = soup.find_all(string=re.compile(keyword, re.IGNORECASE))
            for element in elements:
                parent = element.parent
                if parent.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    # Found a heading about requirements, extract the content after it
                    next_elem = parent.find_next(['p', 'ul', 'ol'])
                    if next_elem:
                        if next_elem.name == 'ul' or next_elem.name == 'ol':
                            # Extract list items
                            for li in next_elem.find_all('li'):
                                requirements.append(li.get_text().strip())
                        else:
                            # Extract paragraph text
                            requirements.append(next_elem.get_text().strip())
        
        return requirements
    
    def _extract_focus_areas(self, soup: BeautifulSoup) -> List[str]:
        """Extract focus areas from soup - placeholder implementation."""
        focus_areas = []
        keywords = ['focus areas', 'program areas', 'priorities', 'areas of interest']
        
        for keyword in keywords:
            elements = soup.find_all(string=re.compile(keyword, re.IGNORECASE))
            for element in elements:
                parent = element.parent
                if parent.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    # Found a heading about focus areas, extract the content after it
                    next_elem = parent.find_next(['p', 'ul', 'ol'])
                    if next_elem:
                        if next_elem.name == 'ul' or next_elem.name == 'ol':
                            # Extract list items
                            for li in next_elem.find_all('li'):
                                focus_areas.append(li.get_text().strip())
                        else:
                            # Extract paragraph text
                            text = next_elem.get_text().strip()
                            # Split by commas if it looks like a list
                            if ',' in text:
                                focus_areas.extend([area.strip() for area in text.split(',')])
                            else:
                                focus_areas.append(text)
        
        return focus_areas
            
    async def _search_grants_web(self, criteria: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Search for grants using web search when API is not available.
        """
        # This would be a more complex implementation using search APIs or web scraping
        # For now, just a placeholder
        logger.info("Web search for grants not yet implemented")
        return []
            
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
                
        # Look for eligibility information
        elig_patterns = [
            r"eligibility:?\s*([^\.]+)",
            r"eligible (?:organizations|applicants|entities)[\s:]+([^\.]+)",
            r"who can apply:?\s*([^\.]+)"
        ]
        
        for pattern in elig_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                eligibility.append(match.group(0).strip())
                
        # Look for deadline information
        deadline_patterns = [
            r"deadline:?\s*([^\.\n]+)",
            r"due (?:date|by):?\s*([^\.\n]+)",
            r"submissions due:?\s*([^\.\n]+)"
        ]
        
        for pattern in deadline_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                deadlines.append(match.group(0).strip())
                
        # Look for scoring criteria
        scoring_patterns = [
            r"scoring criteria:?\s*([^\.]+)",
            r"evaluation criteria:?\s*([^\.]+)",
            r"(?:proposals|applications) will be (?:evaluated|judged|scored) (?:based on|according to):?\s*([^\.]+)"
        ]
        
        for pattern in scoring_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                scoring_criteria.append(match.group(0).strip())
        
        return {
            "requirements": requirements[:10],  # Limit for demonstration
            "eligibility": eligibility[:5],
            "deadlines": deadlines[:3],
            "scoring_criteria": scoring_criteria[:5]
        }
    
    def calculate_match_score(self, grant: Dict[str, Any], org_profile: Dict[str, Any]) -> int:
        """
        Calculate a match score (0-100) between grant opportunity and organization profile.
        
        Parameters:
        - grant: Grant opportunity details
        - org_profile: Organization profile with mission, focus areas, etc.
        
        Returns:
        - Integer score from 0-100
        """
        if not org_profile:
            return 0
            
        # Initialize scoring components with weights
        mission_weight = 0.30  # 30% of total score
        eligibility_weight = 0.25  # 25% of total score
        funding_weight = 0.20  # 20% of total score
        geography_weight = 0.15  # 15% of total score
        timeline_weight = 0.10  # 10% of total score
        
        # 1. Mission Alignment (0-100 points)
        mission_score = self._calculate_mission_alignment(
            grant.get('focus_areas', []),
            org_profile.get('mission_statement', ''),
            org_profile.get('focus_areas', [])
        )
        
        # 2. Eligibility Match (0-100 points)
        eligibility_score = self._calculate_eligibility_match(
            grant.get('eligibility', []),
            org_profile
        )
        
        # 3. Funding Amount (0-100 points)
        funding_score = self._calculate_funding_match(
            grant.get('amount', 0),
            org_profile.get('ideal_funding', {})
        )
        
        # 4. Geographic Focus (0-100 points)
        geography_score = self._calculate_geography_match(
            grant.get('geography', []),
            org_profile.get('service_areas', [])
        )
        
        # 5. Timeline Compatibility (0-100 points)
        timeline_score = self._calculate_timeline_match(
            grant.get('deadline', ''),
            org_profile.get('capacity', {})
        )
        
        # Calculate weighted total score
        total_score = (
            mission_score * mission_weight + 
            eligibility_score * eligibility_weight + 
            funding_score * funding_weight + 
            geography_score * geography_weight + 
            timeline_score * timeline_weight
        ) * 100
        
        # Round to nearest integer and ensure within 0-100 range
        return min(100, max(0, round(total_score)))
    
    def _calculate_mission_alignment(self, 
                                    grant_focus_areas: List[str], 
                                    org_mission: str, 
                                    org_focus_areas: List[str]) -> float:
        """
        Calculate mission alignment score (0-1).
        """
        if not grant_focus_areas or (not org_mission and not org_focus_areas):
            return 0.0
            
        # Convert everything to lowercase for better matching
        grant_focus_areas = [area.lower() for area in grant_focus_areas]
        org_mission = org_mission.lower()
        org_focus_areas = [area.lower() for area in org_focus_areas]
        
        # Calculate direct matches between focus areas
        direct_matches = 0
        for grant_area in grant_focus_areas:
            for org_area in org_focus_areas:
                # Check for exact matches or if one contains the other
                if grant_area == org_area or grant_area in org_area or org_area in grant_area:
                    direct_matches += 1
                    break
        
        # Calculate match ratio based on direct matches
        direct_match_score = direct_matches / len(grant_focus_areas) if grant_focus_areas else 0
        
        # Check if grant focus areas appear in mission statement
        mission_matches = 0
        for area in grant_focus_areas:
            if area in org_mission:
                mission_matches += 1
        
        # Calculate match ratio based on mission statement
        mission_match_score = mission_matches / len(grant_focus_areas) if grant_focus_areas else 0
        
        # Combine scores (giving more weight to direct matches)
        return direct_match_score * 0.7 + mission_match_score * 0.3
    
    def _calculate_eligibility_match(self, grant_eligibility: List[str], org_profile: Dict[str, Any]) -> float:
        """
        Calculate eligibility match score (0-1).
        """
        if not grant_eligibility:
            return 1.0  # No eligibility requirements means everyone is eligible
            
        # Common eligibility criteria to check
        criteria_checkers = {
            "501(c)(3)": lambda profile: profile.get("is_501c3", False),
            "nonprofit": lambda profile: profile.get("is_nonprofit", False),
            "years": self._check_years_requirement,
            "budget": self._check_budget_requirement,
            "location": self._check_location_requirement
        }
        
        # Track the number of criteria met
        criteria_met = 0
        criteria_total = 0
        
        for requirement in grant_eligibility:
            requirement_lower = requirement.lower()
            criteria_total += 1
            
            # Check for 501(c)(3) requirement
            if any(term in requirement_lower for term in ["501(c)(3)", "501c3", "tax-exempt"]):
                if criteria_checkers["501(c)(3)"](org_profile):
                    criteria_met += 1
                    
            # Check for nonprofit status
            elif any(term in requirement_lower for term in ["nonprofit", "non-profit", "not for profit"]):
                if criteria_checkers["nonprofit"](org_profile):
                    criteria_met += 1
                    
            # Check for years of operation
            elif any(term in requirement_lower for term in ["years", "established", "history"]):
                if self._check_years_requirement(requirement_lower, org_profile):
                    criteria_met += 1
                    
            # Check for budget requirements
            elif any(term in requirement_lower for term in ["budget", "revenue", "income"]):
                if self._check_budget_requirement(requirement_lower, org_profile):
                    criteria_met += 1
                    
            # Check for location requirements
            elif any(term in requirement_lower for term in ["located", "location", "area", "region"]):
                if self._check_location_requirement(requirement_lower, org_profile):
                    criteria_met += 1
                    
            # Default assumption for other requirements
            else:
                # For requirements we can't automatically check, assume met
                criteria_met += 0.5
        
        # Calculate match score
        return criteria_met / criteria_total if criteria_total > 0 else 1.0
    
    def _check_years_requirement(self, requirement: str, org_profile: Dict[str, Any]) -> bool:
        """Check if organization meets years of operation requirement."""
        # Extract years number from requirement
        years_match = re.search(r'(\d+)\s*years?', requirement)
        if not years_match:
            return True  # Can't determine requirement, assume met
            
        required_years = int(years_match.group(1))
        org_years = org_profile.get("years_of_operation", 0)
        
        return org_years >= required_years
    
    def _check_budget_requirement(self, requirement: str, org_profile: Dict[str, Any]) -> bool:
        """Check if organization meets budget requirement."""
        # Extract budget number from requirement
        budget_match = re.search(r'budget\s*(under|over|at least|maximum|minimum)?\s*\$?(\d[\d,]*)', requirement)
        if not budget_match:
            return True  # Can't determine requirement, assume met
            
        direction = budget_match.group(1) if budget_match.group(1) else "at least"
        amount = int(budget_match.group(2).replace(',', ''))
        org_budget = org_profile.get("annual_budget", 0)
        
        if direction in ["under", "maximum"]:
            return org_budget <= amount
        else:  # "over", "at least", "minimum", or default
            return org_budget >= amount
    
    def _check_location_requirement(self, requirement: str, org_profile: Dict[str, Any]) -> bool:
        """Check if organization meets location requirement."""
        org_locations = org_profile.get("service_areas", [])
        if not org_locations:
            return False
            
        # Look for location mentions in the requirement
        for location in org_locations:
            if location.lower() in requirement:
                return True
                
        return False
    
    def _calculate_funding_match(self, grant_amount: int, ideal_funding: Dict[str, Any]) -> float:
        """
        Calculate funding amount match score (0-1).
        """
        if not grant_amount or not ideal_funding:
            return 0.5  # Neutral score if information is missing
            
        min_amount = ideal_funding.get("min_amount", 0)
        max_amount = ideal_funding.get("max_amount", float('inf'))
        optimal_amount = ideal_funding.get("optimal_amount", (min_amount + max_amount) / 2 if max_amount != float('inf') else min_amount * 2)
        
        # Check if amount is within range
        if grant_amount < min_amount:
            # Below minimum - partial score based on how close it is
            return max(0, grant_amount / min_amount * 0.5)
        elif max_amount != float('inf') and grant_amount > max_amount:
            # Above maximum - partial score based on how close it is
            return max(0, 0.5 - (grant_amount - max_amount) / max_amount * 0.5)
        else:
            # Within range - full score with bonus for being close to optimal
            base_score = 0.7
            if optimal_amount:
                # Calculate how close to optimal (normalized to 0-0.3 range)
                proximity = 1 - min(abs(grant_amount - optimal_amount) / optimal_amount, 1)
                return base_score + proximity * 0.3
            return base_score
    
    def _calculate_geography_match(self, grant_geography: List[str], org_service_areas: List[str]) -> float:
        """
        Calculate geographic match score (0-1).
        """
        if not grant_geography or not org_service_areas:
            return 0.5  # Neutral score if information is missing
            
        # Normalize geography strings
        grant_geography = [g.lower() for g in grant_geography]
# Normalize geography strings
        grant_geography = [g.lower() for g in grant_geography]
        org_service_areas = [a.lower() for a in org_service_areas]
        
        # Check for direct matches
        direct_matches = 0
        for grant_area in grant_geography:
            for org_area in org_service_areas:
                # Check for exact matches or if one contains the other
                if grant_area == org_area or grant_area in org_area or org_area in grant_area:
                    direct_matches += 1
                    break
        
        # Calculate match ratio
        return direct_matches / len(grant_geography) if grant_geography else 0.5
    
    def _calculate_timeline_match(self, grant_deadline: str, org_capacity: Dict[str, Any]) -> float:
        """
        Calculate timeline compatibility score (0-1).
        """
        if not grant_deadline or not org_capacity:
            return 0.5  # Neutral score if information is missing
            
        # Try to parse deadline into a date
        try:
            # Simple parsing for common date formats
            if '/' in grant_deadline:
                parts = grant_deadline.split('/')
                if len(parts) == 3:
                    month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
                    # Would convert to date object in real implementation
            
            # Check available capacity periods
            available_periods = org_capacity.get("available_periods", [])
            for period in available_periods:
                # Would implement period matching in real implementation
                pass
                
            # For now, return a default medium-high score
            return 0.7
        except Exception:
            # If we can't parse the deadline, return neutral score
            return 0.5
