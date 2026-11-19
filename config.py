"""Configuration module for RiceVision HMI & FBAR 1000 System.
Loads configuration from environment variables with industrial defaults.
"""
import os

# ---------------------------------------------------------------------------
# Authentication & Passcodes
# ---------------------------------------------------------------------------
# HTTP Basic Auth: format 'user:password'. If unset, server refuses to boot.
HMI_AUTH = os.environ.get("HMI_AUTH")

# Station & Recipe Passcodes
STN1_CONTROL_PASSCODE = os.environ.get("STN1_CONTROL_PASSCODE", "1111")
STN1_LOADCELL_PASSCODE = os.environ.get("STN1_LOADCELL_PASSCODE", "2222")
STN2_CAL_PASSCODE = os.environ.get("STN2_CAL_PASSCODE", "3333")
RECIPE_CAL_PASSCODE = os.environ.get("RECIPE_CAL_PASSCODE", "4444")

PASSCODES = {
    "stn1_control": STN1_CONTROL_PASSCODE,
    "stn1_loadcell": STN1_LOADCELL_PASSCODE,
    "stn2_cal": STN2_CAL_PASSCODE,
    "recipe_cal": RECIPE_CAL_PASSCODE,
}

# Reverse lookup: code -> role
CODE_TO_ROLE = {
    STN1_CONTROL_PASSCODE: "stn1_control",
    STN1_LOADCELL_PASSCODE: "stn1_loadcell",
    STN2_CAL_PASSCODE: "stn2_cal",
    RECIPE_CAL_PASSCODE: "recipe_cal",
}

# Unlock token parameters
TOKEN_TTL_S = int(os.environ.get("CAL_TOKEN_TTL_S", "300"))
LOCKOUT_ATTEMPTS = int(os.environ.get("CAL_LOCKOUT_ATTEMPTS", "5"))
LOCKOUT_DURATION_S = int(os.environ.get("CAL_LOCKOUT_DURATION_S", "30"))

# ---------------------------------------------------------------------------
# Validation Constraints
# ---------------------------------------------------------------------------
RECIPE_LIMITS = {
    "repeatLength": {"min": 100, "max": 2000, "unit": "mm"},
    "width": {"min": 1, "max": 1000, "unit": "mm"},
    "markWindow": {"min": 10, "max": 99, "unit": "mm"},
    "markOffset": {"min": -999, "max": 999, "unit": "mm"},
    "sTensionTarget": {"min": 0.0, "max": 99.9, "unit": "kg"},
    "netWeight": {"min": 1.0, "max": 100.0, "unit": "kg"},
}

STN1_CONTROL_LIMITS = {
    "acErr": {"min": 0.01, "max": 9.99},
    "dcErr": {"min": 0, "max": 999},
    "displayDamp": {"min": 1, "max": 99},
    "brakePower": {"min": 0, "max": 100},
    "brakeType": ["Pneumatic", "Powder Brake"],
}

STN1_LOADCELL_LIMITS = {
    "loadcellCapacity": {"min": 1, "max": 999},
    "knownWeight": {"min": 0, "max": 999},
}
