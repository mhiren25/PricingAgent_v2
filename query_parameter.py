"""
Query Parameters - Structured output model for supervisor analysis
Updated with date handling
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from src.utils.date_handler import DateHandler


class QueryParameters(BaseModel):
    """Structured parameters extracted from user query"""
    
    intent: Literal[
        "Knowledge",
        "Data", 
        "Investigation",
        "Monitoring",
        "CodeAnalysis",
        "Comparison"
    ] = Field(
        description="Primary intent of the query"
    )
    
    order_id: Optional[str] = Field(
        default="",
        description="Primary order ID to investigate (empty if not applicable)"
    )
    
    date: Optional[str] = Field(
        default="",
        description="Date for primary order in any format (will be normalized to yyyy-mm-dd)"
    )
    
    comparison_order_id: Optional[str] = Field(
        default="",
        description="Second order ID for comparison (only for Comparison intent)"
    )
    
    comparison_date: Optional[str] = Field(
        default="",
        description="Date for comparison order in any format (will be normalized to yyyy-mm-dd)"
    )
    
    reasoning: str = Field(
        description="Brief explanation of the intent classification"
    )
    
    @field_validator('date', 'comparison_date')
    @classmethod
    def normalize_dates(cls, v: Optional[str]) -> str:
        """
        Normalize dates to yyyy-mm-dd format
        If empty and order_id is provided, use current date
        
        Args:
            v: Date string or empty
            
        Returns:
            Normalized date in yyyy-mm-dd format
        """
        if not v or not v.strip():
            # Return current date
            return DateHandler.get_current_date()
        
        return DateHandler.normalize_date(v)
    
    def ensure_dates_set(self) -> None:
        """
        Ensure dates are set for orders that need them
        Call this after parameter extraction
        """
        # For Investigation/Data intents with order_id, ensure date is set
        if self.intent in ["Investigation", "Data"] and self.order_id:
            if not self.date:
                self.date = DateHandler.get_current_date()
        
        # For Comparison intent, ensure both dates are set if orders exist
        if self.intent == "Comparison":
            if self.order_id and not self.date:
                self.date = DateHandler.get_current_date()
            
            if self.comparison_order_id and not self.comparison_date:
                self.comparison_date = DateHandler.get_current_date()
    
    class Config:
        """Pydantic config"""
        str_strip_whitespace = True
        validate_assignment = True
