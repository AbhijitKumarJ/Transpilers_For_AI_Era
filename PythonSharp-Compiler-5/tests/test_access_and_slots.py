from __future__ import annotations

from psc.diagnostics import DiagnosticEngine
from psc.frontend import Parser
from psc.frontend.ast_nodes import IndexerDecl, PropertyDecl
from psc.semantics import (
    AccessChecker,
    GlobalSymbolTable,
    SlotAndHierarchyAnalyzer,
    SymbolCollector,
)

STDLIB_STUB = """
namespace PythonSharp.Core;

[MapsTo("contextlib.AbstractContextManager")]
public interface IDisposable
{
    [MapsTo("dispose")]
    void Dispose();
}

[MapsTo("contextlib.AbstractAsyncContextManager")]
public interface IAsyncDisposable
{
    [MapsTo("dispose_async")]
    void DisposeAsync();
}

[MapsTo("dict")]
[RuntimeType("dict")]
public primitive class Dict<TKey, TValue>
{
    [InlineTemplate("{}")]
    public extern Dict();
}
"""


def test_deduplicated_slots_nominal_ps_types_and_disposable_context_manager() -> None:
    """
    Verifies Pass 2A `SlotAndHierarchyAnalyzer`:
      1. Base class `BaseEntity` gets `own_slots = ["_id", "_created_by"]`.
      2. Subclass `Account` inherits from `BaseEntity` and implements `IAuditable` + `IDisposable`:
         - `own_slots` excludes `_id` and `_created_by` (preventing CPython slot collision!),
           contains `_balance` and `_audit_tag`, and excludes computed property `IsOverdrawn`.
         - `ps_types_tuple` includes `Account`, `BaseEntity`, `IAuditable`, and `IDisposable`.
         - `generates_context_manager` is set to `True`.
      3. Record `OrderDto` lowers to `SlottedDataclass(is_frozen_dataclass=True)`.
      4. Primitive `Dict` lowers to `ErasedPrimitive`.
    """
    source = """
    namespace Commerce.Domain;

    using PythonSharp.Core;

    public interface IAuditable
    {
        string AuditTag { get; }
    }

    public record OrderDto(int Id, decimal Amount);

    public class BaseEntity
    {
        private readonly string _id;
        public string CreatedBy { get; protected set; }

        public BaseEntity(string id, string createdBy)
        {
            _id = id;
            CreatedBy = createdBy;
        }
    }

    public class Account : BaseEntity, IAuditable, IDisposable
    {
        private readonly string _id; // Redeclared shadow field must be deduplicated!
        public decimal Balance { get; private set; } = 0.0m;
        public string AuditTag { get; private set; }

        // Expression-bodied computed property: must NOT allocate a slot!
        public bool IsOverdrawn => Balance < 0.0m;

        public Account(string id, string createdBy, string tag) : base(id, createdBy)
        {
            AuditTag = tag;
        }

        public void Dispose() { }
    }
    """
    diag = DiagnosticEngine()
    unit_std = Parser.from_source(
        STDLIB_STUB, file_id=0, ps_filename="PythonSharp.Core.d.ps", diagnostics=diag
    ).parse_compilation_unit()
    unit_dom = Parser.from_source(
        source, file_id=1, ps_filename="Domain/Account.ps", diagnostics=diag
    ).parse_compilation_unit()

    symtab = GlobalSymbolTable(default_assembly_name="CommerceApp")
    SymbolCollector(symtab, diag).collect_all([unit_std, unit_dom])
    SlotAndHierarchyAnalyzer(symtab, diag).analyze_all([unit_std, unit_dom])

    assert not diag.has_errors(), diag.format_all()

    # 1. Primitive Dict is erased
    dict_sym = symtab.types_by_qname["PythonSharp.Core.Dict"]
    assert dict_sym.ast_node.emission_strategy.kind == "ErasedPrimitive"
    assert dict_sym.ast_node.emission_strategy.py_runtime_type == "dict"

    # 2. Record OrderDto is a frozen slotted dataclass
    order_sym = symtab.types_by_qname["Commerce.Domain.OrderDto"]
    assert order_sym.ast_node.emission_strategy.kind == "SlottedDataclass"
    assert order_sym.ast_node.emission_strategy.is_frozen_dataclass is True

    # 3. BaseEntity slots
    base_sym = symtab.types_by_qname["Commerce.Domain.BaseEntity"]
    base_strat = base_sym.ast_node.emission_strategy
    assert base_strat.kind == "SlottedClass"
    assert base_strat.own_slots == ["_id", "_created_by"]
    assert base_strat.generates_context_manager is False

    # 4. Subclass Account deduplicated slots, __ps_types__, and IDisposable context manager
    acc_sym = symtab.types_by_qname["Commerce.Domain.Account"]
    acc_strat = acc_sym.ast_node.emission_strategy
    assert acc_strat.kind == "SlottedClass"
    assert acc_strat.own_slots == ["_balance", "_audit_tag"]
    assert "_id" not in acc_strat.own_slots
    assert "_is_overdrawn" not in acc_strat.own_slots
    assert acc_strat.ps_types_tuple == [
        "Commerce.Domain.Account",
        "Commerce.Domain.BaseEntity",
        "Commerce.Domain.IAuditable",
        "PythonSharp.Core.IDisposable",
    ]
    assert acc_strat.generates_context_manager is True


