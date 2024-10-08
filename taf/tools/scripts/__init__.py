import click

from pathlib import Path
from taf.log import taf_logger

import ast


def extract_global_variables(filename):
    """
    Utility function to extract global variables from a Python file.
    This is necessary because we want to execute the Python file in a separate process, and we need to pass the global variables to it.
    TAF currently uses this when executing lifecycle handler scripts from an executable built from pyinstaller, which uses a frozen sys module.
    """
    with open(filename, "r") as f:
        tree = ast.parse(f.read(), filename=filename)

    global_vars = {}

    for node in ast.walk(tree):
        try:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        # We only extract simple variable assignments, not function definitions or imports
                        if isinstance(node.value, (ast.Constant, ast.List, ast.Dict, ast.Tuple, ast.Constant)):
                            # Convert the AST expression to Python objects
                            global_vars[target.id] = ast.literal_eval(node.value)
        except Exception as e:
            taf_logger.debug(f"Error extracting global variables from {filename}: {e}")
            pass

    global_vars["__file__"] = filename

    return global_vars


def execute_command():
    @click.command(help="Executes an arbitrary python script")
    @click.argument("script_path")
    def execute(script_path):
        script_path = Path(script_path).resolve()
        global_scopes = extract_global_variables(script_path)
        with open(script_path, "r") as f:
            exec(f.read(), global_scopes)  # nosec: B102
    return execute


def attach_to_group(group):
    group.add_command(execute_command(), name='execute')
