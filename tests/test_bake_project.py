import os
import re
import pytest
import sh
import yaml
from cookiecutter.exceptions import FailedHookException
from binaryornot.check import is_binary

PATTERN = r"{{(\s?cookiecutter)[.](.*?)}}"
RE_OBJ = re.compile(PATTERN)


def _fixture_id(ctx):
    """Helper to get a user friendly test name from the parametrized context."""
    return "-".join(f"{key}:{value}" for key, value in ctx.items())


def build_files_list(root_dir):
    """Build a list containing absolute paths to the generated files."""
    return [
        os.path.join(dirpath, file_path)
        for dirpath, subdirs, files in os.walk(root_dir)
        for file_path in files
    ]


def check_paths(paths):
    """Method to check all paths have correct substitutions."""
    # Assert that no match is found in any of the files
    for path in paths:
        if is_binary(path):
            continue

        for line in open(path, "r"):
            match = RE_OBJ.search(line)
            assert match is None, f"cookiecutter variable not replaced in {path}"


@pytest.mark.parametrize("context_override", pytest.SUPPORTED_COMBINATIONS, ids=_fixture_id)
def test_bake_project(cookies, context, context_override):
    """Test that project is generated and fully rendered."""
    result = cookies.bake(extra_context={**context, **context_override})
    assert result.exit_code == 0
    assert result.exception is None
    assert result.project.basename == context["project_slug"]
    assert result.project.isdir()

    paths = build_files_list(str(result.project))
    assert paths
    check_paths(paths)


@pytest.mark.parametrize("stage, expected_test_script",
                         [("linting:flake8", ["make ${LINTING_PKG}"]),
                          ("linting:mypy", ["make ${LINTING_PKG}"]),
                          ("linting:bandit", ["make ${LINTING_PKG}"]),
                          ("test:3.6", ["make test"]),
                          ("test:3.7", ["make test"]),
                          ("test:3.8", ["make test"])])
def test_gitlab_invokes_linting_and_pytest(cookies, context, stage,
                                           expected_test_script):
    context.update({"ci_tool": "GitLab"})
    result = cookies.bake(extra_context=context)

    assert result.exit_code == 0
    assert result.exception is None
    assert result.project.basename == context["project_slug"]
    assert result.project.isdir()

    with open(f"{result.project}/.gitlab-ci.yml", "r") as gitlab_yml:
        try:
            gitlab_config = yaml.safe_load(gitlab_yml)
            assert gitlab_config[stage]["script"] == expected_test_script
        except yaml.YAMLError as e:
            pytest.fail(e)


@pytest.mark.parametrize("slug", ["project slug", "Project_Slug"])
def test_invalid_slug(cookies, context, slug):
    """Invalid slug should failed pre-generation hook."""
    context.update({"project_slug": slug})

    result = cookies.bake(extra_context=context)

    assert result.exit_code != 0
    assert isinstance(result.exception, FailedHookException)


@pytest.mark.parametrize("invalid_context", pytest.UNSUPPORTED_COMBINATIONS)
def test_error_if_incompatible(cookies, context, invalid_context):
    """It should not generate project an incompatible combination is selected.
    """
    context.update(invalid_context)
    result = cookies.bake(extra_context=context)

    assert result.exit_code != 0
    assert isinstance(result.exception, FailedHookException)


def linting_check(cookies, linting_type, context_override, call_params=None):
    """Generated project should pass flake8."""
    result = cookies.bake(extra_context=context_override)
    if call_params is None:
        call_params = []
    call_params.append(result.context['project_slug'])
    try:
        current_dir = str(sh.pwd("-P")).replace("\n", "")
        sh.cd(str(result.project))
        sh.pip("install", "-r", os.path.join("requirements", "base.txt"))
        getattr(sh, linting_type)(*call_params)
        sh.cd(current_dir)
        sh.rm("-r", str(result.project))
    except sh.ErrorReturnCode as e:
        pytest.fail(e.stdout.decode())


@pytest.mark.parametrize("context_override", pytest.SUPPORTED_COMBINATIONS, ids=_fixture_id)
def test_flake8_passes(cookies, context_override):
    """Generated project should pass flake8."""
    linting_check(cookies, "flake8", context_override)


@pytest.mark.parametrize("context_override", pytest.SUPPORTED_COMBINATIONS, ids=_fixture_id)
def test_mypy_passes(cookies, context_override):
    """Generated project should pass mypy."""
    linting_check(cookies, "mypy", context_override)


@pytest.mark.parametrize("context_override", pytest.SUPPORTED_COMBINATIONS, ids=_fixture_id)
def test_bandit_passes(cookies, context_override):
    """Generated project should pass bandit."""
    linting_check(cookies, "bandit", context_override, call_params=['-r'])


@pytest.mark.parametrize("context_override", pytest.SUPPORTED_COMBINATIONS, ids=_fixture_id)
def test_pytest_passes(cookies, context_override):
    """Generated project should pass black."""
    result = cookies.bake(extra_context=context_override)

    try:
        current_dir = str(sh.pwd("-P")).replace("\n", "")
        sh.cd(str(result.project))
        sh.make("test")
        sh.cd(current_dir)
        sh.rm("-r", str(result.project))
    except sh.ErrorReturnCode as e:
        pytest.fail(e.stdout.decode())



