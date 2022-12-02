from attrs import define, field


@define
class Info:
    namespace: str = field(default="")
    name: str = field(default="")