def test_ps001_private_and_protected_member_enforcement() -> None:
    """
    Verifies Rule PS001:
      - `SavingsAccount` (subclass of `Account`) CAN write `CreatedBy` (`protected set`),
        CANNOT read `_secretPin` (`private`), and CANNOT write `Balance` (`private set`).
      - `ExternalCheckout` (unrelated class) CANNOT write `Balance` (`private set`)
        and CANNOT write `CreatedBy` (`protected set`), but CAN read `Balance` (`public`).
    """
    source = """
    namespace Commerce.Domain;

    public class Account
    {
        private string _secretPin = "1234";
        public decimal Balance { get; private set; } = 0.0m;
        public string CreatedBy { get; protected set; } = "System";

        public void Deposit(decimal amount)
        {
            // Legal inside declaring class:
            Balance = Balance + amount;
            _secretPin = "9999";
        }
    }

    public class SavingsAccount : Account
    {
        public void Upgrade(string officer)
        {
            // Legal in subclass (`protected set`):
            CreatedBy = officer;

            // ILLEGAL in subclass (`private set` on Balance):
            Balance = 100.0m;

            // ILLEGAL in subclass (`private` field `_secretPin`):
            var pin = _secretPin;
        }
    }

    public class ExternalCheckout
    {
        public void Process(Account acc)
        {
            // Legal public read:
            var current = acc.Balance;

            // ILLEGAL outside declaring class (`private set`):
            acc.Balance = 500.0m;

            // ILLEGAL outside hierarchy (`protected set`):
            acc.CreatedBy = "Hacker";
        }
    }
    """
    diag = DiagnosticEngine()
    unit = Parser.from_source(source, ps_filename="AccessTest.ps", diagnostics=diag).parse_compilation_unit()
    symtab = GlobalSymbolTable(default_assembly_name="CommerceApp")
    SymbolCollector(symtab, diag).collect_all([unit])
    AccessChecker(symtab, diag).check_all([unit])

    assert diag.has_errors()
    errors = [d for d in diag.diagnostics if d.code == "PS001"]
    assert len(errors) == 4

    messages = "\n".join(str(e) for e in errors)
    assert "Commerce.Domain.Account.Balance.set' is 'private'" in messages
    assert "Commerce.Domain.Account._secretPin' is 'private'" in messages
    assert "Commerce.Domain.Account.CreatedBy.set' is 'protected'" in messages


