from __future__ import annotations

import ast

from psc.codegen import ExpressionLowerer
from psc.diagnostics import DiagnosticEngine
from psc.frontend import MethodDecl, Parser
from psc.semantics import GlobalSymbolTable


def test_lower_kitchen_sink_statements_expressions_and_patterns() -> None:
    source = """
    namespace Kitchen.Flow;

    public record Person(string Name);

    public class Flow
    {
        public async void Run(object tensor, object? user, object items, int[] numbers, int number, bool flag)
        {
            using var scope = new GradScope();
            await using var asyncScope = new AsyncScope();
            await foreach (var item in items) { Console.WriteLine(item); }
            foreach (int candidate in numbers) { Console.WriteLine(candidate); }
            if (user != null) { return; } else if (user == null) { throw; } else { throw new Exception("x"); }
            while (user == null) { user = null; }
            var sliced = tensor[1..5, ^2.., ::2, 3:5:2, ..];
            var indexed = tensor[^1];
            var single = tensor[0];
            var name = user?.Profile?.Name ?? "Anonymous";
            var called = user?.Get<int>(1);
            var memberCall = tensor.Map<string>(name);
            var switched = name switch
            {
                "Anonymous" => $"Guest-{1 + 1}",
                string s when s.Length > 5 => s,
                null => "null",
                _ => "Short"
            };
            var tuple = (1, "a");
            var list = [1, 2, 3];
            var obj = new Person("x") { Name = "y" };
            var bare = new Person;
            var constructed = new List<int>();
            var power = 2 ** 3;
            var remainder = 7 % 2;
            var cast = obj as Person;
            var check = obj is Person p { Name: "y" };
            var not = !true;
            var negative = -1;
            var awaited = await FetchAsync();
            var fallback = name ?? "fallback";
            number = 1;
            number += 1;
            number -= 1;
            number *= 2;
            number /= 2;
            name ??= "x";
            FetchById(42);
            Console.WriteLine(name);
            string.Join(",", name);
            try { Run(tensor, user, items, numbers, number, flag); }
            catch (Exception ex) when (ex != null) { throw ex; }
            catch { throw; }
            finally { Console.WriteLine("done"); }
            switch (number)
            {
                case 1:
                    number = 2;
                    break;
                case int i when i > 0:
                    number = i;
                default:
                    number = 0;
                    break;
            }
            int typed = 1;
            List<int> typedList = [1, 2];
            (int Id, string Name) pair = (1, "x");
            Func<int, int, int> lambda = (int x, int y) => x + y;
            Func<int, int> untyped = (x, y) => x;
            Func<int, int> simple = x => x + 1;
            Func<int, int> asyncLambda = async x => await FetchAsync();
            Action blockLambda = () => { Console.WriteLine(); };
            yield return 1;
            yield break;
            return;
        }
    }
    """
    diagnostics = DiagnosticEngine()
    unit = Parser.from_source(source, ps_filename="Flow.ps", diagnostics=diagnostics).parse_compilation_unit()
    assert not diagnostics.has_errors(), diagnostics.format_all()

    flow = next(t for t in unit.types if t.name == "Flow")
    run = next(m for m in flow.members if isinstance(m, MethodDecl) and m.name == "Run")
    assert run.body is not None
    lowered = ExpressionLowerer(GlobalSymbolTable()).lower_block(run.body)
    rendered = ast.unparse(ast.Module(body=lowered, type_ignores=[]))
    assert "with GradScope() as scope" in rendered
    assert "async with AsyncScope() as async_scope" in rendered
    assert "async for item in items" in rendered
    assert "tensor[1:5, -2:, ::2, 3:5:2, :]" in rendered
    assert "(_ps_nc3 := user) is not None" in rendered
    assert ".get(1)" in rendered
    assert "while user == None" in rendered
    assert "match number" in rendered
    assert "yield 1" in rendered
    assert "raise" in rendered
    assert "lambda_: Callable[[int, int], int] = lambda x, y: x + y" in rendered
    assert "async def _ps_lambda" in rendered
    assert "def _ps_lambda" in rendered

    wrapped = ast.Module(
        body=[
            ast.AsyncFunctionDef(
                name="run",
                args=ast.arguments(
                    posonlyargs=[],
                    args=[],
                    kwonlyargs=[],
                    kw_defaults=[],
                    defaults=[],
                ),
                body=lowered,
                decorator_list=[],
            )
        ],
        type_ignores=[],
    )
    ast.fix_missing_locations(wrapped)
    compile(wrapped, filename="Flow.ps", mode="exec")
