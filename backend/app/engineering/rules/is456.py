"""IS 456:2000 Plain and Reinforced Concrete - Code of Practice rules engine."""

from enum import Enum
from pydantic import BaseModel, Field


class ConcreteGrade(str, Enum):
    M20 = "M20"
    M25 = "M25"
    M30 = "M30"
    M35 = "M35"
    M40 = "M40"


class SteelGrade(str, Enum):
    FE250 = "FE250"
    FE415 = "FE415"
    FE500 = "FE500"
    FE550 = "FE550"


class StressType(str, Enum):
    TENSION = "tension"
    COMPRESSION = "compression"


# Table 26.2.1.1: Design bond stress tau_bd for plain bars in tension (N/mm²)
DESIGN_BOND_STRESS_PLAIN_TENSION: dict[ConcreteGrade, float] = {
    ConcreteGrade.M20: 1.2,
    ConcreteGrade.M25: 1.4,
    ConcreteGrade.M30: 1.5,
    ConcreteGrade.M35: 1.7,
    ConcreteGrade.M40: 1.9,
}

# Characteristic yield strength f_y in N/mm² (MPa)
STEEL_YIELD_STRENGTH: dict[SteelGrade, float] = {
    SteelGrade.FE250: 250.0,
    SteelGrade.FE415: 415.0,
    SteelGrade.FE500: 500.0,
    SteelGrade.FE550: 550.0,
}


def normalize_concrete_grade(grade: str | ConcreteGrade) -> ConcreteGrade:
    if isinstance(grade, ConcreteGrade):
        return grade
    cleaned = str(grade).strip().upper()
    try:
        return ConcreteGrade(cleaned)
    except ValueError:
        valid = ", ".join(g.value for g in ConcreteGrade)
        raise ValueError(f"Unsupported concrete grade '{grade}'. Supported grades: {valid}")


def normalize_steel_grade(grade: str | SteelGrade) -> SteelGrade:
    if isinstance(grade, SteelGrade):
        return grade
    cleaned = str(grade).strip().upper()
    try:
        return SteelGrade(cleaned)
    except ValueError:
        valid = ", ".join(g.value for g in SteelGrade)
        raise ValueError(f"Unsupported steel grade '{grade}'. Supported grades: {valid}")


def normalize_stress_type(stress_type: str | StressType) -> StressType:
    if isinstance(stress_type, StressType):
        return stress_type
    cleaned = str(stress_type).strip().lower()
    try:
        return StressType(cleaned)
    except ValueError:
        valid = ", ".join(s.value for s in StressType)
        raise ValueError(f"Unsupported stress type '{stress_type}'. Supported types: {valid}")


class DevelopmentLengthResult(BaseModel):
    bar_diameter_mm: float = Field(gt=0)
    concrete_grade: str
    steel_grade: str
    stress_type: str
    tau_bd_base_n_mm2: float
    tau_bd_design_n_mm2: float
    sigma_s_n_mm2: float
    development_length_mm: float
    development_length_factor: float
    code_clause: str = "IS 456:2000 Cl. 26.2.1"
    formula: str = "Ld = (phi * sigma_s) / (4 * tau_bd)"


def get_design_bond_stress(
    concrete_grade: str | ConcreteGrade,
    steel_grade: str | SteelGrade,
    stress_type: str | StressType = StressType.TENSION,
) -> tuple[float, float]:
    """Calculate base and effective design bond stress (tau_bd) per IS 456:2000 Cl. 26.2.1.1.

    Returns:
        tuple[float, float]: (base_tau_bd, design_tau_bd) in N/mm²
    """
    c_grade = normalize_concrete_grade(concrete_grade)
    s_grade = normalize_steel_grade(steel_grade)
    st_type = normalize_stress_type(stress_type)

    base_tau_bd = DESIGN_BOND_STRESS_PLAIN_TENSION[c_grade]
    design_tau_bd = base_tau_bd

    # Clause 26.2.1.1: For deformed bars conforming to IS 1786, bond stress is increased by 60%
    is_deformed = s_grade in (SteelGrade.FE415, SteelGrade.FE500, SteelGrade.FE550)
    if is_deformed:
        design_tau_bd *= 1.6

    # Clause 26.2.1.1: For bars in compression, bond stress is increased by 25%
    if st_type == StressType.COMPRESSION:
        design_tau_bd *= 1.25

    return base_tau_bd, round(design_tau_bd, 4)


def calculate_development_length(
    bar_diameter_mm: float,
    concrete_grade: str | ConcreteGrade,
    steel_grade: str | SteelGrade,
    stress_type: str | StressType = StressType.TENSION,
) -> DevelopmentLengthResult:
    """Calculate development length Ld per IS 456:2000 Clause 26.2.1.

    Formula:
        Ld = (phi * sigma_s) / (4 * tau_bd)
        where:
          phi = bar diameter (mm)
          sigma_s = 0.87 * f_y (design yield stress in bar)
          tau_bd = design bond stress in N/mm²
    """
    if bar_diameter_mm <= 0:
        raise ValueError("Bar diameter must be greater than 0 mm.")

    c_grade = normalize_concrete_grade(concrete_grade)
    s_grade = normalize_steel_grade(steel_grade)
    st_type = normalize_stress_type(stress_type)

    f_y = STEEL_YIELD_STRENGTH[s_grade]
    sigma_s = round(0.87 * f_y, 2)
    base_tau_bd, design_tau_bd = get_design_bond_stress(c_grade, s_grade, st_type)

    ld = (bar_diameter_mm * sigma_s) / (4.0 * design_tau_bd)
    factor = ld / bar_diameter_mm

    return DevelopmentLengthResult(
        bar_diameter_mm=bar_diameter_mm,
        concrete_grade=c_grade.value,
        steel_grade=s_grade.value,
        stress_type=st_type.value,
        tau_bd_base_n_mm2=base_tau_bd,
        tau_bd_design_n_mm2=design_tau_bd,
        sigma_s_n_mm2=sigma_s,
        development_length_mm=round(ld, 1),
        development_length_factor=round(factor, 2),
    )