def test_ps001_internal_assembly_boundary_enforcement() -> None:
    """
    Verifies that `internal` members are accessible within the same `.psproj` assembly
    (`Commerce.Core`), but emit Rule PS001 when accessed from a different assembly
    (`Commerce.ExternalPlugin`).
    """
    core_source = """
    namespace Commerce.Core;

    public class Ledger
    {
        internal void ReconcileInternal() { }
    }

    public class InternalService
    {
        public void Run(Ledger ledger)
        {
            // Legal within same assembly 'Commerce.Core':
            ledger.ReconcileInternal();
        }
    }
    """

    plugin_source = """
    namespace Commerce.Plugin;

    using Commerce.Core;

    public class PluginRunner
    {
        public void Execute(Ledger ledger)
        {
            // ILLEGAL across assembly boundary ('Commerce.Plugin' != 'Commerce.Core'):
            ledger.ReconcileInternal();
        }
    }
    """
    diag = DiagnosticEngine()
    unit_core = Parser.from_source(
        core_source, file_id=1, ps_filename="Core/Ledger.ps", diagnostics=diag
    ).parse_compilation_unit()
    unit_plugin = Parser.from_source(
        plugin_source, file_id=2, ps_filename="Plugin/PluginRunner.ps", diagnostics=diag
    ).parse_compilation_unit()

    symtab = GlobalSymbolTable()
    collector = SymbolCollector(symtab, diag)
    collector.collect_all([unit_core], assembly_name="Commerce.Core")
    collector.collect_all([unit_plugin], assembly_name="Commerce.Plugin")

    AccessChecker(symtab, diag).check_all([unit_core, unit_plugin])

    assert diag.has_errors()
    errors = [d for d in diag.diagnostics if d.code == "PS001"]
    assert len(errors) == 1
    assert "Ledger.ReconcileInternal' is 'internal'" in errors[0].message
    assert errors[0].span.ps_filename == "Plugin/PluginRunner.ps"


def test_ps003_circular_static_initializer_and_ps004_native_compile_dynamic() -> None:
    """
    Verifies Rules PS003 (circular static initializer cycle across classes)
    and PS004 (`[NativeCompile]` class using `dynamic`).
    """
    source = """
    namespace PerfAndCycles;

    public class Config
    {
        public static string Default = Env.Current;
    }

    public class Env
    {
        public static string Current = Config.Default;
    }

    [NativeCompile]
    public class FastMatrix
    {
        public dynamic Compute(int x) => x;
    }
    """
    diag = DiagnosticEngine()
    unit = Parser.from_source(source, ps_filename="DiagnosticsTest.ps", diagnostics=diag).parse_compilation_unit()
    symtab = GlobalSymbolTable()
    SymbolCollector(symtab, diag).collect_all([unit])
    SlotAndHierarchyAnalyzer(symtab, diag).analyze_all([unit])

    codes = {d.code for d in diag.diagnostics}
    assert "PS003" in codes
    assert "PS004" in codes


def test_ps001_walks_all_statement_and_expression_forms() -> None:
    source = """
    namespace Audit;

    public class Person
    {
        public string Name { get; set; }
        public int Age;
    }

    public class Everything
    {
        private string _secret = "x";
        public string Name { get; private set; } = "n";
        public int Count { get; set; }

        public Everything() : base()
        {
            Name = "ctor";
        }

        public int this[int index]
        {
            get => index;
            private set { Count = value; }
        }

        public void Forms(Person person, Person? maybe, int[] numbers, IEnumerable<int> items, bool flag)
        {
            using var scope = new GradScope();
            await using var asyncScope = new AsyncScope();
            await foreach (var item in items) { Console.WriteLine(item); }
            foreach (int candidate in numbers) { Console.WriteLine(candidate); }
            if (person != null) { Name = person.Name; } else { throw new Exception("x"); }
            while (flag == false) { flag = true; }
            var sliced = numbers[0..1];
            var name = person?.Name ?? "Anonymous";
            var switched = name switch
            {
                "Anonymous" => $"Guest-{1 + 1}",
                string s when s.Length > 5 => s,
                null => "null",
                _ => "Short"
            };
            var tuple = (1, "a");
            var list = [1, 2, 3];
            var obj = new Person("x") { Name = "y", Age = 3 };
            var cast = obj as Person;
            var check = obj is Person p { Name: "y" };
            var not = !true;
            var awaited = await FetchAsync();
            FetchById(42);
            this.Count = 1;
            this[0] = 2;
            try { Run(person, maybe, numbers, items, flag); }
            catch (Exception ex) when (ex != null) { throw ex; }
            catch { throw; }
            finally { Console.WriteLine("done"); }
            switch (Count)
            {
                case 1:
                    Count = 2;
                    break;
                default:
                    Count = 0;
                    break;
            }
            var lambda = (int x, int y) => x + y;
            var blockLambda = () => { Count = 1; };
            yield return 1;
            return;
        }
    }
    """
    diag = DiagnosticEngine()
    unit = Parser.from_source(source, ps_filename="Everything.ps", diagnostics=diag).parse_compilation_unit()
    symtab = GlobalSymbolTable()
    SymbolCollector(symtab, diag).collect_all([unit])
    AccessChecker(symtab, diag).check_all([unit])

    assert not diag.has_errors(), diag.format_all()
    assert any(isinstance(member, PropertyDecl) for member in unit.types[1].members)
    assert any(isinstance(member, IndexerDecl) for member in unit.types[1].members)


