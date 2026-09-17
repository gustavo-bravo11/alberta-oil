"""Tests for the one-time Trans Mountain GeoJSON extraction."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pipeline.extract import tm_geo_extract


class TmGeoExtractTests(unittest.TestCase):
    def test_main_writes_configured_layers_and_records_retrieval(self) -> None:
        responses = [
            SimpleNamespace(url="https://example.test/facilities", content=b"facilities"),
            SimpleNamespace(url="https://example.test/existing", content=b"existing"),
        ]
        with (
            patch.object(tm_geo_extract, "safe_request_get", side_effect=responses) as request,
            patch.object(tm_geo_extract, "download_file", return_value=True) as download,
            patch.object(tm_geo_extract, "record_retrieval") as record,
        ):
            tm_geo_extract.main(run_id="tm-test", run_type="forced")

        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[0].args[0], tm_geo_extract.layer_query_url(1))
        self.assertEqual(request.call_args_list[0].kwargs["params"], tm_geo_extract.NRCAN_TM_QUERY_PARAMS)
        self.assertEqual(
            [call.kwargs["output_name"] for call in download.call_args_list],
            ["transmountain_facilities_raw.geojson", "transmountain_existing_raw.geojson"],
        )
        self.assertTrue(
            all(
                call.kwargs["output_dir"] == tm_geo_extract.RAW_TM_GEOSPATIAL_BUCKET
                for call in download.call_args_list
            )
        )
        self.assertEqual(
            [call.kwargs["source_name"] for call in record.call_args_list],
            ["transmountain_facilities", "transmountain_existing"],
        )
        self.assertTrue(all(call.kwargs["run_id"] == "tm-test" for call in record.call_args_list))
