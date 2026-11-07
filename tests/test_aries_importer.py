import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from import_aries_revision_pairs import map_record  # noqa: E402


@pytest.mark.parametrize("record", [None, [], ["not", "an", "object"], "text", 42, True])
def test_importer_rejects_non_object_json_records(record):
    with pytest.raises(ValueError, match="record must be a JSON object"):
        map_record(record)