def test_ps001_enforces_readonly_property_indexer_constructor_and_type_visibility() -> None:
    source = """
    namespace Boundaries;

    private class Hidden
    {
        public static Hidden Make() => new Hidden();
    }

    internal class Shared { }
    protected class Guarded { }

    public class SameAssembly
    {
        public void Use(Hidden hidden, Shared shared) { }
    }

    public class GuardedUser
    {
        public void Use(Guarded guarded) { }
    }

    public class GuardedChild : Guarded
    {
        public void Use(Guarded guarded) { }
    }

    public class Vault
    {
        private readonly int _pin;
        public Vault() { _pin = 1; }
        public int ReadOnly => 1;
        public int HiddenSet { get; private set; }
        public int Custom
        {
            get { return _pin; }
            private set { HiddenSet = value; }
        }
        public int this[int index]
        {
            get => index;
            private set { HiddenSet = value; }
        }

        public void Mutate()
        {
            _pin = 2;
            ReadOnly = 3;
            HiddenSet = 4;
            Custom = 5;
            this[0] = 6;
        }
    }

    public class Intruder
    {
        public void Probe(Vault vault)
        {
            var publicValue = vault.ReadOnly;
            vault.HiddenSet = 1;
            vault[0] = 1;
            var pin = vault._pin;
        }
    }

    public class Locked
    {
        private Locked() { }
        public static Locked Make() => new Locked();
    }

    public class Outsider
    {
        public void Try()
        {
            var locked = new Locked();
        }
    }
    """
    diag = DiagnosticEngine()
    unit = Parser.from_source(source, ps_filename="Boundaries.ps", diagnostics=diag).parse_compilation_unit()
    symtab = GlobalSymbolTable(default_assembly_name="Core")
    SymbolCollector(symtab, diag).collect_all([unit])
    AccessChecker(symtab, diag).check_all([unit])

    errors = [d for d in diag.diagnostics if d.code == "PS001"]
    assert len(errors) == 8
    messages = "\n".join(d.message for d in errors)
    assert "Boundaries.Hidden' is 'private'" in messages
    assert "Boundaries.Guarded' is 'protected'" in messages
    assert "Boundaries.Vault._pin' is 'readonly'" in messages
    assert "Boundaries.Vault.ReadOnly.set' is 'private (read-only)'" in messages
    assert "Boundaries.Vault.this[].set' is 'private'" in messages
    assert "Boundaries.Locked.Locked' is 'private'" in messages


def test_ps001_internal_type_crosses_assembly_boundary() -> None:
    core_source = """
    namespace Boundaries.Core;

    internal class Ledger
    {
        public static int Count;
    }

    public class Reader
    {
        public void Read(Ledger ledger) { }
    }
    """
    plugin_source = """
    namespace Boundaries.Plugin;

    using Boundaries.Core;

    public class Writer
    {
        public void Write(Ledger ledger) { }
    }
    """
    diag = DiagnosticEngine()
    core_unit = Parser.from_source(
        core_source, file_id=1, ps_filename="Core/Ledger.ps", diagnostics=diag
    ).parse_compilation_unit()
    plugin_unit = Parser.from_source(
        plugin_source, file_id=2, ps_filename="Plugin/Writer.ps", diagnostics=diag
    ).parse_compilation_unit()

    symtab = GlobalSymbolTable()
    collector = SymbolCollector(symtab, diag)
    collector.collect_all([core_unit], assembly_name="Core")
    collector.collect_all([plugin_unit], assembly_name="Plugin")
    AccessChecker(symtab, diag).check_all([core_unit, plugin_unit])

    errors = [d for d in diag.diagnostics if d.code == "PS001"]
    assert len(errors) == 1
    assert "Ledger' is 'internal'" in errors[0].message
    assert errors[0].span.ps_filename == "Plugin/Writer.ps"


