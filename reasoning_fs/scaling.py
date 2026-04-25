"""Confidence-based scaling for agent behavior.

Implements dynamic token budget and temperature adjustment based on
confidence from memory similarity search.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class ScalingParams:
    """Parameters for scaling agent behavior."""
    max_tokens: int
    temperature: float
    top_p: float
    presence_penalty: float
    frequency_penalty: float


class ConfidenceScaler:
    """Scale agent behavior based on confidence from memory.
    
    Based on ReasoningBank's test-time scaling approach:
    - High confidence (similar traces exist): Lower temperature, fewer tokens
    - Low confidence (novel task): Higher temperature, more tokens
    
    Example:
        >>> scaler = ConfidenceScaler()
        >>> similar = memory.search("Find SQL injection")
        >>> confidence = scaler.calculate_confidence(similar)
        >>> params = scaler.scale(confidence)
        >>> print(params.max_tokens)  # Adjusted token budget
    """

    def __init__(
        self,
        base_max_tokens: int = 2000,
        min_max_tokens: int = 500,
        max_max_tokens: int = 8000,
        base_temperature: float = 0.7,
        min_temperature: float = 0.1,
        max_temperature: float = 1.0,
        confidence_threshold: float = 0.5,
    ):
        """Initialize scaler.
        
        Args:
            base_max_tokens: Default token budget
            min_max_tokens: Minimum token budget
            max_max_tokens: Maximum token budget
            base_temperature: Default temperature
            min_temperature: Minimum temperature (high confidence)
            max_temperature: Maximum temperature (low confidence)
            confidence_threshold: Threshold for confidence classification
        """
        self.base_max_tokens = base_max_tokens
        self.min_max_tokens = min_max_tokens
        self.max_max_tokens = max_max_tokens
        self.base_temperature = base_temperature
        self.min_temperature = min_temperature
        self.max_temperature = max_temperature
        self.confidence_threshold = confidence_threshold

    def calculate_confidence(self, similar_traces: List[Any]) -> float:
        """Calculate confidence from similar traces.
        
        Args:
            similar_traces: List of similar reasoning traces
            
        Returns:
            Confidence score (0.0 to 1.0)
        """
        if not similar_traces:
            return 0.0
        
        # Count successful traces
        success_count = sum(1 for t in similar_traces if getattr(t, 'success', False))
        
        # Confidence based on success rate and number of traces
        success_rate = success_count / len(similar_traces)
        trace_count_factor = min(len(similar_traces) / 5, 1.0)  # Normalize to 5 traces
        
        confidence = (success_rate * 0.7) + (trace_count_factor * 0.3)
        
        return min(max(confidence, 0.0), 1.0)

    def scale(self, confidence: float) -> ScalingParams:
        """Scale parameters based on confidence.
        
        Args:
            confidence: Confidence score (0.0 to 1.0)
            
        Returns:
            ScalingParams with adjusted values
        """
        # Direct relationship: high confidence = MORE tokens (for verification), 
        # lower temperature (more deterministic)
        # Low confidence = fewer tokens (exploration is expensive), 
        # higher temperature (more creative)
        
        # Token scaling (direct)
        token_factor = confidence  # 0.0 to 1.0
        max_tokens = int(
            self.min_max_tokens + 
            token_factor * (self.max_max_tokens - self.min_max_tokens)
        )
        
        # Temperature scaling (inverse)
        temp_factor = 1.0 - confidence
        temperature = self.min_temperature + temp_factor * (self.max_temperature - self.min_temperature)
        
        return ScalingParams(
            max_tokens=max_tokens,
            temperature=round(temperature, 2),
            top_p=0.9,
            presence_penalty=0.0,
            frequency_penalty=0.0,
        )

    def get_recommendation(self, confidence: float) -> str:
        """Get human-readable recommendation based on confidence.
        
        Args:
            confidence: Confidence score
            
        Returns:
            Recommendation string
        """
        if confidence >= 0.8:
            return "High confidence: Use conservative settings, rely on past patterns"
        elif confidence >= 0.5:
            return "Medium confidence: Balanced exploration and exploitation"
        elif confidence >= 0.3:
            return "Low confidence: Increase exploration, allocate more tokens"
        else:
            return "Very low confidence: High exploration mode, extensive reasoning required"
