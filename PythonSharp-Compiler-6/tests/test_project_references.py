import subprocess
import sys
from pathlib import Path

import pytest

from psc.cli import main
from psc.project import load_project


def _create_starter_project(target_dir: Path, name: str) -> Path:
    proj_dir = target_dir / name
    proj_dir.mkdir(parents=True, exist_ok=True)
    psproj = proj_dir / f"{name}.psproj"
    psproj.write_text(
        f"""<Project Sdk="PythonSharp.Sdk/0.1.0">
  <PropertyGroup>
    <AssemblyName>{name}</AssemblyName>
    <TargetFramework>py3.11</TargetFramework>
  </PropertyGroup>
</Project>
""",
        encoding="utf-8",
    )
    return psproj


def test_cli_add_reference_and_add_reference_alias(tmp_path: Path) -> None:
    workspace = tmp_path / "Workspace"
    workspace.mkdir()

    proj_a_file = _create_starter_project(workspace, "ProjA")
    proj_b_file = _create_starter_project(workspace, "ProjB")
    proj_c_file = _create_starter_project(workspace, "ProjC")

    # Test `psc add reference`
    ret = main(["add", "reference", str(proj_b_file), "-p", str(proj_a_file)])
    assert ret == 0

    cfg_a = load_project(proj_a_file)
    assert len(cfg_a.project_references) == 1
    assert cfg_a.project_references[0] == proj_b_file.resolve()

    # Test `psc add-reference` alias
    ret2 = main(["add-reference", str(proj_c_file), "-p", str(proj_a_file)])
    assert ret2 == 0

    cfg_a2 = load_project(proj_a_file)
    assert len(cfg_a2.project_references) == 2
    assert proj_b_file.resolve() in cfg_a2.project_references
    assert proj_c_file.resolve() in cfg_a2.project_references


