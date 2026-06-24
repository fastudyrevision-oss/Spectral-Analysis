# -*- coding: utf-8 -*-
"""
Step 4: Elemental Preferences & Peak-wise Competition Analysis

Analyzes which elements best match detected peaks through competitive scoring,
generating element rankings and identifying the most probable primary element.
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from pathlib import Path

from src import (
    STEP4_PARAMS, setup_logger,
    ProcessingError
)


logger = setup_logger(__name__)


class ElementalPreferencesAnalyzer:
    """
    Analyzes elemental matches and ranks elements by competitive scoring.
    
    Features:
    - Peak-wise competition: determines winning element per peak
    - Element ranking: counts wins and totals scores per element
    - Confidence scoring: evaluates confidence in element identification
    - Multi-file support: combines matches from multiple NIST databases
    """
    
    def __init__(self, config: dict = None):
        """
        Initialize elemental preferences analyzer.
        
        Parameters
        ----------
        config : dict, optional
            Configuration with keys:
            - MIN_SCORE: minimum score threshold for analysis
            
            If None, uses defaults from STEP4_PARAMS
        """
        if config is None:
            config = STEP4_PARAMS
        
        self.min_score = float(config.get('MIN_SCORE', 0))
        
        logger.info(f"ElementalPreferencesAnalyzer initialized with:")
        logger.info(f"  MIN_SCORE={self.min_score}")
    
    def validate_input(self, df: pd.DataFrame) -> bool:
        """
        Validate input data frame.
        
        Parameters
        ----------
        df : pd.DataFrame
            Input matching results
        
        Returns
        -------
        bool
            True if valid
        
        Raises
        ------
        ElementalAnalysisError
            If validation fails
        """
        if df is None or df.empty:
            raise ElementalAnalysisError("Input DataFrame is empty")
        
        required_cols = ["Observed_WL", "Matched_WL", "Score", "Element"]
        missing = [c for c in required_cols if c not in df.columns]
        
        if missing:
            raise ElementalAnalysisError(
                f"Missing required columns: {missing}"
            )
        
        logger.info(f"Input validation passed: {len(df)} rows")
        return True
    
    @staticmethod
    def detect_column_names(df: pd.DataFrame) -> pd.DataFrame:
        """
        Auto-detect and normalize column names.
        
        Parameters
        ----------
        df : pd.DataFrame
            DataFrame with potentially varying column names
        
        Returns
        -------
        pd.DataFrame
            DataFrame with normalized column names
        """
        # Strip whitespace from column names
        df.columns = df.columns.str.strip()
        
        # Create case-insensitive mapping
        cols_lower = {col.lower(): col for col in df.columns}
        
        # Map known variations
        rename_map = {}
        
        # Observed wavelength
        for variant in ['observed_wl', 'observed wavelength', 'detected_wl']:
            if variant in cols_lower:
                rename_map[cols_lower[variant]] = 'Observed_WL'
                break
        
        # Matched wavelength
        for variant in ['matched_wl', 'matched wavelength', 'nist_wl']:
            if variant in cols_lower:
                rename_map[cols_lower[variant]] = 'Matched_WL'
                break
        
        # Score
        for variant in ['score', 'confidence', 'match_score']:
            if variant in cols_lower:
                rename_map[cols_lower[variant]] = 'Score'
                break
        
        # Element
        for variant in ['element', 'ion', 'species']:
            if variant in cols_lower:
                rename_map[cols_lower[variant]] = 'Element'
                break
        
        if rename_map:
            df = df.rename(columns=rename_map)
            logger.info(f"Normalized columns: {rename_map}")
        
        return df
    
    def combine_matches(self, dataframes: List[pd.DataFrame]) -> pd.DataFrame:
        """
        Combine multiple NIST matching files into single dataset.
        
        Parameters
        ----------
        dataframes : List[pd.DataFrame]
            List of DataFrames from individual element matches
        
        Returns
        -------
        pd.DataFrame
            Combined DataFrame
        
        Raises
        ------
        ElementalAnalysisError
            If combination fails
        """
        if not dataframes or all(df.empty for df in dataframes):
            raise ElementalAnalysisError("No valid data to combine")
        
        # Filter and normalize each dataframe
        processed_dfs = []
        for df in dataframes:
            if df.empty:
                continue
            
            # Normalize columns
            df = self.detect_column_names(df)
            
            # Validate required columns
            self.validate_input(df)
            
            # Keep only positive scores
            df = df[df["Score"] > self.min_score].copy()
            
            if not df.empty:
                processed_dfs.append(df)
        
        if not processed_dfs:
            raise ElementalAnalysisError("No valid matches after filtering")
        
        # Combine all data
        combined = pd.concat(processed_dfs, ignore_index=True)
        
        logger.info(f"Combined {len(processed_dfs)} files: {len(combined)} total rows")
        
        return combined
    
    def analyze_peak_competition(
        self, combined_data: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Perform peak-wise competition to determine winning element per peak.
        
        Parameters
        ----------
        combined_data : pd.DataFrame
            Combined matching data
        
        Returns
        -------
        pd.DataFrame
            Competition results with winners
        """
        # Create pivot table: rows=wavelengths, columns=elements, values=scores
        pivot = combined_data.pivot_table(
            index="Matched_WL",
            columns="Element",
            values="Score",
            aggfunc="max"
        ).fillna(0)
        
        # Add competition metrics
        pivot["Max_Score"] = pivot.max(axis=1)
        pivot["Winner"] = pivot.idxmax(axis=1)
        pivot["Num_Competitors"] = (pivot.drop(
            columns=["Max_Score", "Winner"]
        ) > 0).sum(axis=1)
        
        # Reset index to make wavelength a column
        competition = pivot.reset_index()
        
        logger.info(f"Peak competition completed: {len(competition)} peaks analyzed")
        
        return competition
    
    def analyze_element_ranking(
        self, combined_data: pd.DataFrame,
        competition_data: pd.DataFrame
    ) -> Tuple[pd.DataFrame, str]:
        """
        Rank elements by wins and total score.
        
        Parameters
        ----------
        combined_data : pd.DataFrame
            Combined matching data
        competition_data : pd.DataFrame
            Competition results with winners
        
        Returns
        -------
        Tuple[pd.DataFrame, str]
            (ranking_summary, primary_element)
        """
        # Count wins per element
        wins = competition_data["Winner"].value_counts()
        summary = wins.reset_index()
        summary.columns = ["Element", "Wins"]
        
        # Sum scores per element
        score_sum = combined_data.groupby("Element")["Score"].sum().reset_index()
        score_sum.columns = ["Element", "Total_Score"]
        
        # Merge and sort
        summary = pd.merge(summary, score_sum, on="Element")
        summary["Avg_Score"] = summary["Total_Score"] / summary["Wins"]
        summary = summary.sort_values("Wins", ascending=False).reset_index(drop=True)
        
        primary_element = summary.iloc[0]["Element"] if not summary.empty else None
        
        logger.info(f"Element ranking: {primary_element} is primary element")
        logger.info(f"Summary:\n{summary}")
        
        return summary, primary_element
    
    def extract_winner_lines(
        self, competition_data: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Extract winning element lines with metadata.
        
        Parameters
        ----------
        competition_data : pd.DataFrame
            Competition results with winners
        
        Returns
        -------
        pd.DataFrame
            Winner lines with element, wavelengths, and confidence
        """
        winner_lines = competition_data[[
            "Matched_WL",
            "Winner",
            "Max_Score",
            "Num_Competitors"
        ]].copy()
        
        # Rename for clarity
        winner_lines = winner_lines.rename(columns={
            "Winner": "Winning_Element",
            "Matched_WL": "Observed_Wavelength",
            "Max_Score": "Confidence_Score",
        })
        
        winner_lines["NIST_Matched_Wavelength"] = winner_lines["Observed_Wavelength"]
        
        # Reorder columns
        winner_lines = winner_lines[[
            "Winning_Element",
            "Observed_Wavelength",
            "NIST_Matched_Wavelength",
            "Confidence_Score",
            "Num_Competitors"
        ]]
        
        # Round wavelengths
        winner_lines["Observed_Wavelength"] = winner_lines["Observed_Wavelength"].round(2)
        winner_lines["NIST_Matched_Wavelength"] = winner_lines["NIST_Matched_Wavelength"].round(2)
        winner_lines["Confidence_Score"] = winner_lines["Confidence_Score"].round(4)
        
        # Sort by element and wavelength
        winner_lines = winner_lines.sort_values(
            ["Winning_Element", "Observed_Wavelength"]
        ).reset_index(drop=True)
        
        logger.info(f"Extracted {len(winner_lines)} winner lines")
        
        return winner_lines
    
    def analyze(self, dataframes: List[pd.DataFrame]) -> Dict:
        """
        Complete elemental analysis pipeline.
        
        Parameters
        ----------
        dataframes : List[pd.DataFrame]
            List of NIST matching DataFrames
        
        Returns
        -------
        Dict with keys:
            - 'combined_data': all combined matches
            - 'competition': peak-wise competition results
            - 'ranking': element ranking summary
            - 'primary_element': identified primary element
            - 'winner_lines': winning lines per peak
        
        Raises
        ------
        ElementalAnalysisError
            If analysis fails at any step
        """
        try:
            # Step 1: Combine all matching files
            combined = self.combine_matches(dataframes)
            
            # Step 2: Perform peak-wise competition
            competition = self.analyze_peak_competition(combined)
            
            # Step 3: Rank elements
            ranking, primary_element = self.analyze_element_ranking(combined, competition)
            
            # Step 4: Extract winner lines
            winner_lines = self.extract_winner_lines(competition)
            
            logger.info("Elemental analysis completed successfully")
            
            return {
                'combined_data': combined,
                'competition': competition,
                'ranking': ranking,
                'primary_element': primary_element,
                'winner_lines': winner_lines
            }
        
        except Exception as e:
            raise ElementalAnalysisError(f"Analysis failed: {str(e)}")


class ElementalAnalysisError(ProcessingError):
    """Raised when elemental analysis fails."""
    pass
