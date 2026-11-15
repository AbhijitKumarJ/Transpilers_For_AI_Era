from __future__ import annotations

from psc.diagnostics import DiagnosticEngine
from psc.frontend import Parser
from psc.semantics import GlobalSymbolTable, analyze_compilation_units


def test_type_checker_enforces_constraints_and_nullability() -> None:
    source = """
    namespace Types;

    public class Entity { }
    public class Bad { }
    public class Repo<T> where T : Entity { public T Value; }
    public class Weird<T> where Missing : Entity { }

    public class Consumer
    {
        public Entity Field = null;
        public Entity? MaybeField = null;
        public Entity Prop { get; set; } = null;
        public Entity DefaultProp { get; set; } = default;
        public Entity? NullableProp { get; set; } = null;
        public Entity Custom { get { return null; } set { } }
        public Entity this[int i] { get { return null; } }

        public Entity Get()
        {
            Entity local = null;
            return null;
        }

        public Entity? Maybe() { return null; }
        public Entity Arrow() => null;

        public void Defaults(Entity e = null) { }

        public void Make(Entity e)
        {
            var bad = new Repo<Bad>();
            var good = new Repo<Entity>();
            Use(new Repo<Bad>());
            var fallback = e ?? new Repo<Bad>();
            var arithmetic = 1 + new Repo<Bad>().Value.GetHashCode();
        }

        public void Use(object value) { }
    }
    """
    diag = DiagnosticEngine()
    unit = Parser.from_source(source, ps_filename="Types.ps", diagnostics=diag).parse_compilation_unit()
    symtab = GlobalSymbolTable()
    analyze_compilation_units([unit], symtab, diag)

    assert diag.has_errors()
    errors = [d for d in diag.diagnostics if d.code == "PS000"]
    assert len(errors) == 12
    messages = "\n".join(d.message for d in errors)
    assert "Constraint references undeclared type parameter 'Missing'" in messages
    assert "Cannot assign 'null' to non-nullable target 'Field'" in messages
    assert "Cannot assign 'null' to non-nullable target 'Prop'" in messages
    assert "Cannot assign 'null' to non-nullable target 'local'" in messages
    assert "Cannot assign 'null' to non-nullable target 'Arrow() return'" in messages
    assert "Cannot assign 'null' to non-nullable target 'e'" in messages
    assert messages.count("does not satisfy constraint 'Types.Entity'") == 3
    assert not any("MaybeField" in d.message or "NullableProp" in d.message for d in errors)


def test_type_checker_walks_statement_and_expression_forms() -> None:
    source = """
    namespace Types.Flow;

    public class Person
    {
        public string Name { get; set; }
        public int Age;
    }

    public class Flow
    {
        public string Name { get; set; } = "x";
        public int Count { get; set; }
        public int this[int index]
        {
            get { return index; }
            set { Count = value; }
        }

        public int Run(Person person, int[] numbers, IEnumerable<int> items, bool flag)
        {
            using var scope = new Scope();
            foreach (int candidate in numbers) { Count = candidate; }
            foreach (var item in items) { Count = 1; }
            if (person != null) { Name = person.Name; } else { Name = "none"; }
            while (flag) { flag = false; }
            var tuple = (1, "a");
            var list = [1, 2, 3];
            var obj = new Person { Name = "y", Age = 3 };
            var cast = obj as Person;
            var check = obj is Person p;
            var lambda = (int x) => x + 1;
            var blockLambda = () => { Count = 1; };
            var switched = Name switch { "x" => 1, _ => 0 };
            try { Count = 1; }
            catch (Exception ex) when (ex != null) { Count = 2; }
            finally { Count = 3; }
            switch (Count)
            {
                case 1:
                    Count = 2;
                    break;
                default:
                    break;
            }
            yield return Count;
            return Count;
        }
    }
    """
    diag = DiagnosticEngine()
    unit = Parser.from_source(source, ps_filename="Flow.ps", diagnostics=diag).parse_compilation_unit()
    symtab = GlobalSymbolTable()
    analyze_compilation_units([unit], symtab, diag)

    assert not diag.has_errors(), diag.format_all()
    assert symtab.types_by_qname["Types.Flow.Person"].ast_node.members
    flow = symtab.types_by_qname["Types.Flow.Flow"]
    assert flow is not None