def test_circular_project_reference_detection(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    workspace = tmp_path / "CycleWorkspace"
    workspace.mkdir()

    proj_a_file = _create_starter_project(workspace, "ProjA")
    proj_b_file = _create_starter_project(workspace, "ProjB")

    # Add source files
    (workspace / "ProjA" / "A.ps").write_text("namespace ProjA; public class A {}", encoding="utf-8")
    (workspace / "ProjB" / "B.ps").write_text("namespace ProjB; public class B {}", encoding="utf-8")

    # Create cycle: A -> B and B -> A
    assert main(["add", "reference", str(proj_b_file), "-p", str(proj_a_file)]) == 0
    assert main(["add", "reference", str(proj_a_file), "-p", str(proj_b_file)]) == 0

    # Building ProjA should detect the cycle
    ret = main(["build", str(proj_a_file)])
    assert ret == 1
    err = capsys.readouterr().err
    assert "Circular project reference detected" in err


def test_five_layer_enterprise_architecture(tmp_path: Path) -> None:
    """
    Sets up a full 5-layer enterprise project dependency chain:
      Layer 1: Enterprise.Core
      Layer 2: Enterprise.Domain (references Core)
      Layer 3: Enterprise.Data (references Domain)
      Layer 4: Enterprise.Services (references Data)
      Layer 5: Enterprise.App (references Services)
    Verifies:
      1. Independent compilation of sub-layer (Domain or Data).
      2. Full top-down compilation of App builds all transitive dependencies in topological order.
      3. All dependency artifacts are copied into App's dist/ directory.
      4. App runs and interacts with types across all 5 layers.
    """
    workspace = tmp_path / "Enterprise5Layer"
    workspace.mkdir()

    # Layer 1: Core
    core_proj = _create_starter_project(workspace, "Core")
    (workspace / "Core" / "Entity.ps").write_text(
        """namespace Enterprise.Core;

public class BaseEntity
{
    public int Id { get; set; }
    public string CreatedAt { get; set; }

    public BaseEntity(int id, string createdAt)
    {
        this.Id = id;
        this.CreatedAt = createdAt;
    }
}

public class IdGenerator
{
    public static int NextId(int current)
    {
        return current + 1;
    }
}
""",
        encoding="utf-8",
    )

    # Layer 2: Domain (references Core)
    domain_proj = _create_starter_project(workspace, "Domain")
    assert main(["add", "reference", str(core_proj), "-p", str(domain_proj)]) == 0
    (workspace / "Domain" / "User.ps").write_text(
        """namespace Enterprise.Domain;

using Enterprise.Core;

public class User : BaseEntity
{
    public string Username { get; set; }
    public string Email { get; set; }

    public User(int id, string username, string email) : base(id, "2026-01-01")
    {
        this.Username = username;
        this.Email = email;
    }

    public string Describe()
    {
        return $"User #{this.Id}: {this.Username} <{this.Email}>";
    }
}
""",
        encoding="utf-8",
    )

    # Layer 3: Data (references Domain)
    data_proj = _create_starter_project(workspace, "Data")
    assert main(["add", "reference", str(domain_proj), "-p", str(data_proj)]) == 0
    (workspace / "Data" / "UserRepository.ps").write_text(
        """namespace Enterprise.Data;

using Enterprise.Core;
using Enterprise.Domain;

public class UserRepository
{
    public User FindById(int id)
    {
        return new User(id, "ada_lovelace", "ada@computing.org");
    }
}
""",
        encoding="utf-8",
    )

    # Layer 4: Services (references Data)
    services_proj = _create_starter_project(workspace, "Services")
    assert main(["add", "reference", str(data_proj), "-p", str(services_proj)]) == 0
    (workspace / "Services" / "UserService.ps").write_text(
        """namespace Enterprise.Services;

using Enterprise.Domain;
using Enterprise.Data;

public class UserService
{
    public string GetUserDetails(int id)
    {
        var repo = new UserRepository();
        var user = repo.FindById(id);
        return $"[SERVICE RESPONSE] {user.Describe()}";
    }
}
""",
        encoding="utf-8",
    )

    # Layer 5: App (references Services)
    app_proj = _create_starter_project(workspace, "App")
    assert main(["add", "reference", str(services_proj), "-p", str(app_proj)]) == 0
    (workspace / "App" / "ProjMain.ps").write_text(
        """namespace Enterprise.App;

using PythonSharp.Core;
using Enterprise.Core;
using Enterprise.Domain;
using Enterprise.Data;
using Enterprise.Services;

public class ProjMain
{
    public static void Main(string[] args)
    {
        Console.WriteLine("=== Enterprise 5-Layer App Starting ===");
        var id = IdGenerator.NextId(99);
        var svc = new UserService();
        var result = svc.GetUserDetails(id);
        Console.WriteLine(result);
        Console.WriteLine("=== Enterprise 5-Layer App Completed ===");
    }
}
""",
        encoding="utf-8",
    )

    # --- Verification 1: Build Layer 2 (Domain) independently ---
    ret_domain = main(["build", str(domain_proj), "--no-pyc"])
    assert ret_domain == 0

    domain_dist = workspace / "Domain" / "dist"
    assert (domain_dist / "enterprise" / "domain.py").is_file()
    # Check that Core was built and copied into Domain's dist/
    assert (domain_dist / "enterprise" / "core.py").is_file()

    # --- Verification 2: Build Layer 5 (App) ---
    # This should trigger topological compilation of Core -> Domain -> Data -> Services -> App
    ret_app = main(["build", str(app_proj), "--no-pyc"])
    assert ret_app == 0

    app_dist = workspace / "App" / "dist"
    assert app_dist.is_dir()

    # All 5 layers must be present in App's dist/
    assert (app_dist / "enterprise" / "core.py").is_file()
    assert (app_dist / "enterprise" / "domain.py").is_file()
    assert (app_dist / "enterprise" / "data.py").is_file()
    assert (app_dist / "enterprise" / "services.py").is_file()
    assert (app_dist / "enterprise" / "app.py").is_file()

    # --- Verification 3: Execute App's runner harness ---
    run_main_script = f"""
import sys
from pathlib import Path

sys.path.insert(0, r"{app_dist}")

from enterprise.app import ProjMain

ProjMain.main([])
"""
    result = subprocess.run(
        [sys.executable, "-c", run_main_script],
        capture_output=True,
        text=True,
        check=True,
    )

    assert "=== Enterprise 5-Layer App Starting ===" in result.stdout
    assert "[SERVICE RESPONSE] User #100: ada_lovelace <ada@computing.org>" in result.stdout
    assert "=== Enterprise 5-Layer App Completed ===" in result.stdout


def test_cross_project_qualified_type_access_and_using_validation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    workspace = tmp_path / "QualifiedTest"
    workspace.mkdir()

    # Create Lib project with TestUtil
    lib_proj = _create_starter_project(workspace, "MyLib")
    (workspace / "MyLib" / "TestUtil.ps").write_text(
        """namespace MyLib;
using PythonSharp.Core;
public class TestUtil {
    public static void Log(string msg) { Console.WriteLine($"[MyLib] {msg}"); }
}
""",
        encoding="utf-8",
    )

    # Create Main project referencing Lib
    main_proj = _create_starter_project(workspace, "MyMain")
    main_proj.write_text(
        f"""<Project Sdk="PythonSharp.Sdk/0.1.0">
  <PropertyGroup>
    <AssemblyName>MyMain</AssemblyName>
    <TargetFramework>py3.11</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="{lib_proj}" />
  </ItemGroup>
</Project>
""",
        encoding="utf-8",
    )

    # 1. Test typo in using and qualified call -> compiler diagnostic with hint
    (workspace / "MyMain" / "ProjMain.ps").write_text(
        """namespace MyMain;
using PythonSharp.Core;
using MyLyb; // typo

public class ProjMain {
    public static void Main(string[] args) {
        MyLyb.TestUtil.Log("hi");
    }
}
""",
        encoding="utf-8",
    )

    ret_err = main(["build", str(main_proj), "--no-pyc"])
    assert ret_err == 1
    captured = capsys.readouterr()
    assert "The type or namespace name 'MyLyb' could not be found (did you mean 'MyLib' ?)" in captured.err

    # 2. Fix using and qualify MyLib.TestUtil.Log alongside local MyMain.TestUtil
    (workspace / "MyMain" / "TestUtil.ps").write_text(
        """namespace MyMain;
using PythonSharp.Core;
public class TestUtil {
    public static void Log(string msg) { Console.WriteLine($"[MyMain] {msg}"); }
}
""",
        encoding="utf-8",
    )
    (workspace / "MyMain" / "ProjMain.ps").write_text(
        """namespace MyMain;
using PythonSharp.Core;
using MyLib;

public class ProjMain {
    public static void Main(string[] args) {
        TestUtil.Log("Calling local");
        MyLib.TestUtil.Log("Calling library");
    }
}
""",
        encoding="utf-8",
    )

    ret_ok = main(["build", str(main_proj), "--no-pyc"])
    assert ret_ok == 0

    main_dist = workspace / "MyMain" / "dist"
    run_script = f"""
import sys
sys.path.insert(0, r"{main_dist}")
from my_main import ProjMain
ProjMain.main([])
"""
    result = subprocess.run([sys.executable, "-c", run_script], capture_output=True, text=True, check=True)
    assert "[MyMain] Calling local" in result.stdout
    assert "[MyLib] Calling library" in result.stdout