def test_slot_analyzer_strategy_matrix_and_async_disposal() -> None:
    source = """
    namespace Strategies;

    using PythonSharp.Core;

    public enum Color { Red, Green }

    public interface IMarker { }

    public struct Vec { public int X; }

    public record struct Pair(int A, int B);

    [NativeCompile]
    public record FastRecord(int X);

    [SchemaModel]
    public class SchemaA { public int X; }

    public class SchemaB : BaseModel { public int Y; }

    public class SyncDisposable : IDisposable
    {
        public void Dispose() { }
    }

    public class AsyncDisposable : IAsyncDisposable
    {
        public void DisposeAsync() { }
    }

    public class ChildDisposable : SyncDisposable { }
    """
    diag = DiagnosticEngine()
    unit = Parser.from_source(source, ps_filename="Strategies.ps", diagnostics=diag).parse_compilation_unit()
    symtab = GlobalSymbolTable()
    SymbolCollector(symtab, diag).collect_all([unit])
    SlotAndHierarchyAnalyzer(symtab, diag).analyze_all()

    assert not diag.has_errors(), diag.format_all()

    def strategy(qname: str):
        return symtab.types_by_qname[qname].ast_node.emission_strategy

    assert strategy("Strategies.Color").ps_types_tuple == ["Strategies.Color"]
    assert strategy("Strategies.IMarker").own_slots == []
    assert strategy("Strategies.Vec").kind == "SlottedDataclass"
    assert strategy("Strategies.Vec").own_slots == ["x"]
    assert strategy("Strategies.Pair").is_frozen_dataclass is False
    assert strategy("Strategies.FastRecord").kind == "NativeCompiledClass"
    assert strategy("Strategies.FastRecord").is_frozen_dataclass is True
    assert strategy("Strategies.SchemaA").kind == "SchemaModel"
    assert strategy("Strategies.SchemaA").own_slots == []
    assert strategy("Strategies.SchemaB").kind == "SchemaModel"
    assert strategy("Strategies.SyncDisposable").generates_context_manager is True
    assert strategy("Strategies.AsyncDisposable").generates_async_context_manager is True
    assert strategy("Strategies.ChildDisposable").generates_context_manager is True


def test_ps003_self_cycles_and_ps004_dynamic_locations() -> None:
    source = """
    namespace Diagnostics;

    public class SelfCycle
    {
        public static int A = A;
        public static int B => B;
        public static int C = Helper.Calc(A) + -SelfCycle.A;
        public static SelfCycle Inst = new SelfCycle();
        public static int Safe = 1;
    }

    [NativeCompile]
    public record Shapes(dynamic Seed)
    {
        public dynamic Field;
        public dynamic Prop { get; set; }

        public dynamic Compute(dynamic input)
        {
            dynamic local = input;
            using dynamic res = new Res();
            foreach (dynamic item in input) { }
            if (true) { dynamic inIf = 1; } else { dynamic inElse = 2; }
            while (false) { dynamic inWhile = 1; }
            try { dynamic inTry = 1; }
            catch (Exception ex) when (true) { dynamic inCatch = ex; }
            finally { dynamic inFinally = 1; }
            switch (1)
            {
                case 1:
                    dynamic inSwitch = 1;
                    break;
                default:
                    break;
            }
            return local;
        }

        public dynamic Arrow() => 1;
    }

    [NativeCompile]
    public class Fast
    {
        public int X;
    }
    """
    diag = DiagnosticEngine()
    unit = Parser.from_source(source, ps_filename="Diagnostics.ps", diagnostics=diag).parse_compilation_unit()
    symtab = GlobalSymbolTable()
    SymbolCollector(symtab, diag).collect_all([unit])
    SlotAndHierarchyAnalyzer(symtab, diag).analyze_all([unit])

    ps003 = [d for d in diag.diagnostics if d.code == "PS003"]
    ps004 = [d for d in diag.diagnostics if d.code == "PS004"]
    assert len(ps003) == 2
    assert len(ps004) == 16
    assert all("SelfCycle" in d.message for d in ps003)
    assert all("Shapes" in d.message for d in ps004)
