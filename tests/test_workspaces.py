import importlib.machinery
import pytest
import subprocess
import glob
import importlib
import inspect
import os
from typing import List, Tuple, Type, Optional
from types import ModuleType
from buildzr.models import *
from tests.abstract_builder import AbstractBuilder

@pytest.fixture
def json_workspace_paths() -> List[str]:
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

@pytest.fixture
def builders() -> List[AbstractBuilder]:
    """Gets the instances of classes that implements `AbstractBuilder`."""

    samples = glob.glob("tests/samples/[a-zA-Z0-9]*.py")

    sample_packages : List[Tuple[str, str]] = []

    for sample in samples:
        parts   = sample.rpartition('.')[0].rpartition('/')

        module  = f".{parts[2]}"
        package = f".{parts[0].replace('/', '.')}"

        sample_packages.append((module, package))

    modules = [importlib.import_module(sample, package=package) \
               for (sample, package) in sample_packages]

    abstract_builder_mod = importlib.import_module('.abstract_builder', package='.tests')
    abstract_builder_cls = [\
        cls for name, cls in inspect.getmembers(abstract_builder_mod, inspect.isclass)\
        if name == 'AbstractBuilder'
    ][0]

    builds: List[AbstractBuilder] = []

    mod: ModuleType
    for mod in modules:
        module_classes = inspect.getmembers(mod, inspect.isclass)

        # Exclude imported class. Alsoname,  make sure the class inherits the abstract
        # base class. Luckily, type hinting is retained on `cls` as well!
        classes: List[Type[Any]] = [\
            cls for _name, cls in module_classes\
                if issubclass(cls, abstract_builder_cls) and\
                   cls != abstract_builder_cls
            ]

        for cls in classes:
            builds.append(cls())

    return builds

def test_json_encode() -> Optional[None]:

    from .samples import simple
    from buildzr.encoders import JsonEncoder
    import json

    simple_workspace = simple.Simple().build()
    json.dumps(simple_workspace, cls=JsonEncoder)

def test_pass_structurizr_validation(builders: List[AbstractBuilder]) -> Optional[None]:
    """Uses structurizr CLI to validate the JSON document."""

    completed_processes : List[subprocess.CompletedProcess] = []

    for builder in builders:
        json_file_name = builder.__class__.__module__

        json_file_path = os.path.join('tests', 'samples', f"{json_file_name}.json")

        builder.writes_json_to(json_file_path)

        completed_process = subprocess.run([
            'structurizr.sh',
            'validate',
            '-workspace',
            json_file_path
        ])
        completed_processes.append(completed_process)

    assert all([output.returncode == 0 for output in completed_processes])