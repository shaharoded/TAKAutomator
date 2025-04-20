import pandas as pd
import json
from typing import Tuple, List
from datetime import datetime

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
            self.excel = pd.read_excel(excel_path, sheet_name=None, dtype=str)
            self.excel = {sheet: df.fillna('') for sheet, df in self.excel.items()}
        except Exception as e:
            raise RuntimeError(f"Failed to load Excel file: {e}")

    def validate(self) -> Tuple[bool, str]:
        """Top-level validation entrypoint that applies specific sheet validations."""
        errors = []

        # Check required sheets exist
        missing_sheets = [sheet for sheet in ValidatorConfig.REQUIRED_SHEETS if sheet not in self.excel]
        if missing_sheets:
            errors.append(f"Missing required sheet(s): {', '.join(missing_sheets)}")

        # Validate each sheet if present
        if "raw_concepts" in self.excel:
            valid, msgs = self.validate_raw_concepts(self.excel["raw_concepts"])
            if not valid:
                msgs = "\n".join(msgs)
                errors.append(f"raw_concepts: \n{msgs}")
        if "states" in self.excel:
            valid, msgs = self.validate_states(self.excel["states"])
            msgs = "\n".join(msgs)
            if not valid:
                errors.append(f"states: \n{msgs}")
        if "events" in self.excel:
            valid, msgs = self.validate_events(self.excel["events"])
            if not valid:
                msgs = "\n".join(msgs)
                errors.append(f"events: \n{msgs}")
        if "contexts" in self.excel:
            valid, msgs = self.validate_contexts(self.excel["contexts"])
            if not valid:
                msgs = "\n".join(msgs)
                errors.append(f"contexts: \n{msgs}")
        
        # Validate unique IDs globally
        global_ids = sum([
            self.excel[sheet]['ID'].dropna().tolist() 
            for sheet in ValidatorConfig.REQUIRED_SHEETS 
            if sheet in self.excel], [])
        
        # Identify duplicates
        duplicates = pd.Series(global_ids)
        duplicate_ids = duplicates[duplicates.duplicated()].unique().tolist()

        if duplicate_ids:
            errors.append(f"global-error: Duplicate IDs found across sheets: {duplicate_ids}")
        
        # Validate unique TAK_NAMEs globally
        global_names = sum([
            self.excel[sheet]['TAK_NAME'].dropna().astype(str).tolist()
            for sheet in ValidatorConfig.REQUIRED_SHEETS
            if sheet in self.excel], [])

        duplicates = pd.Series(global_names)
        duplicate_names = duplicates[duplicates.duplicated()].unique().tolist()

        if duplicate_names:
            errors.append(f"global-error: Duplicate TAK_NAMEs found across sheets: {duplicate_names}")
        
        # Validate all raw_concepts are referenced at least once in other sheets.
        raw_concepts_refs = set(
            pd.to_numeric(self.excel['states']["DERIVED_FROM"], errors='coerce').dropna().astype(int).tolist() +
            pd.to_numeric(self.excel['events']["ATTRIBUTES"], errors='coerce').dropna().astype(int).tolist() +
            pd.to_numeric(self.excel['contexts']["INDUCER_ID"], errors='coerce').dropna().astype(int).tolist()
        )
        raw_concept_ids = set(self.excel['raw_concepts']["ID"].dropna().astype(int).tolist())
        missing_refs = raw_concept_ids - raw_concepts_refs
        if missing_refs:
            print(f"[Warning]: raw_concepts are defined but not referenced in other sheets in their DERIVED_FROM or ATTRIBUTES fields: {', '.join(map(str, missing_refs))}")
        
        if errors:
            return False, "!!!Excel file in invalid!!!\n" + "; ".join(errors)
        return True, "Excel file is valid."

    def validate_raw_concepts(self, df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """
        Validate structure and required values for the 'raw_concepts' sheet.

        This includes:
        - Ensuring non-empty and unique IDs.
        - Checking that numeric concepts include all required numeric fields.
        - Checking that nominal concepts include the ALLOWED_VALUES_NOMINAL field.

        Returns:
            Tuple:
                - bool indicating if validation passed.
                - list of error messages (empty if valid).
        """
        errors = []

        # Check that ID is present and unique
        if df["ID"].isnull().any() or (df["ID"].str.strip() == "").any():
            errors.append("One or more rows in raw_concepts have an empty ID.")
        if df["ID"].duplicated().any():
            errors.append("IDs in raw_concepts are not unique.")

        for idx, row in df.iterrows():
            typ = row["TYPE"].strip().lower() if pd.notna(row["TYPE"]) else ""
            if typ == "numeric-raw-concept":
                for col in ["ALLOWED_VALUES_MIN", "ALLOWED_VALUES_MAX", "ALLOWED_VALUES_UNITS", "ALLOWED_VALUES_SCALE"]:
                    if col not in df.columns or pd.isna(row[col]) or row[col].strip() == "":
                        errors.append(f"Row {idx+2} (ID={row['ID']}): '{col}' must be specified for numeric-raw-concept.")
            if typ == "time-raw-concept":
                for col in ["ALLOWED_VALUES_MIN", "ALLOWED_VALUES_MAX"]:
                    if col not in df.columns or pd.isna(row[col]) or str(row[col]).strip() == "":
                        errors.append(f"Row {idx+2} (ID={row['ID']}): '{col}' must be specified for time-raw-concept.")
                    else:
                        value = str(row[col]).strip()
                        try:
                            datetime.strptime(value, "%d/%m/%Y")
                        except ValueError:
                            errors.append(f"Row {idx+2} (ID={row['ID']}): '{col}' has invalid date format (expected DD/MM/YYYY).")
            elif typ == "nominal-raw-concept":
                if "ALLOWED_VALUES_NOMINAL" not in df.columns or pd.isna(row["ALLOWED_VALUES_NOMINAL"]) or row["ALLOWED_VALUES_NOMINAL"].strip() == "":
                    errors.append(f"Row {idx+2} (ID={row['ID']}): 'ALLOWED_VALUES_NOMINAL' must be specified for nominal-raw-concept.")

        if errors:
            return False, errors
        return True, ["Raw concepts are valid."]

    def validate_states(self, df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """
        Validate structure and content for the 'states' sheet.

        This includes:
        - Ensuring non-empty and unique IDs.
        - Validating DERIVED_FROM contains only known IDs.
        - Ensuring valid MAPPING and STATE_LABELS for numeric-derived states.
        - Ensuring STATE_LABELS match raw concept values for nominal-derived states.
        - Checking MAPPING fully aligns with raw concept min/max ranges and is logically consistent.

        Returns:
            Tuple:
                - bool indicating if validation passed.
                - list of error messages (empty if valid).
        """
        errors = []

        # Validate basic ID requirements
        if df["ID"].isnull().any() or (df["ID"].str.strip() == "").any():
            errors.append("One or more rows in states have an empty STATE_ID.")
        if df["ID"].duplicated().any():
            errors.append("STATE_IDs in states are not unique.")
        if df["DERIVED_FROM"].isnull().any() or (df["DERIVED_FROM"].str.strip() == "").any():
            errors.append("One or more rows in states have an empty Derived_From.")

        # Gather allowed IDs from raw_concepts and events
        allowed_ids = set()
        if "raw_concepts" in self.excel:
            allowed_ids.update(self.excel["raw_concepts"]["ID"].dropna().str.strip().tolist())
        if "events" in self.excel:
            allowed_ids.update(self.excel["events"]["ID"].dropna().str.strip().tolist())

        # Map raw_concepts ID -> TYPE
        raw_df = self.excel.get("raw_concepts", pd.DataFrame())
        raw_types = {
            row["ID"].strip(): row["TYPE"].strip().lower()
            for _, row in raw_df.iterrows()
            if pd.notna(row["ID"]) and pd.notna(row["TYPE"])
        }

        for idx, row in df.iterrows():
            row_errors = []

            # Check that all referenced IDs exist
            derived = row["DERIVED_FROM"].strip()
            derived_ids = [d.strip() for d in derived.split(",") if d.strip()]
            if len(derived_ids) > 1:
                print(f"[Warning]: State {row['ID']} is is derived from more then 1 concept: {derived_ids} which the system can't currently enforce. Skipping on validation.")
                continue
            derived_id = derived_ids[0]
            if derived_id not in allowed_ids:
                row_errors.append(f"DERIVED_FROM contains undefined ID '{derived_id}'.")
            if not raw_types.get(derived_id, None):
                print(f"[Warning]: State {row['ID']}: Derived concept '{derived_id}' is not a raw concept (likely an event) which the system can't currently enforce. Skipping value-based validation.")
                continue 

            # Determine type of raw concept being derived from
            is_nominal = raw_types.get(derived_id, "") == "nominal-raw-concept"
            is_numeric = raw_types.get(derived_id, "") == "numeric-raw-concept"

            # Always attempt to parse STATE_LABELS (needed for both nominal and numeric base types)
            try:
                labels = json.loads(row["STATE_LABELS"].strip())
            except Exception as e:
                row_errors.append(f"error parsing STATE_LABELS: {e}")
                errors.append(f"Row {idx+2} (ID={row['ID']}): " + "; ".join(row_errors))
                continue

            if is_nominal:
                # For nominal types: STATE_LABELS must match allowed values
                derived_id = derived_ids[0]
                raw_row = raw_df[raw_df["ID"].str.strip() == derived_id]
                expected_raw = raw_row.iloc[0].get("ALLOWED_VALUES_NOMINAL", "")
                try:
                    expected_list = json.loads(expected_raw) if expected_raw else []
                except json.JSONDecodeError:
                    expected_list = [v.strip() for v in expected_raw.split(",")]  # fallback in case it's not a JSON array
                if sorted(expected_list) != sorted(labels):
                    row_errors.append(f"STATE_LABELS {labels} do not match ALLOWED_VALUES_NOMINAL {expected_list}.")

            elif is_numeric:
                # For numeric types: check MAPPING + STATE_LABELS consistency
                try:
                    bins = json.loads(row["MAPPING"].strip())
                except Exception as e:
                    row_errors.append(f"error parsing MAPPING: {e}")
                    errors.append(f"Row {idx+2} (ID={row['ID']}): " + "; ".join(row_errors))
                    continue

                # Validate structure of MAPPING and STATE_LABELS
                if not isinstance(bins, list) or not isinstance(labels, list):
                    row_errors.append("MAPPING and STATE_LABELS must be lists.")
                elif len(bins) != len(labels):
                    row_errors.append("MAPPING and STATE_LABELS must have the same length.")

                # If a single raw concept, validate range bounds
                raw_row = raw_df[raw_df["ID"].str.strip() == derived_id]
                if not raw_row.empty:
                    raw_row = raw_row.iloc[0]
                    min_val = raw_row.get("ALLOWED_VALUES_MIN")
                    max_val = raw_row.get("ALLOWED_VALUES_MAX")
                    try:
                        if min_val is not None and float(bins[0][0]) != float(min_val):
                            row_errors.append(f"first bin lower bound ({bins[0][0]}) does not match raw concept min ({min_val}).")
                        if max_val is not None and float(bins[-1][1]) != float(max_val):
                            row_errors.append(f"last bin upper bound ({bins[-1][1]}) does not match raw concept max ({max_val}).")
                    except Exception:
                        row_errors.append("error comparing bin bounds with raw concept min/max.")
                else:
                    row_errors.append(f"Raw concept with ID '{derived_id}' not found for bin alignment check.")

                # Validate MAPPING continuity and no overlap
                range_issues = self._validate_range_list_integrity(bins)
                row_errors.extend(range_issues)
            
            else:
                print(f"[Warning]: State {row['ID']} is based on unsupported type of derived concept: {row['DERIVED_FROM']}. Needs further develoopment.")

            # Append row-level errors if any
            if row_errors:
                errors.append(f"Row {idx+2} (ID={row['ID']}): " + "; ".join(row_errors))

        if errors:
            return False, errors
        return True, ["States are valid."]
    
    def _validate_range_list_integrity(self, ranges: List[List[float]]) -> List[str]:
        """
        Validates that a list of numeric ranges is sorted, non-overlapping, and gap-free.

        Args:
            ranges (List[List[float]]): List of [start, end] numeric ranges.

        Returns:
            List[str]: List of issues found in the range structure.
        """
        issues = []
        if not ranges:
            return ["Empty range list provided."]

        # Sort by start of range
        ranges_sorted = sorted(ranges, key=lambda r: r[0])

        for i, (start, end) in enumerate(ranges_sorted):
            if start >= end:
                issues.append(f"Range {i} is invalid: start {start} is not less than end {end}.")

            if i > 0:
                prev_end = ranges_sorted[i-1][1]
                if start < prev_end:
                    issues.append(f"Range {i} overlaps with previous range: starts at {start}, previous ends at {prev_end}.")
                elif start > prev_end:
                    issues.append(f"Gap detected: Range {i-1} ends at {prev_end}, but Range {i} starts at {start}.")

        return issues
    
    def validate_events(self, df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """
        Validate structure and content of events sheet.
        
        This includes checking:
            - Required sheet existence
            - No duplicate or empty IDs
            - All attributes are valid raw concepts, if exists. 
        """
        errors = []
        if df["ID"].isnull().any() or (df["ID"].str.strip() == "").any():
            errors.append("One or more rows in events have an empty EVENT_ID.")
        if df["ID"].duplicated().any():
            errors.append("IDs in events are not unique.")
        
        # If DERIVED_FROM is present in events, validate its entries.
        allowed_ids = set()
        if "raw_concepts" in self.excel:
            allowed_ids.update(self.excel["raw_concepts"]["ID"].dropna().str.strip().tolist())
        if "events" in self.excel:
            allowed_ids.update(self.excel["events"]["ID"].dropna().str.strip().tolist())
        for idx, row in df.iterrows():
            derived = row["ATTRIBUTES"].strip() if pd.notna(row["ATTRIBUTES"]) else ""
            if derived:
                derived_ids = [d.strip() for d in derived.split(",") if d.strip()]
                for d in derived_ids:
                    if d not in allowed_ids:
                        errors.append(f"Row {idx+2} (ID={row['ID']}): ATTRIBUTES contains undefined ID '{d}'.")
        if errors:
            return False, errors        
        return True, ["Events are valid."]
    
    def validate_contexts(self, df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """
        Validates the context TAKs Excel sheet.

        Checks:
        - No duplicate context IDs.
        - Each inducer ID exists in the global concept/event/state set.
        - Each inducer has at least a 'from' or 'until' block.
        - If 'from' or 'until' is present, its subfields (value and granularity) must exist.
        - If a clipper is defined, all its related fields must be non-empty and valid.
        """
        errors = []

        # Dynamically compute all valid IDs from the other TAK sheets
        valid_ids = set()
        for sheet in ["raw_concepts", "states", "events"]:
            if sheet in self.excel:
                valid_ids.update(self.excel[sheet]["ID"].dropna().astype(str).tolist())

        # Check for duplicate IDs
        if df["ID"].duplicated().any():
            errors.append("Duplicate context IDs found.")

        for idx, row in df.iterrows():
            row_errors = []
            row_id = row.get("ID", f"Row {idx+2}")

            inducer_id = str(row.get("INDUCER_ID", "")).strip()
            if not inducer_id:
                row_errors.append("INDUCER_ID is missing.")
            elif inducer_id not in valid_ids:
                row_errors.append(f"INDUCER_ID '{inducer_id}' does not exist in the TAK entity list.")

            from_ok = str(row.get("FROM_BOUND", "")).strip() != ""
            until_ok = str(row.get("UNTIL_BOUND", "")).strip() != ""

            if not (from_ok or until_ok):
                row_errors.append("At least one of FROM_BOUND or UNTIL_BOUND must be defined for the inducer.")

            if from_ok:
                if str(row.get("FROM_SHIFT", "")).strip() == "" or str(row.get("FROM_GRANULARITY", "")).strip() == "":
                    row_errors.append("FROM_SHIFT and FROM_GRANULARITY must be provided if FROM_BOUND is specified.")

            if until_ok:
                if str(row.get("UNTIL_SHIFT", "")).strip() == "" or str(row.get("UNTIL_GRANULARITY", "")).strip() == "":
                    row_errors.append("UNTIL_SHIFT and UNTIL_GRANULARITY must be provided if UNTIL_BOUND is specified.")

            clipper_id = str(row.get("CLIPPER_ID", "")).strip()
            if clipper_id:
                for field in ["CLIPPER_BOUND", "CLIPPER_SHIFT", "CLIPPER_GRANULARITY"]:
                    if str(row.get(field, "")).strip() == "":
                        row_errors.append(f"{field} must be defined if CLIPPER_ID is present.")

            if row_errors:
                errors.append(f"Row {idx+2} (ID={row_id}): " + "; ".join(row_errors))

        return (False, errors) if errors else (True, ["Contexts are valid."])


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