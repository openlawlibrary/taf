from typing import Iterator


class RolesIterator:
    def __init__(self, main_roles):
        self.main_roles = main_roles

    def __iter__(self) -> Iterator:
        # Define the order of roles
        roles = [
            self.main_roles.root,
            self.main_roles.targets,
            self.main_roles.snapshot,
            self.main_roles.timestamp,
        ]

        # Iterate over roles and their delegations
        for role in roles:
            yield role

            # Check if the role has delegations
            if hasattr(role, "delegations"):
                for delegation in role.delegations.values():
                    yield delegation
