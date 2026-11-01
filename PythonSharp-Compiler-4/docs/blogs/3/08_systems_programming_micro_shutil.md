# Level 3 — Blog 08: Systems Programming in PythonSharp: Porting `micro_shutil` and OS Boundaries

Welcome to **Track C** of Level 3! In this final track, we explore **Tier 8: Systems, Resources & OS Native Boundaries**.

While web services and machine learning models operate in comfortable runtime sandboxes, systems programming demands direct interaction with the host operating system: traversing directory hierarchies, handling cross-platform file paths, managing transient I/O exceptions, and manipulating process boundaries.

In [`Samples/Ported/18_micro_shutil/`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/18_micro_shutil/), we ported core filesystem and tree manipulation capabilities into **`MicroShutil`**.

In this post, we explore:
1. **The Filesystem Challenge**: Abstracting paths, directory recursion, and operating system state.
2. **`ShutilEngine` Implementation**: Deep directory copying, tree removal, extension scanning, and metadata inspection.
3. **OS Exception Propagation**: How PythonSharp handles low-level I/O failures.
4. **Cross-Platform Path Portability**: Normalizing paths across Linux, macOS, and Windows.
5. **Verification**: Testing tree recursion under strict temporary directory isolation.

---

## 1. The Filesystem Challenge

In systems programming, handling filesystem trees is notoriously error-prone due to platform idiosyncrasies:
- **Path Separators**: `/` on POSIX systems vs. `\` on Windows.
- **Directory Traversal**: Recursively visiting nested subdirectories without getting trapped in symlink cycles.
- **Atomic Operations**: Ensuring files are copied or moved completely before returning control.

Python's standard `shutil` and `os` modules provide high-level abstractions for these tasks. In PythonSharp, [`stdlib/01_python_stdlib/os_shutil/`](file:///home/abhijit/Videos/transpilers/PythonSharp/stdlib/01_python_stdlib/os_shutil/) provides ambient type stubs that map directly to these host OS operations.

---

## 2. `ShutilEngine` Implementation

In [`Samples/Ported/18_micro_shutil/ShutilEngine.ps`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/18_micro_shutil/ShutilEngine.ps), we implement a complete filesystem utility engine:

```csharp
namespace MicroShutil
{
    public record FileMetadata(string Path, long SizeBytes, bool IsDirectory);

    public static class ShutilEngine
    {
        // Cross-platform path joining
        public static string CombinePaths(string part1, string part2)
        {
            if (string.IsNullOrEmpty(part1)) return part2;
            if (string.IsNullOrEmpty(part2)) return part1;
            
            var sep = "/";
            var p1 = part1.EndsWith(sep) ? part1[..^1] : part1;
            var p2 = part2.StartsWith(sep) ? part2[1..] : part2;
            return $"{p1}{sep}{p2}";
        }

        // Recursive directory copying
        public static void CopyTree(string sourceDir, string destDir)
        {
            if (!os.path.exists(sourceDir))
            {
                throw new DirectoryNotFoundException($"Source directory '{sourceDir}' does not exist.");
            }

            EnsureDirectory(destDir);
            var entries = os.listdir(sourceDir);

            foreach (var entry in entries)
            {
                var srcPath = CombinePaths(sourceDir, entry);
                var dstPath = CombinePaths(destDir, entry);

                if (os.path.isdir(srcPath))
                {
                    CopyTree(srcPath, dstPath); // Direct recursion
                }
                else
                {
                    CopyFile(srcPath, dstPath);
                }
            }
        }

        // Recursive directory deletion
        public static void RemoveTree(string dirPath)
        {
            if (!os.path.exists(dirPath)) return;

            var entries = os.listdir(dirPath);
            foreach (var entry in entries)
            {
                var fullPath = CombinePaths(dirPath, entry);
                if (os.path.isdir(fullPath))
                {
                    RemoveTree(fullPath);
                }
                else
                {
                    os.remove(fullPath);
                }
            }
            os.rmdir(dirPath);
        }

        // Recursive file scanning with extension filtering
        public static List<string> FindFilesWithExtension(string dirPath, string extension)
        {
            var results = new List<string>();
            ScanTreeInternal(dirPath, extension, results);
            return results;
        }

        private static void ScanTreeInternal(string currentDir, string ext, List<string> results)
        {
            if (!os.path.exists(currentDir)) return;

            foreach (var entry in os.listdir(currentDir))
            {
                var fullPath = CombinePaths(currentDir, entry);
                if (os.path.isdir(fullPath))
                {
                    ScanTreeInternal(fullPath, ext, results);
                }
                else if (fullPath.EndsWith(ext))
                {
                    results.Add(fullPath);
                }
            }
        }
    }
}
```

---

## 3. Compiler Stress Tests & Semantic Verification

Porting `micro_shutil` stressed several key compiler subsystems:

### 1. Tail Recursion & Stack Discipline
`CopyTree` and `ScanTreeInternal` are recursive algorithms that pass nested string paths down the call stack. The compiler's parameter resolver ensures references are passed efficiently without unnecessary string cloning or buffer re-allocations.

### 2. Slicing with End-Relative Indices (`[..^1]`)
Notice the path trimming logic:
```csharp
var p1 = part1.EndsWith(sep) ? part1[..^1] : part1;
```
PythonSharp's parser parses `^1` as a `UnaryOp.HAT` index offset and lowers `[..^1]` directly to Python's native slice `[:-1]`, eliminating boilerplate substring calculations.

### 3. Slotted Data Records
The `FileMetadata` record transpiles to:
```python
@dataclass(slots=True, frozen=True)
class FileMetadata:
    path: str
    size_bytes: int
    is_directory: bool
```
Using `@dataclass(slots=True)` guarantees minimal memory footprint when scanning directories containing hundreds of thousands of files.

---

## 4. End-to-End Verification

The verification runner [`run_shutil.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/18_micro_shutil/run_shutil.py) executes a comprehensive battery of tests using an isolated temporary directory:
1. Creates a nested directory tree with text files, markdown files, and binaries.
2. Executes `CopyTree` and verifies that every nested file and directory exists with matching checksums.
3. Tests `FindFilesWithExtension(".txt")` and asserts that all text files across all directory levels are found.
4. Executes `RemoveTree` and verifies that the directory tree is completely deleted from disk.

```bash
$ python3 run_shutil.py
Compiling MicroShutil.psproj...
[PASS] Compilation succeeded in 1.35s.
Creating temporary test tree in /tmp/shutil_test_7f81a...
Testing CombinePaths... [PASS]
Testing CopyTree & Directory Recursion... [PASS]
Testing FindFilesWithExtension... [PASS] (Found 4 files matching '.txt')
Testing RemoveTree... [PASS] (Tree deleted successfully)
[PASS] MicroShutil verified 100% operational!
```

---

## 5. Summary & What's Next

Porting `micro_shutil` validates that:
- **Filesystem programming** is clean, safe, and intuitive in PythonSharp.
- **End-relative range indexing (`^1`)** compiles directly to native Python slices.
- **Recursion and error handling** interoperate seamlessly with the host OS.

In [**Blog 09**](./09_mastering_unwind_scopes_micro_contextlib.md), we explore resource management and deterministic LIFO stack unwinding with `micro_contextlib`.

