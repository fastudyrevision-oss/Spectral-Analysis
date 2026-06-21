# -*- coding: utf-8 -*-
"""
Test Pipeline - Full 3-Step Workflow

This script demonstrates the complete spectral analysis pipeline:
Step 1: SG-ALS Baseline Correction
Step 2: Automatic Peaks Detection
Step 3: NIST Element Identification
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src import setup_logger
from src.core.step1_sg_als import BaselineCorrection
from src.core.step2_peaks import PeaksDetector
from src.core.step3_nist_matching import NISTMatcher
from src.io.file_reader import CSVReader
from src.io.file_writer import CSVWriter, PlotGenerator


logger = setup_logger(__name__)


def main():
    """Run full pipeline test."""
    logger.info("=" * 60)
    logger.info("SPECTRAL ANALYSIS SOFTWARE - FULL PIPELINE TEST")
    logger.info("=" * 60)
    
    # Paths
    input_file = Path("data/sample_inputs/soil3-unprocessed.csv")
    nist_file = Path("data/nist_databases/NIST-Ca.csv")
    
    # Check if sample data exists
    if not input_file.exists():
        logger.warning(f"Sample input file not found: {input_file}")
        logger.info("Copy your sample CSV files to data/sample_inputs/")
        logger.info("Copy NIST databases to data/nist_databases/")
        return
    
    try:
        # ==========================================
        # STEP 1: BASELINE CORRECTION
        # ==========================================
        logger.info("\n" + "=" * 60)
        logger.info("STEP 1: SG-ALS BASELINE CORRECTION")
        logger.info("=" * 60)
        
        reader = CSVReader()
        raw_spectra = reader.read_raw_spectra(str(input_file))
        
        corrector = BaselineCorrection()
        processed = corrector.process(raw_spectra.wavelength, raw_spectra.intensity)
        
        # Save results
        writer = CSVWriter()
        output_csv = writer.write_processed_spectra("SG_ALS_LIBS_processed.csv", processed)
        logger.info(f"[OK] Step 1 output saved: {output_csv}")
        
        # Generate plot
        plot_gen = PlotGenerator()
        output_plot = plot_gen.plot_step1_baseline(processed, "SG_ALS_LIBS_processed.png")
        logger.info(f"[OK] Step 1 plot saved: {output_plot}")
        
        # ==========================================
        # STEP 2: PEAKS DETECTION
        # ==========================================
        logger.info("\n" + "=" * 60)
        logger.info("STEP 2: AUTOMATIC PEAKS DETECTION")
        logger.info("=" * 60)
        
        detector = PeaksDetector()
        detected_peaks = detector.detect_peaks(processed.wavelength, processed.corrected)
        
        # Save results
        peaks_csv = writer.write_detected_peaks("detected_peaks.csv", detected_peaks)
        logger.info(f"[OK] Step 2 output saved: {peaks_csv}")
        logger.info(f"  Found {len(detected_peaks)} peaks")
        
        # Generate plot
        peaks_plot = plot_gen.plot_step2_peaks(
            processed.wavelength, 
            processed.corrected,
            detected_peaks,
            "Automatic_peaks_identification.png"
        )
        logger.info(f"[OK] Step 2 plot saved: {peaks_plot}")
        
        # ==========================================
        # STEP 3: NIST MATCHING
        # ==========================================
        logger.info("\n" + "=" * 60)
        logger.info("STEP 3: NIST ELEMENT IDENTIFICATION")
        logger.info("=" * 60)
        
        if nist_file.exists():
            nist_db = reader.read_nist_database(str(nist_file))
            
            matcher = NISTMatcher()
            matches = matcher.match_peaks(detected_peaks, nist_db)
            
            # Save results
            matches_csv = writer.write_nist_matches("LIBS_matching_results.csv", matches)
            logger.info(f"[OK] Step 3 output saved: {matches_csv}")
            
            # Statistics
            identified = [m for m in matches if m.element]
            logger.info(f"  Identified peaks: {len(identified)}/{len(matches)}")
            
        else:
            logger.warning(f"NIST database not found: {nist_file}")
            logger.info("Skipping Step 3 - Place NIST CSV in data/nist_databases/")
        
        logger.info("\n" + "=" * 60)
        logger.info("[OK] PIPELINE COMPLETE")
        logger.info("=" * 60)
        
        logger.info("\nOutput files generated:")
        logger.info("  - SG_ALS_LIBS_processed.csv")
        logger.info("  - SG_ALS_LIBS_processed.png")
        logger.info("  - detected_peaks.csv")
        logger.info("  - Automatic_peaks_identification.png")
        if nist_file.exists():
            logger.info("  - LIBS_matching_results.csv")
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
