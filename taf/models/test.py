import json
from pathlib import Path
from taf.models.converter import from_dict

from taf.models.types import RolesKeysData


json_data = json.loads(
    Path("D:\\oll\\library\\oll-test-repos\\keys-description.json").read_text()
)
data = from_dict(json_data, RolesKeysData)
print(data)
