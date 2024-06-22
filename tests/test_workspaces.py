import pytest
import subprocess
import glob
from typing import List
from deepdiff import DeepDiff
from buildzr.models import *
from buildzr.encoders import JsonEncoder

@pytest.fixture
def json_workspace_paths():
    """Use structurizr CLI to generate the json file for each dsl test files."""

    export_outputs : List[subprocess.CompletedProcess] = []
    for dsl_file_path in glob.glob("tests/dsl/*.dsl"):
        completed_process = subprocess.run([
            'structurizr.sh',
            'export',
            '-w', dsl_file_path,
            '-f', 'json',
        ])
        export_outputs.append(completed_process)

    assert all([output.returncode == 0 for output in export_outputs])

    return glob.glob("tests/dsl/*.json")

def test_json_encode():

    from .samples import simple
    from buildzr.encoders import JsonEncoder
    import json

    simple_workspace = simple.Simple().build()
    json.dumps(simple_workspace, cls=JsonEncoder)

def test_pass_structurizr_validation(json_workspace_paths: List[str]):
    """Uses structurizr CLI to validate the JSON document."""

    import importlib
    import glob

    samples = glob.glob("tests/samples/[a-zA-Z0-9]*.py")

    sample_packages : List[(str, str)] = []

    for sample in samples:
        parts   = samples[0].rpartition('.')[0].rpartition('/')

        module  = f".{parts[2]}"
        package = f".{parts[0].replace('/', '.')}"

        sample_packages.append((module, package))

    modules = [importlib.import_module(sample, package=package) \
               for (sample, package) in sample_packages]

    completed_processes : List[subprocess.CompletedProcess] = []
    for path in json_workspace_paths:
        completed_process = subprocess.run([
            'structurizr.sh',
            'validate',
            '-workspace',
            path
        ])
        completed_processes.append(completed_process)

    assert all([output.returncode == 0 for output in completed_processes])