from typing import Iterator


# TODO make this more intuitive
class RolesIterator:
    def __init__(self, roles):
        self.roles = roles

    def __iter__(self) -> Iterator:
        # Define the order of roles
        if hasattr(self.roles, "root"):
            roles = [
                self.roles.root,
                self.roles.targets,
                self.roles.snapshot,
                self.roles.timestamp,
            ]
        else:
            roles = [self.roles]

        # Iterate over roles and their delegations
        for role in roles:
            yield role

            # Check if the role has delegations
            if hasattr(role, "delegations"):
                for delegation in role.delegations.values():
                    yield delegation
