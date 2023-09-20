from ast import Dict
from typing import Type
import attrs
import cattrs
from cattrs.gen import make_dict_structure_fn
from taf.exceptions import RolesKeyDataConversionError

converter = cattrs.Converter()
converter.register_structure_hook_factory(
    attrs.has,
    lambda cl: make_dict_structure_fn(
        cl, converter, _cattrs_forbid_extra_keys=True, _cattrs_detailed_validation=False
    ),
)


def from_dict(data_dict: Dict, model_type: Type):
    try:
        return converter.structure(data_dict, model_type)
    except cattrs.errors.IterableValidationError as e:
        raise RolesKeyDataConversionError(e.exceptions)
    except ValueError as e:
        raise RolesKeyDataConversionError([str(e)])
