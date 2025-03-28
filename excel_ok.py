import pandas as pd
import json
from typing import Tuple

# Local Code
from Config.validator_config import ValidatorConfig


class Excelok:
    """
    Validates the structural and logical consistency of a TAK definition Excel file
    used to generate valid TAK XML files.

    This includes checking:
      - Required sheet existence and required columns
      - ID uniqueness and non-emptiness
      - Specific column dependencies based on the concept type (numeric, nominal, etc.)
      - Valid JSON structure for MAPPING and STATE_LABELS in states
      - Valid DERIVED_FROM or ATTRIBUTES relationships across sheets
    """
    def __init__(self, excel_path: str):
        self.excel_path = excel_path
        try:
            # Read all sheets as DataFrames with string type (to avoid type conversion issues)
            self.sheets = pd.read_excel(excel_path, sheet_name=None, dtype=str)
        except Exception as e:
            raise RuntimeError(f"Failed to load Excel file: {e}")

    def validate(self) -> Tuple[bool, str]:
        """Top-level validation entrypoint that applies specific sheet validations."""
        errors = []

        # Check required sheets exist
        missing_sheets = [sheet for sheet in ValidatorConfig.REQUIRED_SHEETS if sheet not in self.sheets]
        if missing_sheets:
            errors.append(f"Missing required sheet(s): {', '.join(missing_sheets)}")

        # Validate each sheet if present
        if "raw_concepts" in self.sheets:
            valid, msg = self.validate_raw_concepts(self.sheets["raw_concepts"])
            if not valid:
                errors.append(f"raw_concepts: \n{msg}")
        if "states" in self.sheets:
            valid, msg = self.validate_states(self.sheets["states"])
            if not valid:
                errors.append(f"states: \n{msg}")
        if "events" in self.sheets:
            valid, msg = self.validate_events(self.sheets["events"])
            if not valid:
                errors.append(f"events: \n{msg}")
        
        # Validate unique IDs globally
        global_ids = sum([self.sheets[sheet]['ID'].dropna().tolist() for sheet in ValidatorConfig.REQUIRED_SHEETS if sheet in self.sheets], [])
        if len(global_ids) != len(set(global_ids)):
            errors.append("global-error: Global IDs across raw_concepts, states, and events are not unique.")
        
        if errors:
            return False, "!!!Excel file in invalid!!!\n" + "; ".join(errors)
        return True, "Excel file is valid."

    def validate_raw_concepts(self, df: pd.DataFrame) -> Tuple[bool, str]:
        """Validate structure and required values for raw_concepts sheet."""
        # Basic required columns for raw_concepts
        required_cols = ["ID", "TAK_NAME", "TYPE", "GOOD_BEFORE", "GOOD_BEFORE_UNIT", "GOOD_AFTER", "GOOD_AFTER_UNIT",
                         "downward-hereditary", "forward", "backward", "solid", "concatenable", "gestalt"]
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            return False, f"Missing columns: {', '.join(missing)}"

        # Check that ID is present and unique
        if df["ID"].isnull().any() or (df["ID"].str.strip() == "").any():
            return False, "One or more rows in raw_concepts have an empty ID."
        if df["ID"].duplicated().any():
            return False, "IDs in raw_concepts are not unique."

        for idx, row in df.iterrows():
            typ = row["TYPE"].strip().lower() if pd.notna(row["TYPE"]) else ""
            if typ == "raw-numeric":
                for col in ["MIN_VALUE", "MAX_VALUE", "UNIT", "SCALE"]:
                    if col not in df.columns or pd.isna(row[col]) or row[col].strip() == "":
                        return False, f"Row {idx+2} (ID={row['ID']}): '{col}' must be specified for raw-numeric."
            elif typ == "raw-nominal":
                if "NOMINAL_VALUES" not in df.columns or pd.isna(row["NOMINAL_VALUES"]) or row["NOMINAL_VALUES"].strip() == "":
                    return False, f"Row {idx+2} (ID={row['ID']}): 'NOMINAL_VALUES' must be specified for raw-nominal concept."
        return True, "Raw concepts are valid."

    def validate_states(self, df: pd.DataFrame) -> Tuple[bool, str]:
        """Validate structure and content for states sheet."""
        required_cols = ["ID", "TAK_NAME", "DERIVED_FROM", "Mapping_Rank_Selection_Criteria", 
                         "MAPPING", "STATE_LABELS", "GOOD_BEFORE", "GOOD_BEFORE_UNIT", "GOOD_AFTER", "GOOD_AFTER_UNIT",
                         "downward-hereditary",	"forward",	"backward",	"solid", "concatenable", "gestalt"]
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            return False, f"Missing columns: {', '.join(missing)}"
        
        # Check STATE_ID non-empty and unique
        if df["ID"].isnull().any() or (df["ID"].str.strip() == "").any():
            return False, "One or more rows in states have an empty STATE_ID."
        if df["ID"].duplicated().any():
            return False, "STATE_IDs in states are not unique."

        # Check that Derived_From is non-empty
        if df["DERIVED_FROM"].isnull().any() or (df["DERIVED_FROM"].str.strip() == "").any():
            return False, "One or more rows in states have an empty Derived_From."

        # Global allowed IDs for DERIVED_FROM: union of raw_concepts and events
        allowed_ids = set()
        if "raw_concepts" in self.sheets:
            allowed_ids.update(self.sheets["raw_concepts"]["ID"].dropna().str.strip().tolist())
        if "events" in self.sheets:
            allowed_ids.update(self.sheets["events"]["ID"].dropna().str.strip().tolist())

        for idx, row in df.iterrows():
            derived = row["DERIVED_FROM"].strip()
            derived_ids = [d.strip() for d in derived.split(",") if d.strip()]
            for d in derived_ids:
                if d not in allowed_ids:
                    return False, f"Row {idx+2} (ID={row['ID']}): DERIVED_FROM contains undefined ID '{d}'."
        
        # Build a dictionary from the raw_concepts sheet: ID -> TYPE
        raw_types = {row["ID"].strip(): row["TYPE"].strip().lower() for _, row in self.sheets["raw_concepts"].iterrows()}
        
        # For each state, check if its DERIVED_FROM refers to a raw concept that is not boolean.
        # If none of the derived IDs is raw-boolean, then MAPPING and STATE_LABELS must be valid JSON lists of equal length.
        for idx, row in df.iterrows():
            derived_ids = [d.strip() for d in row["DERIVED_FROM"].split(",") if d.strip()]
            skip_mapping = any((d in raw_types and raw_types[d] == "nominal-raw-concept") for d in derived_ids)
            if not skip_mapping:
                try:
                    bins = json.loads(row["MAPPING"].strip())
                    labels = json.loads(row["STATE_LABELS"].strip())
                except Exception as e:
                    return False, f"Row {idx+2} (ID={row['ID']}): error parsing MAPPING or STATE_LABELS: {e}"
                if not isinstance(bins, list) or not isinstance(labels, list):
                    return False, f"Row {idx+2} (ID={row['ID']}): MAPPING and STATE_LABELS must be lists."
                if len(bins) != len(labels):
                    return False, f"Row {idx+2} (ID={row['ID']}): MAPPING and STATE_LABELS must have the same length."
        return True, "States are valid."

    def validate_events(self, df: pd.DataFrame) -> Tuple[bool, str]:
        """Validate structure and content of events sheet."""
        required_cols = ["ID", "TAK_NAME", "ATTRIBUTES"]
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            return False, f"Missing columns: {', '.join(missing)}"
        if df["ID"].isnull().any() or (df["ID"].str.strip() == "").any():
            return False, "One or more rows in events have an empty EVENT_ID."
        if df["ID"].duplicated().any():
            return False, "IDs in events are not unique."
        # Optionally, check if ATTRIBUTES is provided then non-empty.
        if df["ATTRIBUTES"].isnull().any() or (df["ATTRIBUTES"].str.strip() == "").any():
            return False, "One or more rows in events have an empty attribute."
        
        # If DERIVED_FROM is present in events, validate its entries.
        allowed_ids = set()
        if "raw_concepts" in self.sheets:
            allowed_ids.update(self.sheets["raw_concepts"]["ID"].dropna().str.strip().tolist())
        if "events" in self.sheets:
            allowed_ids.update(self.sheets["events"]["ID"].dropna().str.strip().tolist())
        for idx, row in df.iterrows():
            derived = row["ATTRIBUTES"].strip() if pd.notna(row["ATTRIBUTES"]) else ""
            if derived:
                derived_ids = [d.strip() for d in derived.split(",") if d.strip()]
                for d in derived_ids:
                    if d not in allowed_ids:
                        return False, f"Row {idx+2} (ID={row['ID']}): ATTRIBUTES contains undefined ID '{d}'."
        
        return True, "Events are valid."


if __name__ == "__main__":
    import sys
    excel_path = ValidatorConfig.EXCEL_PATH

    try:
        validator = Excelok(excel_path)
    except Exception as e:
        sys.exit(f"Error loading Excel: {e}")

    valid, msg = validator.validate()
    if valid:
        print("Excel file is valid!")
    else:
        print(msg)