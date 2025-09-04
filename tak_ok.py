import os
import json
from pydoc import doc
from lxml import etree
from typing import Tuple, List
import pandas as pd
import re

# Local Code
from Config.validator_config import ValidatorConfig
from utils import get_template


class TAKok:
    """
    TAKok is a validation class that verifies TAK XML files both against the provided XSD schema
    and cross-checks their structure and content with business logic defined in an Excel configuration file.
    
    The class ensures:
    - Structural validity using XML Schema (XSD)
    - Business rule consistency by comparing with taks.xlsx definitions
    
    Attributes:
        schema (etree.XMLSchema): Compiled XML schema for validation
        excel (dict): Dictionary of DataFrames from Excel, keyed by sheet name
    """

    def __init__(self, schema_path: str, excel_path: str):
        """
        Initialize TAKok with paths to the schema and the business logic Excel file.

        Args:
            schema_path (str): Path to the XML schema (.xsd)
            excel_path (str): Path to the business logic Excel file (e.g., taks.xlsx)

        Raises:
            RuntimeError: If schema or Excel cannot be loaded
        """
        try:
            self.schema_doc = etree.parse(schema_path)
            self.schema = etree.XMLSchema(self.schema_doc)
        except Exception as e:
            raise RuntimeError(f"Failed to load schema from {schema_path}: {e}")

        try:
            self.excel = pd.read_excel(excel_path, sheet_name=None, dtype=str)
            self.excel = {sheet: df.fillna('') for sheet, df in self.excel.items()}
        except Exception as e:
            raise RuntimeError(f"Failed to load Excel from {excel_path}: {e}")

    def validate(self, tak_text: str, tak_id: str = None) -> Tuple[bool, str, List[str]]:
        """
        Validate a TAK XML string against both the schema and business rules.

        Args:
            tak_text (str): The TAK XML content as a string
            tak_id (str, optional): TAK identifier. If None, will extract from XML.

        Returns:
            Tuple[bool, str, List[str]]: 
                - (True, 'OK: ', ["Valid"]) if valid
                - (False, 'Critical error: ', ["issue1, issue2..."]) for structural issues that should break the loop and LLM should fix.
                - (False, 'Business logic issues: ', ["issue1, issue2..."]) for fixable problems LLM can iterate on
        """
        # === CRITICAL: Invalid XML ===
        try:
            doc = etree.fromstring(tak_text.encode('utf-8'))
        except etree.XMLSyntaxError as e:
            return False, 'Critical error: ', [f"XML syntax error: {e}"]

        # === CRITICAL: Schema invalid ===
        if not self.schema.validate(doc):
            errors = [str(error) for error in self.schema.error_log]
            return False, 'Critical schema validation errors: ', errors

        # === CRITICAL: Type or ID mismatch ===
        root_tag = doc.tag
        tak_id_from_xml = doc.get("id")
        tak_id = tak_id or tak_id_from_xml

        if tak_id != tak_id_from_xml:
            return False, 'Critical error: ', [f"TAK ID mismatch. Expected={tak_id}, but got={tak_id_from_xml} in XML."]

        sheet = self._get_sheet_for_tag(root_tag)
        if sheet is None:
            return False, 'Critical error: ', [f"Unrecognized TAK type with root tag <{root_tag}>."]

        df = self.excel[sheet]
        row = df[df['ID'] == tak_id]
        if row.empty:
            return False, 'Critical error: ', [f"No matching ID '{tak_id}' found in sheet '{sheet}'."]

        # === BUSINESS LOGIC VALIDATION ===
        row = row.iloc[0]
        issues = []

        if sheet == "raw_concepts":
            typ = row.get("TYPE", "").lower()
            if typ == "numeric-raw-concept" and doc.find(".//numeric-allowed-values") is None:
                issues.append("Missing <numeric-allowed-values> for numeric-raw-concept.")
            elif typ == "nominal-raw-concept" and doc.find(".//nominal-allowed-values") is None:
                issues.append("Missing <nominal-allowed-values> for nominal-raw-concept.")
            elif typ == "time-raw-concept" and doc.find(".//time-allowed-values") is None:
                issues.append("Missing <time-allowed-values> for time-raw-concept.")

        elif sheet == "states":
            if doc.find(".//derived-from") is None:
                issues.append("Missing <derived-from> block in state.")
            if pd.notna(row.get("MAPPING")) and row.get("MAPPING").strip():
                if doc.find(".//mapping-function") is None:
                    issues.append("Missing <mapping-function> element despite MAPPING specified in Excel.")
                else:
                    try:
                        # Parse Excel MAPPING column as a list of [min, max] lists
                        excel_bins = json.loads(row["MAPPING"])
                        excel_bins = [(float(b[0]), float(b[1])) for b in excel_bins if isinstance(b, list) and len(b) == 2]
                    except Exception as e:
                        issues.append(f"Failed to parse Excel MAPPING as bins: {e}")
                        excel_bins = []

                    # Add threshold logic validation
                    issues += self._validate_state_range_coverage(doc, excel_bins)

        elif sheet == "events":
            if doc.find(".//Attributes") is None:
                issues.append("Missing <Attributes> block in event.")
        
        elif sheet == "contexts":
            inducers = doc.findall(".//inducer-entity")
            if not inducers:
                issues.append("Missing <inducer-entity> block in context.")

            for inducer in inducers:
                has_from = inducer.find(".//from") is not None
                has_until = inducer.find(".//until") is not None
                if not (has_from or has_until):
                    issues.append(f"Inducer {inducer.get('id')} must have at least <from> or <until> block.")

                for tag in ["from", "until"]:
                    tag_block = inducer.find(tag)
                    if tag_block is not None:
                        tg = tag_block.find(".//time-gap")
                        if tg is None or not tg.get("value") or not tg.get("granularity"):
                            issues.append(f"{tag.title()} block in inducer {inducer.get('id')} missing value or granularity.")

            clippers = doc.findall(".//clipper-entity")
            for clipper in clippers:
                if clipper.find(".//from") is None or clipper.find(".//time-gap") is None:
                    issues.append(f"Clipper {clipper.get('id')} is missing <from> or <time-gap>.")
                else:
                    tg = clipper.find(".//time-gap")
                    if not tg.get("value") or not tg.get("granularity"):
                        issues.append(f"Clipper {clipper.get('id')} has invalid <time-gap> settings.")
        
        elif sheet == "trends":
            # === Validate <derived-from> presence ===
            if doc.find(".//derived-from") is None:
                issues.append("Missing <derived-from> block in trend.")

            # === Validate gradient-trend-allowed-values ===
            if doc.find(".//gradient-trend-allowed-values") is None:
                issues.append("Missing <gradient-trend-allowed-values> in trend.")

            # === Validate ordinal labels ===
            trend_labels = {"DEC", "SAME", "INC"}
            found_labels = {
                ov.get("value") for ov in doc.findall(".//ordinal-allowed-value")
                if ov.get("value")
            }
            missing = trend_labels - found_labels
            if missing:
                issues.append(f"Missing expected trend label(s): {', '.join(sorted(missing))}")

            # === Validate time-steady block ===
            time_steady = doc.find(".//time-steady")
            if time_steady is None:
                issues.append("Missing <time-steady> block in trend.")
            else:
                if not time_steady.get("value") or not time_steady.get("granularity"):
                    issues.append("Missing or empty 'value' or 'granularity' attributes in <time-steady>.")
            
            # === Enforce local-persistence presence & attributes ===
            lp = doc.find(".//local-persistence")
            if lp is None:
                issues.append("Missing <local-persistence> in trend persistence.")
            else:
                gb = doc.find(".//good-before")
                ga = doc.find(".//good-after")
                if gb is None or not gb.get("value") or not gb.get("granularity"):
                    issues.append("Missing or invalid <good-before value= granularity=> in <local-persistence>.")
                if ga is None or not ga.get("value") or not ga.get("granularity"):
                    issues.append("Missing or invalid <good-after value= granularity=> in <local-persistence>.")

        # Get correct template
        template_str = get_template(sheet, row)
        issues += self._validate_against_businesslogic_values(doc, row, template_str)
        if sheet in ["raw_concepts", "states"]:
            issues += self._validate_allowed_values_against_excel(doc, row)

        if issues:
            return False, "Business logic issues: ", issues

        return True, 'OK: ', ["TAK is Valid"]

    def _get_sheet_for_tag(self, tag: str) -> str:
        """
        Internal helper to map root XML tag to Excel sheet name.

        Args:
            tag (str): Root tag from the TAK XML (e.g., 'state')

        Returns:
            str: Corresponding sheet name (e.g., 'states') or None if unknown
        """
        tag_to_sheet = {
            "numeric-raw-concept": "raw_concepts",
            "nominal-raw-concept": "raw_concepts",
            "time-raw-concept": "raw_concepts",
            "state": "states",
            "event": "events",
            "pattern": "patterns",
            "context": "contexts",
            "trend": "trends",
            "scenario": "scenarios"
        }
        return tag_to_sheet.get(tag)

    def _validate_state_range_coverage(self, doc: etree._Element, excel_bins: List[Tuple[float, float]]) -> List[str]:
        """
        Validates the <mapping-function> coverage in a <state> TAK:
        - All bins must follow the format: lower_bound <= x < upper_bound
        - Validates no overlaps or gaps between adjacent bins
        - Verifies the thresholds used in XML match those defined in Excel

        Args:
            doc: The parsed XML <state> element
            excel_bins: A list of (min, max) pairs from the Excel's MAPPING column

        Returns:
            A list of human-readable issues found in the XML definition.
        """
        def extract_bounds(bin_elem) -> Tuple[Tuple[float, str], Tuple[float, str]]:
            logic = bin_elem.find(".//logical-function")
            if logic is not None:
                comparisons = logic.findall(".//comparison-function")
                lower = upper = None
                for comp in comparisons:
                    op = comp.get("comparison-operator")
                    val = float(comp.findtext(".//double"))
                    if op.startswith("bigger"):
                        lower = (val, op)
                    elif op.startswith("smaller"):
                        upper = (val, op)
                return lower, upper
            return None, None

        def is_overlap(prev_upper, curr_lower):
            val_u, op_u = prev_upper
            val_l, op_l = curr_lower
            if val_u > val_l:
                return True
            elif val_u == val_l:
                return not (op_u == "smaller" and op_l == "bigger-equal")
            return False

        def is_gap(prev_upper, curr_lower):
            val_u, _ = prev_upper
            val_l, _ = curr_lower
            return val_u != val_l
        
        def describe_range(lower: Tuple[float, str], upper: Tuple[float, str]) -> str:
            """
            Convert a lower and upper bound with operators into a readable string like:
            '70 <= x < 140'
            """
            op_map = {
                "bigger": ">",
                "bigger-equal": ">=",
                "smaller": "<",
                "smaller-equal": "<="
            }
            lower_op = op_map.get(lower[1], lower[1])
            upper_op = op_map.get(upper[1], upper[1])
            return f"x {lower_op} {lower[0]} AND x {upper_op} {upper[0]}"

        issues = []
        bins = doc.findall(".//mapping-function-2-value")
        if not bins:
            return ["Missing <mapping-function-2-value> bins."]

        parsed_bins = []
        for idx, bin_elem in enumerate(bins):
            label = bin_elem.get("value", f"Bin {idx}")
            lower, upper = extract_bounds(bin_elem)

            if not lower or not upper:
                issues.append(f"Bin {idx} ('{label}') must contain BOTH lower and upper bounds using logical-function.")
                continue

            range_desc = describe_range(lower, upper)
            issues.append(f"Bin {idx} ('{label}') range: {range_desc}")
            parsed_bins.append({
                "idx": idx,
                "label": label,
                "lower": lower,
                "upper": upper,
                "desc": range_desc
            })

        # Sort bins by lower value
        sorted_bins = sorted(parsed_bins, key=lambda b: b["lower"][0])
        actual_issues = []

        for i in range(len(sorted_bins) - 1):
            b1 = sorted_bins[i]
            b2 = sorted_bins[i + 1]

            if is_overlap(b1["upper"], b2["lower"]):
                actual_issues.append(
                    f"Overlap between Bin {b1['idx']} ('{b1['label']}') [{b1['desc']}] and "
                    f"Bin {b2['idx']} ('{b2['label']}') [{b2['desc']}]."
                )
            elif is_gap(b1["upper"], b2["lower"]):
                actual_issues.append(
                    f"Gap between Bin {b1['idx']} ('{b1['label']}') [{b1['desc']}] and "
                    f"Bin {b2['idx']} ('{b2['label']}') [{b2['desc']}]."
                )

        xml_bounds_set = {round(b["lower"][0], 6) for b in sorted_bins}.union(
            {round(b["upper"][0], 6) for b in sorted_bins}
        )
        excel_bounds_set = {round(low, 6) for low, high in excel_bins}.union(
            {round(high, 6) for low, high in excel_bins}
        )

        missing_in_xml = excel_bounds_set - xml_bounds_set
        if missing_in_xml:
            actual_issues.append(f"Threshold mismatch: The following values exist in Excel but not in XML: {sorted(missing_in_xml)}")

        # Threshold value checks
        xml_bounds_set = {round(b["lower"][0], 6) for b in sorted_bins}.union(
            {round(b["upper"][0], 6) for b in sorted_bins}
        )
        excel_bounds_set = {round(low, 6) for low, high in excel_bins}.union(
            {round(high, 6) for low, high in excel_bins}
        )

        missing_from_excel = sorted(xml_bounds_set - excel_bounds_set)
        if missing_from_excel:
            actual_issues.append(f"These values are used in XML but not found in Excel MAPPING: {missing_from_excel}")

        # Only show range descriptions if there is a problem
        if actual_issues:
            bin_descriptions = [f"Bin {b['idx']} ('{b['label']}') range: {b['desc']}" for b in sorted_bins]
            return bin_descriptions + actual_issues
        return []
    
    def _validate_against_businesslogic_values(self, doc: etree._Element, row: pd.Series, template_str: str) -> List[str]:
        """
        Dynamically compare all placeholders from the XML template against actual Excel values.

        Args:
            doc: The parsed XML element.
            row: The corresponding Excel row.
            template_str: A TAK-type-specific template (e.g., for state, context).

        Returns:
            List of mismatch descriptions.
        """

        def extract_placeholders(template: str) -> List[str]:
            return sorted(set(re.findall(r"\{([^{}]+)\}", template)))

        def find_xpath_of_field(field: str) -> str:
            """
            Try to locate the path where a placeholder appears in the template.
            Assumes format: <tag ... attr="{FIELD}"> or <tag>{FIELD}</tag>
            """
            matches = re.findall(
                    rf"""<(?P<tag1>[a-zA-Z0-9_-]+)[^>]*?\{{{field}}}|  # match attributes
                        <(?P<tag2>[a-zA-Z0-9_-]+)>\s*\{{{field}}}\s*</[^>]+>  # match inner text
                    """, template_str, re.VERBOSE)
            if not matches:
                return None
            # Try to reconstruct a usable path (best effort)
            # E.g., match for 'good-after granularity="{LOCAL_PERSISTENCE_GOOD_AFTER_GRANULARITY}"'
            tag_match = matches[0]
            tag_name = tag_match[0] or tag_match[1]
            return f".//{tag_name}"

        def get_xml_value_dynamic(field: str) -> str:
            # First try known fields
            if field == "ID":
                return doc.get("id", "").strip()
            elif field == "TAK_NAME":
                return doc.get("name", "").strip()

            # Handle special field mappings dynamically
            if field in ValidatorConfig.SPECIAL_FIELD_MAP:
                tag, attr = ValidatorConfig.SPECIAL_FIELD_MAP[field]
                
                # Only add .// if tag doesn't already start with it
                xpath = tag if tag is None else (tag if tag.startswith(".//") else f".//{tag}")

                search_root = doc if xpath is None else doc.find(xpath)
                if search_root is not None:
                    return search_root.get(attr, "").strip()
                return ""

            # Fallback to generic template-based extraction
            path = find_xpath_of_field(field)
            if not path:
                return ""
            elements = doc.findall(path)
            for el in elements:
                for attr_key, attr_val in el.attrib.items():
                    if attr_key.lower().endswith(field.lower().split("_")[-1]):
                        return attr_val.strip()
                if el.text and el.text.strip():
                    return el.text.strip()
            return ""

        issues = []
        placeholders = extract_placeholders(template_str)

        for field in placeholders:
            if field not in row:
                continue

            expected = str(row.get(field, "")).strip()
            actual = get_xml_value_dynamic(field)

            if expected != actual:
                # Add issue + disclaimer due to code issue
                issues.append(f"{field} mismatch: XML shows='{actual}' | Excel says it should be='{expected}'. Note: This validation might not be accurate due to code issue. If the validation says current value is an empty str and Excel value match the XML value - Carry on")

        return issues
    
    def _validate_allowed_values_against_excel(self, doc: etree._Element, row: pd.Series) -> list[str]:
        """
        Checks that all values listed in <nominal-allowed-values> or <ordinal-allowed-values> exist
        in the corresponding Excel column for that TAK type.

        Args:
            doc (etree._Element): The parsed TAK XML.
            row (pd.Series): The matching Excel row.

        Returns:
            List[str]: A list of mismatch issues.
        """
        issues = []

        def extract_xml_values(tag: str, value_attr: str = "value") -> List[str]:
            return [el.get(value_attr).strip() for el in doc.findall(f".//{tag}") if el.get(value_attr)]

        def parse_excel_list(col: str) -> List[str]:
            raw_val = row.get(col, "")
            if pd.isna(raw_val):
                return []
            try:
                parsed = json.loads(raw_val) if isinstance(raw_val, str) else raw_val
                return [v.strip() for v in parsed if isinstance(v, str)]
            except Exception:
                return [v.strip() for v in raw_val.split(",")]  # fallback for comma-separated

        if doc.find(".//nominal-allowed-values") is not None:
            xml_vals = extract_xml_values("nominal-allowed-value")
            excel_vals = parse_excel_list("ALLOWED_VALUES_NOMINAL")
            missing = [v for v in xml_vals if v not in excel_vals]
            if missing:
                issues.append(f"XML nominal values not found in Excel ALLOWED_VALUES_NOMINAL: {missing}")

        if doc.find(".//ordinal-allowed-values") is not None:
            xml_vals = extract_xml_values("ordinal-allowed-value")
            excel_vals = parse_excel_list("STATE_LABELS")
            missing = [v for v in xml_vals if v not in excel_vals]
            if missing:
                issues.append(f"XML ordinal values not found in Excel STATE_LABELS: {missing}")

        return issues


if __name__ == "__main__":
    import sys

    try:
        with open("sample_tak.xml", "r", encoding="utf-8") as f:
            sample_tak = f.read()
    except Exception as e:
        sys.exit(f"Error reading sample TAK file: {e}")

    try:
        validator = TAKok(ValidatorConfig.SCHEMA_PATH, ValidatorConfig.EXCEL_PATH)
    except RuntimeError as e:
        sys.exit(f"Initialization error: {e}")

    valid, ind, messages = validator.validate(sample_tak)
    if valid:
        print("TAK file is valid!")
    else:
        print("TAK file is invalid:", ind + "; ".join(messages))