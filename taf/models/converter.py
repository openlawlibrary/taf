import attrs
import cattrs
from typing import ForwardRef
from cattrs.gen import make_dict_structure_fn
from taf.models.types import DelegatedRole

converter = cattrs.Converter()
converter.register_structure_hook_factory(
    attrs.has,
    lambda cl: make_dict_structure_fn(
        cl, converter, _cattrs_forbid_extra_keys=True, _cattrs_detailed_validation=False
    ),
)


def from_dict(data_dict, model_type):
    return converter.structure(data_dict, model_type)
