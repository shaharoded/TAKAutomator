class ValidatorConfig:
    SCHEMA_PATH = 'schema.xsd'
    EXCEL_PATH = 'taks.xlsx'
    REQUIRED_SHEETS = ["raw_concepts", "events", "states", "contexts", "trends"] # Sheets for validation and generation

    # Maps Excel field -> (XPath tag, attribute name)
    SPECIAL_FIELD_MAP = {
        # Numeric Raw Concept
        "ALLOWED_VALUES_MIN": ("numeric-allowed-values", "min-value"),
        "ALLOWED_VALUES_MAX": ("numeric-allowed-values", "max-value"),
        "ALLOWED_VALUES_UNITS": ("numeric-allowed-values", "units"),
        "ALLOWED_VALUES_SCALE": ("numeric-allowed-values", "scale"),
        "OUTPUT_TYPE": ("numeric-allowed-values", "output-type"),

        # Trends
        "SIGNIFICANT_VARIATION": (None, "significant-variation"),  # root-level
        "TIME_STEADY_VALUE": ("time-steady", "value"),
        "TIME_STEADY_UNIT": ("time-steady", "granularity"),

        # Contexts (from/in clipper/inducer blocks)
        "FROM_BOUND": (".//from", "boundary-point"),
        "FROM_SHIFT": (".//from/time-gap", "value"),
        "UNTIL_GRANULARITY": (".//until/time-gap", "granularity"),
        "CLIPPER_GRANULARITY": (".//clipper-entity/from/time-gap", "granularity"),
    }
