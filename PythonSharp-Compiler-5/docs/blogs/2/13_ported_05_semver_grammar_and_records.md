# Level 2 — Blog 13: Ported 05 — SemVer (`05_semver`): Semantic Version 2.0.0, Records & Value Equality

We conclude **Tier 2: Algorithms & Math** with **`05_semver`**, ported from canonical concepts in the `semver` specification and Python package.

This port tests several critical modern C# language features:
1. **Positional Record Types**: `public record SemVer(...)` and their lowering to `@dataclass(slots=True, frozen=True)`.
2. **String Interpolation**: `$"{Major}.{Minor}.{Patch}"` compiling to native Python f-strings.
3. **Exception Translation**: `ArgumentException` mapping to Python's native `ValueError`.
4. **SemVer 2.0.0 Precedence Rules**: Complex multidimensional comparison chains (Major $\to$ Minor $\to$ Patch $\to$ Prerelease $\to$ Build metadata).

---

## 1. The Specification: SemVer 2.0.0 Precedence

According to the official [SemVer 2.0.0 specification](https://semver.org/):
1. **Normal Versioning**: Precedence is determined by the first difference when comparing `Major`, `Minor`, and `Patch` numerically: `1.0.0 < 2.0.0 < 2.1.0 < 2.1.1`.
2. **Prerelease Precedence**: A normal version has greater precedence than a prerelease version: `1.0.0-alpha < 1.0.0`.
3. **Prerelease Identifier Rules**: Dot-separated identifiers (`alpha.1`, `beta.2`) are compared left to right:
   - Identifiers consisting of only digits are compared numerically: `1 < 2`.
   - Identifiers with letters are compared lexically: `alpha < beta`.
   - Numeric identifiers always have lower precedence than alphanumeric ones.
4. **Build Metadata Exclusion**: Build metadata (`+build.1`, `+sha.5114f85`) MUST be ignored when determining version precedence: `1.0.0+1 == 1.0.0+2`.

---

## 2. Project Layout

The project lives under [`Samples/Ported/05_semver/`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/05_semver/):

```
Samples/Ported/05_semver/
├── SemVer.psproj           # Project configuration manifest
├── SemanticVersion.ps      # C# record source implementation
├── README.md               # Documentation and build instructions
├── run_semver.py           # Automated test runner and verification suite
└── dist/
    └── sem_ver_util.py     # Transpiled pure Python 3.11 module
```

---

## 3. The C# Source Implementation: `SemanticVersion.ps`

In [`SemanticVersion.ps`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/05_semver/SemanticVersion.ps), `SemVer` is declared as an immutable positional record:

```csharp
namespace SemVerUtil;

using PythonSharp.Core;

public record SemVer(int Major, int Minor, int Patch, string Prerelease = "", string Build = "")
{
    public string Formatted()
    {
        string ver = $"{Major}.{Minor}.{Patch}";
        if (Prerelease.Length > 0)
        {
            ver = $"{ver}-{Prerelease}";
        }
        if (Build.Length > 0)
        {
            ver = $"{ver}+{Build}";
        }
        return ver;
    }

    public static SemVer Parse(string versionString)
    {
        if (string.IsNullOrEmpty(versionString))
        {
            throw new ArgumentException("Version string cannot be null or empty");
        }

        string work = versionString.Trim();
        string build = "";
        int buildIdx = work.IndexOf("+");
        if (buildIdx >= 0)
        {
            build = work.Substring(buildIdx + 1);
            work = work.Substring(0, buildIdx);
        }

        string prerelease = "";
        int preIdx = work.IndexOf("-");
        if (preIdx >= 0)
        {
            prerelease = work.Substring(preIdx + 1);
            work = work.Substring(0, preIdx);
        }

        List<string> parts = work.Split(".");
        if (parts.Count != 3)
        {
            throw new ArgumentException("Invalid SemVer format. Expected 'Major.Minor.Patch'");
        }

        int major = Int32.Parse(parts[0]);
        int minor = Int32.Parse(parts[1]);
        int patch = Int32.Parse(parts[2]);

        return new SemVer(major, minor, patch, prerelease, build);
    }

    public int CompareTo(SemVer other)
    {
        if (Major != other.Major) return Major > other.Major ? 1 : -1;
        if (Minor != other.Minor) return Minor > other.Minor ? 1 : -1;
        if (Patch != other.Patch) return Patch > other.Patch ? 1 : -1;

        bool hasPre = Prerelease.Length > 0;
        bool otherHasPre = other.Prerelease.Length > 0;

        if (!hasPre && !otherHasPre) return 0;
        if (!hasPre && otherHasPre) return 1;   // 1.0.0 > 1.0.0-alpha
        if (hasPre && !otherHasPre) return -1;  // 1.0.0-alpha < 1.0.0

        return ComparePrerelease(Prerelease, other.Prerelease);
    }

    public bool IsCompatibleWith(SemVer other)
    {
        if (Major > 0)
        {
            return Major == other.Major && CompareTo(other) >= 0;
        }
        return Major == other.Major && Minor == other.Minor && CompareTo(other) >= 0;
    }
}
```

---

## 4. The Transpiled Output: `@dataclass(frozen=True, slots=True)`

Compiling with:
```bash
psc build Samples/Ported/05_semver -o Samples/Ported/05_semver/dist
```
produces [`Samples/Ported/05_semver/dist/sem_ver_util.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/05_semver/dist/sem_ver_util.py):

```python
# Auto-generated by PythonSharp (psc) — Bytecode line-pinned to SemanticVersion.ps
from __future__ import annotations
from dataclasses import dataclass

@dataclass(slots=True, frozen=True)
class SemVer:
    __ps_types__ = ('SemVerUtil.SemVer',)
    major: int
    minor: int
    patch: int
    prerelease: str = ''
    build: str = ''

    def formatted(self) -> str:
        ver: str = f'{self.major}.{self.minor}.{self.patch}'
        if len(self.prerelease) > 0:
            ver = f'{ver}-{self.prerelease}'
        if len(self.build) > 0:
            ver = f'{ver}+{self.build}'
        return ver

    @staticmethod
    def parse(version_string: str) -> SemVer:
        if version_string is None or len(version_string) == 0:
            raise ValueError('Version string cannot be null or empty')
        work: str = version_string.strip()
        build: str = ''
        build_idx: int = work.find('+')
        if build_idx >= 0:
            build = work[build_idx + 1:]
            work = work[0:0 + build_idx]
        prerelease: str = ''
        pre_idx: int = work.find('-')
        if pre_idx >= 0:
            prerelease = work[pre_idx + 1:]
            work = work[0:0 + pre_idx]
        parts: list[str] = work.split('.')
        if len(parts) != 3:
            raise ValueError("Invalid SemVer format. Expected 'Major.Minor.Patch'")
        major: int = int(parts[0])
        minor: int = int(parts[1])
        patch: int = int(parts[2])
        return SemVer(major, minor, patch, prerelease, build)

    def compare_to(self, other: SemVer) -> int:
        if self.major != other.major:
            return 1 if self.major > other.major else -1
        if self.minor != other.minor:
            return 1 if self.minor > other.minor else -1
        if self.patch != other.patch:
            return 1 if self.patch > other.patch else -1
        has_pre: bool = len(self.prerelease) > 0
        other_has_pre: bool = len(other.prerelease) > 0
        if not has_pre and (not other_has_pre):
            return 0
        if not has_pre and other_has_pre:
            return 1
        if has_pre and (not other_has_pre):
            return -1
        return SemVer.compare_prerelease(self.prerelease, other.prerelease)
```

### Compiler Lowering Feats:
1. **Positional Records $\to$ Frozen Dataclasses**: In C#, records provide value equality, immutability, and hash codes. PythonSharp emits `@dataclass(slots=True, frozen=True)` which provides automatic `__eq__`, `__hash__`, and `__repr__` methods natively in Python.
2. **String Interpolation $\to$ f-strings**: `$"{Major}.{Minor}.{Patch}"` lowers directly to Python 3.11 `f'{self.major}.{self.minor}.{self.patch}'`.
3. **Ambient Exception Mapping**: In C#, invalid arguments raise `ArgumentException`. In Python, the idiomatic equivalent is `ValueError`. PythonSharp automatically remaps `ArgumentException` to `ValueError`.
4. **`IndexOf` to `.find()`**: `work.IndexOf("+")` maps to `work.find('+')`.

---

## 5. Verification Test Suite

[`run_semver.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/05_semver/run_semver.py) validates the SemVer parser across 10 ordered versions:

```python
# 1. Parsing and formatting
v = SemVer.parse("1.2.3")
assert v.major == 1 and v.minor == 2 and v.patch == 3
assert v.formatted() == "1.2.3"

# 2. Prerelease and build metadata
v_complex = SemVer.parse("1.0.0-beta.2+exp.sha.5114f85")
assert v_complex.prerelease == "beta.2"
assert v_complex.build == "exp.sha.5114f85"

# 3. Canonical SemVer 2.0.0 precedence chain:
versions = [
    SemVer.parse("1.0.0-alpha"),
    SemVer.parse("1.0.0-alpha.1"),
    SemVer.parse("1.0.0-alpha.beta"),
    SemVer.parse("1.0.0-beta"),
    SemVer.parse("1.0.0-beta.2"),
    SemVer.parse("1.0.0-beta.11"),
    SemVer.parse("1.0.0-rc.1"),
    SemVer.parse("1.0.0"),
    SemVer.parse("2.0.0"),
    SemVer.parse("2.1.0"),
]

for i in range(len(versions) - 1):
    assert versions[i].is_less_than(versions[i + 1])
    assert versions[i + 1].is_greater_than(versions[i])

# 4. Build metadata ignored in precedence
v_b1 = SemVer.parse("1.0.0+build.1")
v_b2 = SemVer.parse("1.0.0+build.2")
assert v_b1.is_equal_to(v_b2)
```

Running the runner:
```bash
python3 Samples/Ported/05_semver/run_semver.py
```
Outputs:
```
=== Step 1: Building SemVer via `psc build` ===
Build is up to date: outputs in '.../dist' are fresh.

=== Step 2: Testing Ported SemVer Functionality ===
[PASS] SemVer.parse('1.2.3') -> 1.2.3
[PASS] SemVer.parse('2.0.1-alpha.1') -> 2.0.1-alpha.1
[PASS] SemVer.parse with prerelease and build metadata -> 1.0.0-beta.2+exp.sha.5114f85
[PASS] SemVer.parse('invalid-version') correctly raised ValueError
[PASS] Canonical SemVer 2.0.0 precedence chain verified across 10 versions
[PASS] Build metadata ignored in precedence (1.0.0+build.1 == 1.0.0+build.2)
[PASS] SemVer.is_compatible_with caret rules verified

All semver verification checks succeeded with 0 errors!
```

---

## Key Takeaways

1. **Modern C# Records in Python**: Emitting `@dataclass(frozen=True, slots=True)` gives Python developers the full power of immutable C# records with value semantics.
2. **Native Exception Translation**: Cross-language exceptions (`ArgumentException` $\to$ `ValueError`) feel natural to Python consumers.
3. **Complex Logic Without Dependencies**: Complete SemVer 2.0.0 compliance in less than 200 lines of typed C#.

---

## Next Steps

We now move to **Tier 3: Utilities & Tools**!

In **[Blog 14: Ported 06 — Micro-Tqdm (`06_micro_tqdm`): Terminal Control, Carriage Returns & Timing](./14_ported_06_micro_tqdm_terminal_and_timing.md)**, we examine terminal rendering, carriage return carriage updates (`\r`), and dynamic rate calculation!

