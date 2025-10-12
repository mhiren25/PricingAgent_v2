"""
Date Handler Utility - Converts various date formats to yyyy-mm-dd
"""

from datetime import datetime
from typing import Optional
import re


class DateHandler:
    """Utility class for handling and normalizing date inputs"""
    
    @staticmethod
    def get_current_date() -> str:
        """
        Get current date in yyyy-mm-dd format
        
        Returns:
            Current date as string (e.g., "2025-10-12")
        """
        return datetime.now().strftime("%Y-%m-%d")
    
    @staticmethod
    def normalize_date(date_input: Optional[str]) -> str:
        """
        Normalize date to yyyy-mm-dd format or return current date
        
        Supports formats:
        - yyyy-mm-dd (already correct)
        - dd-mm-yyyy
        - mm/dd/yyyy
        - dd/mm/yyyy
        - yyyy/mm/dd
        - Natural language: "today", "yesterday"
        - None or empty string → current date
        
        Args:
            date_input: Date string in various formats or None
            
        Returns:
            Date in yyyy-mm-dd format
        """
        # Handle None or empty string
        if not date_input or not date_input.strip():
            return DateHandler.get_current_date()
        
        date_str = date_input.strip().lower()
        
        # Handle natural language
        if date_str in ["today", "now"]:
            return DateHandler.get_current_date()
        
        if date_str == "yesterday":
            from datetime import timedelta
            yesterday = datetime.now() - timedelta(days=1)
            return yesterday.strftime("%Y-%m-%d")
        
        # Try to parse various date formats
        formats_to_try = [
            "%Y-%m-%d",      # 2025-10-12
            "%Y/%m/%d",      # 2025/10/12
            "%d-%m-%Y",      # 12-10-2025
            "%d/%m/%Y",      # 12/10/2025
            "%m/%d/%Y",      # 10/12/2025
            "%Y%m%d",        # 20251012
            "%d-%b-%Y",      # 12-Oct-2025
            "%d %b %Y",      # 12 Oct 2025
            "%B %d, %Y",     # October 12, 2025
            "%d %B %Y",      # 12 October 2025
        ]
        
        for date_format in formats_to_try:
            try:
                parsed_date = datetime.strptime(date_str, date_format)
                return parsed_date.strftime("%Y-%m-%d")
            except ValueError:
                continue
        
        # Try to extract date with regex (yyyy-mm-dd pattern)
        match = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', date_str)
        if match:
            year, month, day = match.groups()
            try:
                parsed_date = datetime(int(year), int(month), int(day))
                return parsed_date.strftime("%Y-%m-%d")
            except ValueError:
                pass
        
        # Try dd-mm-yyyy or dd/mm/yyyy pattern
        match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', date_str)
        if match:
            day, month, year = match.groups()
            try:
                parsed_date = datetime(int(year), int(month), int(day))
                return parsed_date.strftime("%Y-%m-%d")
            except ValueError:
                pass
        
        # If all parsing fails, return current date as fallback
        print(f"Warning: Could not parse date '{date_input}', using current date")
        return DateHandler.get_current_date()
    
    @staticmethod
    def validate_date(date_str: str) -> bool:
        """
        Validate if string is in yyyy-mm-dd format
        
        Args:
            date_str: Date string to validate
            
        Returns:
            True if valid yyyy-mm-dd format, False otherwise
        """
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False
