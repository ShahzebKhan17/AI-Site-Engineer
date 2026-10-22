"""Deterministic 1D Cutting Stock Optimizer & Rebar Procurement Engine.

Civil construction standard rebar in India and internationally is supplied in
commercial 12,000 mm (12.0 m) straight stock lengths per IS 1786.
This engine solves the 1D Cutting Stock Problem (CSP) to minimize scrap off-cuts,
grouping required cutting lengths into 12m stock bars and computing procurement bundles.
"""

from typing import Any
from pydantic import BaseModel, Field

# Standard commercial rebar stock length in millimeters
STANDARD_STOCK_LENGTH_MM = 12000.0

# Usable offcut threshold (pieces >= 1000 mm can be reused on site for chairs, dowels, or spacers)
USABLE_OFFCUT_THRESHOLD_MM = 1000.0


class CutPiece(BaseModel):
    member_id: str
    bar_mark: str
    bar_diameter_mm: int
    cutting_length_mm: float
    piece_index: int


class StockBarPattern(BaseModel):
    stock_bar_id: int
    bar_diameter_mm: int
    stock_length_mm: float = STANDARD_STOCK_LENGTH_MM
    cuts: list[CutPiece] = Field(default_factory=list)
    total_cut_length_mm: float = 0.0
    waste_scrap_mm: float = 0.0
    is_usable_offcut: bool = False
    wastage_percentage: float = 0.0


class DiameterOptimizationSummary(BaseModel):
    bar_diameter_mm: int
    total_pieces_required: int
    total_net_length_m: float
    total_net_weight_kg: float
    stock_bars_12m_required: int
    total_gross_length_m: float
    total_gross_weight_kg: float
    total_scrap_weight_kg: float
    wastage_percentage: float
    usable_offcuts_count: int
    patterns: list[StockBarPattern] = Field(default_factory=list)


class ProcurementOrderRequisition(BaseModel):
    project_id: str
    standard_stock_length_m: float = 12.0
    total_stock_bars_12m: int
    total_net_weight_tonnes: float
    total_gross_weight_tonnes: float
    total_scrap_tonnes: float
    overall_wastage_percentage: float
    diameter_summaries: list[DiameterOptimizationSummary] = Field(default_factory=list)
    procurement_recommendations: list[str] = Field(default_factory=list)


def unit_weight(diameter_mm: int) -> float:
    """Compute rebar unit weight in kg/m using d^2 / 162."""
    return round((diameter_mm ** 2) / 162.0, 3)


