CER_PRODUCTION = {
    "name": "cer_production",
    "source_page_url": "https://www.cer-rec.gc.ca/en/data-analysis/energy-commodities/crude-oil-petroleum-products/statistics/estimated-production-canadian-crude-oil-equivalent.html",
    "file_extensions": (".xlsx", ".xls"),
    "sheet_name": "HIST - cubic meters per day",
    "raw_filename": "cer_estimated_production_details.xlsx",
    "output_filename": "western_canada_estimated_production.csv",
}

CER_PIPELINE_SOURCES = [
    {
        "name": "enbridge_mainline",
        "source_page_url": "https://open.canada.ca/data/en/dataset/dc343c43-a592-4a27-8ee7-c77df56afb34/resource/a3877960-65f2-47d0-9886-688ba1cabddc",
        "file_extensions": (".csv",),
        "raw_filename": "enbridge_throughput_details.csv",
        "flow_locations_filename": "enbridge_mainline_flow_location.csv",
        "capacity_filename": "enbrdige_mainline_capacity.csv"
    },
    {
        "name": "keystone",
        "source_page_url": "https://open.canada.ca/data/en/dataset/dc343c43-a592-4a27-8ee7-c77df56afb34/resource/b7597d90-0d9a-44d8-8d31-3434d693d6d9",
        "file_extensions": (".csv",),
        "raw_filename": "keystone_throughput_details.csv",
        "flow_locations_filename": "keystone_flow_location.csv",
        "capacity_filename": "keystone_capacity.csv"
    },
    {
        "name": "transmountain",
        "source_page_url": "https://open.canada.ca/data/en/dataset/dc343c43-a592-4a27-8ee7-c77df56afb34/resource/404fa9e0-73b1-4a8c-9f43-8045d7edb426",
        "file_extensions": (".csv",),
        "raw_filename": "transmountain_throughput_details.csv",
        "flow_locations_filename": "transmountain_flow_location.csv",
        "capacity_filename": "transmountain_capacity.csv"
    },
]

CER_RAIL_EXPORTS = {
    "name": "cer_rail",
    "source_page_url": "https://www.cer-rec.gc.ca/en/data-analysis/energy-commodities/crude-oil-petroleum-products/statistics/canadian-crude-oil-exports-rail-monthly-data.html",
    "file_extensions": (".xlsx", ".xls"),
    "sheet_name": "CrudeOilExportsByRail",
    "raw_filename": "cer_rail_exports_monthly_raw.xlsx",
    "output_filename": "monthyl_rail_exports.csv",
}
