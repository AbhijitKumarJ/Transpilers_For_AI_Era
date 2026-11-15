import subprocess
import sys
from pathlib import Path

from psc.cli import main


def test_multidepth_and_distinct_namespaces_compilation(tmp_path: Path) -> None:
    """
    Verifies that projects with primary namespaces, multi-depth sub-namespaces across
    arbitrary folder depths, and distinct namespaces compile cleanly to dist/ without
    Python module/package file shadowing collisions, and execute correctly.
    """
    proj_dir = tmp_path / "MultiDepthApp"
    proj_dir.mkdir(parents=True, exist_ok=True)

    # 1. Project file
    psproj_file = proj_dir / "MultiDepthApp.psproj"
    psproj_file.write_text(
        """<Project Sdk="PythonSharp.Sdk/0.1.0">
  <PropertyGroup>
    <AssemblyName>MultiDepthApp</AssemblyName>
    <TargetFramework>py3.11</TargetFramework>
  </PropertyGroup>
</Project>
""",
        encoding="utf-8",
    )

    # 2. Root file with primary namespace Company.App
    (proj_dir / "ProjMain.ps").write_text(
        """namespace Company.App;

using PythonSharp.Core;
using Company.App.Services;
using Company.App.Services.Payments;
using Company.App.Services.Payments.Gateways.Stripe;
using ThirdParty.Diagnostics.Telemetry;

public class ProjMain
{
    public static void Main(string[] args)
    {
        Console.WriteLine("MultiDepthApp - Root Start");
        var svc = new OrderService();
        Console.WriteLine(svc.ProcessOrder("ORD-101"));

        var gw = new StripeGateway();
        Console.WriteLine(gw.Charge(99.95));

        var logger = new TelemetrySink();
        logger.Emit("All layers verified!");
    }
}
""",
        encoding="utf-8",
    )

    # 3. Child namespace at depth 1: Company.App.Services (in Services/)
    services_dir = proj_dir / "Services"
    services_dir.mkdir(parents=True, exist_ok=True)
    (services_dir / "OrderService.ps").write_text(
        """namespace Company.App.Services;

using Company.App.Services.Payments;

public class OrderService
{
    public string ProcessOrder(string id)
    {
        var proc = new PaymentProcessor();
        return $"Order {id} processed via {proc.GetProcessorName()}";
    }
}
""",
        encoding="utf-8",
    )

    # 4. Child namespace at depth 2: Company.App.Services.Payments (in Services/Payments/)
    payments_dir = services_dir / "Payments"
    payments_dir.mkdir(parents=True, exist_ok=True)
    (payments_dir / "PaymentProcessor.ps").write_text(
        """namespace Company.App.Services.Payments;

public class PaymentProcessor
{
    public string GetProcessorName()
    {
        return "StandardProcessor";
    }
}
""",
        encoding="utf-8",
    )

    # 5. Child namespace at depth 3 (leaf): Company.App.Services.Payments.Gateways.Stripe
    # (in Services/Payments/Gateways/)
    gateways_dir = payments_dir / "Gateways"
    gateways_dir.mkdir(parents=True, exist_ok=True)
    (gateways_dir / "StripeGateway.ps").write_text(
        """namespace Company.App.Services.Payments.Gateways.Stripe;

public class StripeGateway
{
    public string Charge(double amount)
    {
        return $"Charged ${amount} via Stripe API";
    }
}
""",
        encoding="utf-8",
    )

    # 6. Sibling distinct namespace at depth 2: ThirdParty.Diagnostics.Telemetry (in Diagnostics/Sinks/)
    diag_dir = proj_dir / "Diagnostics" / "Sinks"
    diag_dir.mkdir(parents=True, exist_ok=True)
    (diag_dir / "TelemetrySink.ps").write_text(
        """namespace ThirdParty.Diagnostics.Telemetry;

using PythonSharp.Core;

public class TelemetrySink
{
    public void Emit(string msg)
    {
        Console.WriteLine($"[TELEMETRY] {msg}");
    }
}
""",
        encoding="utf-8",
    )

    # Build the project
    ret = main(["build", str(psproj_file), "--no-pyc"])
    assert ret == 0

    dist_dir = proj_dir / "dist"
    assert dist_dir.is_dir()

    # Verify directory structure in dist/
    # Company.App has child Company.App.Services, so company/app/__init__.py
    assert (dist_dir / "company" / "app" / "__init__.py").is_file()
    # No shadowing company/app.py file!
    assert not (dist_dir / "company" / "app.py").exists()

    # Company.App.Services has child Payments, so company/app/services/__init__.py
    assert (dist_dir / "company" / "app" / "services" / "__init__.py").is_file()
    assert not (dist_dir / "company" / "app" / "services.py").exists()

    # Company.App.Services.Payments has child Gateways.Stripe, so payments/__init__.py
    assert (dist_dir / "company" / "app" / "services" / "payments" / "__init__.py").is_file()

    # Leaf namespace Company.App.Services.Payments.Gateways.Stripe -> stripe.py
    assert (dist_dir / "company" / "app" / "services" / "payments" / "gateways" / "stripe.py").is_file()

    # Leaf namespace ThirdParty.Diagnostics.Telemetry -> third_party/diagnostics/telemetry.py
    assert (dist_dir / "third_party" / "diagnostics" / "telemetry.py").is_file()

    # Execute run_main harness
    run_main_script = f"""
import sys
from pathlib import Path

sys.path.insert(0, r"{dist_dir}")

from company.app import ProjMain

ProjMain.main([])
"""
    result = subprocess.run(
        [sys.executable, "-c", run_main_script],
        capture_output=True,
        text=True,
        check=True,
    )

    assert "MultiDepthApp - Root Start" in result.stdout
    assert "Order ORD-101 processed via StandardProcessor" in result.stdout
    assert "Charged $99.95 via Stripe API" in result.stdout
    assert "[TELEMETRY] All layers verified!" in result.stdout