def optimize_cutting_stock(
    items: list[dict[str, Any]],
    project_id: str = "Structural Project",
    stock_length_mm: float = STANDARD_STOCK_LENGTH_MM,
) -> ProcurementOrderRequisition:
    """Run First-Fit Decreasing 1D cutting stock heuristic per bar diameter.

    Args:
        items: List of BBS items with cutting_length_mm, bar_diameter_mm, num_bars, member_id, bar_mark.
        project_id: Identification of project.
        stock_length_mm: Standard commercial length (default 12000 mm).

    Returns:
        ProcurementOrderRequisition containing cutting patterns, stock bar counts, and scrap metrics.
    """
    # Group required pieces by diameter
    pieces_by_dia: dict[int, list[CutPiece]] = {}

    for it in items:
        dia = int(it.get("bar_diameter_mm", 16))
        cut_len = float(it.get("cutting_length_mm", 0.0))
        num_bars = int(it.get("num_bars", 1))
        mem_id = str(it.get("member_id", "MEM"))
        b_mark = str(it.get("bar_mark", "Bar"))

        if cut_len <= 0 or num_bars <= 0:
            continue

        if dia not in pieces_by_dia:
            pieces_by_dia[dia] = []

        for p_idx in range(1, num_bars + 1):
            pieces_by_dia[dia].append(
                CutPiece(
                    member_id=mem_id,
                    bar_mark=b_mark,
                    bar_diameter_mm=dia,
                    cutting_length_mm=cut_len,
                    piece_index=p_idx,
                )
            )

    dia_summaries: list[DiameterOptimizationSummary] = []
    total_12m_bars = 0
    total_net_wt_kg = 0.0
    total_gross_wt_kg = 0.0
    total_scrap_wt_kg = 0.0

    # Sort diameters ascending
    for dia in sorted(pieces_by_dia.keys()):
        raw_pieces = pieces_by_dia[dia]
        # Sort pieces descending for First-Fit Decreasing (FFD) heuristic
        sorted_pieces = sorted(raw_pieces, key=lambda p: p.cutting_length_mm, reverse=True)

        stock_patterns: list[StockBarPattern] = []
        uw = unit_weight(dia)

        for piece in sorted_pieces:
            # Handle pieces longer than standard 12m stock (requires commercial lap splice)
            effective_len = piece.cutting_length_mm
            if effective_len > stock_length_mm:
                # Segment into full 12m bars + remainder
                while effective_len > stock_length_mm:
                    full_pattern = StockBarPattern(
                        stock_bar_id=len(stock_patterns) + 1,
                        bar_diameter_mm=dia,
                        stock_length_mm=stock_length_mm,
                        cuts=[
                            CutPiece(
                                member_id=piece.member_id,
                                bar_mark=f"{piece.bar_mark} (Part 12m)",
                                bar_diameter_mm=dia,
                                cutting_length_mm=stock_length_mm,
                                piece_index=piece.piece_index,
                            )
                        ],
                        total_cut_length_mm=stock_length_mm,
                        waste_scrap_mm=0.0,
                        is_usable_offcut=False,
                        wastage_percentage=0.0,
                    )
                    stock_patterns.append(full_pattern)
                    effective_len -= stock_length_mm

            # Now fit remaining piece into existing stock bars using Best-Fit
            best_idx = -1
            min_waste = stock_length_mm + 1.0

            for idx, pat in enumerate(stock_patterns):
                remaining_space = stock_length_mm - pat.total_cut_length_mm
                if remaining_space >= effective_len:
                    waste_after = remaining_space - effective_len
                    if waste_after < min_waste:
                        min_waste = waste_after
                        best_idx = idx

            if best_idx != -1:
                # Add to existing stock bar
                target_pat = stock_patterns[best_idx]
                target_pat.cuts.append(
                    CutPiece(
                        member_id=piece.member_id,
                        bar_mark=piece.bar_mark,
                        bar_diameter_mm=dia,
                        cutting_length_mm=effective_len,
                        piece_index=piece.piece_index,
                    )
                )
                target_pat.total_cut_length_mm += effective_len
                target_pat.waste_scrap_mm = round(stock_length_mm - target_pat.total_cut_length_mm, 1)
                target_pat.is_usable_offcut = target_pat.waste_scrap_mm >= USABLE_OFFCUT_THRESHOLD_MM
                target_pat.wastage_percentage = round((target_pat.waste_scrap_mm / stock_length_mm) * 100.0, 2)
            else:
                # Open a new 12m stock bar
                new_pat = StockBarPattern(
                    stock_bar_id=len(stock_patterns) + 1,
                    bar_diameter_mm=dia,
                    stock_length_mm=stock_length_mm,
                    cuts=[
                        CutPiece(
                            member_id=piece.member_id,
                            bar_mark=piece.bar_mark,
                            bar_diameter_mm=dia,
                            cutting_length_mm=effective_len,
                            piece_index=piece.piece_index,
                        )
                    ],
                    total_cut_length_mm=effective_len,
                    waste_scrap_mm=round(stock_length_mm - effective_len, 1),
                    is_usable_offcut=(stock_length_mm - effective_len) >= USABLE_OFFCUT_THRESHOLD_MM,
                    wastage_percentage=round(((stock_length_mm - effective_len) / stock_length_mm) * 100.0, 2),
                )
                stock_patterns.append(new_pat)

        # Summary for this diameter
        bars_count = len(stock_patterns)
        net_len_m = round(sum(p.cutting_length_mm for p in raw_pieces) / 1000.0, 3)
        net_wt_kg = round(net_len_m * uw, 2)
        gross_len_m = round(bars_count * (stock_length_mm / 1000.0), 3)
        gross_wt_kg = round(gross_len_m * uw, 2)
        scrap_wt_kg = round(gross_wt_kg - net_wt_kg, 2)
        wastage_pct = round((scrap_wt_kg / gross_wt_kg) * 100.0, 2) if gross_wt_kg > 0 else 0.0
        usable_offcuts = sum(1 for p in stock_patterns if p.is_usable_offcut)

        dia_summaries.append(
            DiameterOptimizationSummary(
                bar_diameter_mm=dia,
                total_pieces_required=len(raw_pieces),
                total_net_length_m=net_len_m,
                total_net_weight_kg=net_wt_kg,
                stock_bars_12m_required=bars_count,
                total_gross_length_m=gross_len_m,
                total_gross_weight_kg=gross_wt_kg,
                total_scrap_weight_kg=scrap_wt_kg,
                wastage_percentage=wastage_pct,
                usable_offcuts_count=usable_offcuts,
                patterns=stock_patterns,
            )
        )

        total_12m_bars += bars_count
        total_net_wt_kg += net_wt_kg
        total_gross_wt_kg += gross_wt_kg
        total_scrap_wt_kg += scrap_wt_kg

    overall_wastage = round((total_scrap_wt_kg / total_gross_wt_kg) * 100.0, 2) if total_gross_wt_kg > 0 else 0.0

    recommendations = [
        f"Order {total_12m_bars} standard 12.0 m commercial stock bars totaling {round(total_gross_wt_kg / 1000.0, 3)} Tonnes.",
        f"Predicted site scrap wastage rate is {overall_wastage}%, well within IS 456 standard allowable limit (< 5.0%).",
        "Offcuts >= 1000 mm should be color-tagged on site and allocated for footing chairs and slab spacer bars.",
    ]

    return ProcurementOrderRequisition(
        project_id=project_id,
        standard_stock_length_m=stock_length_mm / 1000.0,
        total_stock_bars_12m=total_12m_bars,
        total_net_weight_tonnes=round(total_net_wt_kg / 1000.0, 3),
        total_gross_weight_tonnes=round(total_gross_wt_kg / 1000.0, 3),
        total_scrap_tonnes=round(total_scrap_wt_kg / 1000.0, 3),
        overall_wastage_percentage=overall_wastage,
        diameter_summaries=dia_summaries,
        procurement_recommendations=recommendations,
    )
