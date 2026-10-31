The complete four-file `.d.ps` bundles (`00_*.primitives.d.ps`, `01_*.raw.d.ps`, `02_*.csharp.d.ps`, and `03_*.enterprise.d.ps`) for `stdlib/01_python_stdlib/` cover the six core modules (`os_shutil`, `sys`, `json`, `re`, `time_datetime`, `logging`) plus the remaining roadmap standard library packages (`urllib_http`, `contextlib_subprocess`, and `pathlib_hashlib_uuid`).

Every file declares a single top-level `namespace` with explicit `using PythonSharp.Core;` imports, `[SurfaceLevel]`, `[CanonicalApi]`, `[MapsTo]`, and `[InlineTemplate]` attributes so `load_project()` and `SymbolCollector` resolve them with zero wrapper overhead.

---

## 1. `os_shutil` (File System, Paths, Directory Trees & Environment Variables)

Implements the Triple-Surface bindings for `os`, `os.path`, and `shutil` alongside `EnvironmentVariableMap` and `DirectoryEntry` primitives.

### `stdlib/01_python_stdlib/os_shutil/00_os.primitives.d.ps`

```csharp
namespace PythonSharp.System.IO;

using PythonSharp.Core;
extern using os as _py_os;

[MapsTo("os._Environ")]
[RuntimeType("dict")]
public primitive class EnvironmentVariableMap : IEnumerable<KeyValuePair<string, string>>
{
    [InlineTemplate("{self}[{0}]")]
    public extern string this[string variableName]
    {
        get;
        [InlineTemplate("{self}[{0}] = {value}")] set;
    }

    // --- Surface 1: Self-Documenting Enterprise Methods ---
    [MapsTo("get")]
    public extern string? GetVariableOrDefault(string variableName, string? defaultValue = null);

    [InlineTemplate("({0} in {self})")]
    public extern bool ContainsVariable(string variableName);

    // --- Surface 3: C#-Standardized Methods ---
    [CanonicalApi("PythonSharp.System.IO.EnvironmentVariableMap.GetVariableOrDefault")]
    [MapsTo("get")]
    public extern string? Get(string key, string? defaultValue = null);

    [CanonicalApi("PythonSharp.System.IO.EnvironmentVariableMap.ContainsVariable")]
    [InlineTemplate("({0} in {self})")]
    public extern bool ContainsKey(string key);

    // --- Surface 2: Raw Python snake_case Methods ---
    [CanonicalApi("PythonSharp.System.IO.EnvironmentVariableMap.GetVariableOrDefault", "Get")]
    [MapsTo("get")]
    public extern string? get(string key, string? defaultValue = null);
}

[MapsTo("os.DirEntry")]
[RuntimeType("os.DirEntry")]
public primitive class DirectoryEntry
{
    [InlineTemplate("{self}.name")]
    public extern string EntryName { get; }

    [CanonicalApi("PythonSharp.System.IO.DirectoryEntry.EntryName")]
    [InlineTemplate("{self}.name")]
    public extern string Name { get; }

    [CanonicalApi("PythonSharp.System.IO.DirectoryEntry.EntryName", "Name")]
    [InlineTemplate("{self}.name")]
    public extern string name { get; }

    [InlineTemplate("{self}.path")]
    public extern string FullPath { get; }

    [CanonicalApi("PythonSharp.System.IO.DirectoryEntry.FullPath")]
    [InlineTemplate("{self}.path")]
    public extern string Path { get; }

    [CanonicalApi("PythonSharp.System.IO.DirectoryEntry.FullPath", "Path")]
    [InlineTemplate("{self}.path")]
    public extern string path { get; }

    [MapsTo("is_dir")]
    public extern bool IsDirectory();

    [CanonicalApi("PythonSharp.System.IO.DirectoryEntry.IsDirectory")]
    [MapsTo("is_dir")]
    public extern bool is_dir();

    [MapsTo("is_file")]
    public extern bool IsRegularFile();

    [CanonicalApi("PythonSharp.System.IO.DirectoryEntry.IsRegularFile")]
    [MapsTo("is_file")]
    public extern bool IsFile();

    [CanonicalApi("PythonSharp.System.IO.DirectoryEntry.IsRegularFile", "IsFile")]
    [MapsTo("is_file")]
    public extern bool is_file();
}

```

### `stdlib/01_python_stdlib/os_shutil/01_os.raw.d.ps`

```csharp
namespace os;

using PythonSharp.Core;
using PythonSharp.System.IO;
extern using os as _py_os;
extern using shutil as _py_shutil;

[SurfaceLevel(2)]
[MapsTo("_py_os.path")]
public static primitive class OsPathModule
{
    [CanonicalApi("PythonSharp.System.IO.FilePath.Combine", "PythonSharp.OS.OS.Path.Join")]
    [InlineTemplate("_py_os.path.join({0}, {1})")]
    public static extern string join(string a, string b);

    [CanonicalApi("PythonSharp.System.IO.FilePath.CombineThree", "PythonSharp.OS.OS.Path.Join")]
    [InlineTemplate("_py_os.path.join({0}, {1}, {2})")]
    public static extern string join(string a, string b, string c);

    [CanonicalApi("PythonSharp.System.IO.FileSystemEntry.ExistsAtPath", "PythonSharp.OS.OS.Path.Exists")]
    [InlineTemplate("_py_os.path.exists({0})")]
    public static extern bool exists(string path);

    [CanonicalApi("PythonSharp.System.IO.FileSystemEntry.IsRegularFile", "PythonSharp.OS.OS.Path.IsFile")]
    [InlineTemplate("_py_os.path.isfile({0})")]
    public static extern bool isfile(string path);

    [CanonicalApi("PythonSharp.System.IO.FileSystemEntry.IsDirectory", "PythonSharp.OS.OS.Path.IsDir")]
    [InlineTemplate("_py_os.path.isdir({0})")]
    public static extern bool isdir(string path);

    [CanonicalApi("PythonSharp.System.IO.FilePath.GetAbsolutePath", "PythonSharp.OS.OS.Path.AbsPath")]
    [InlineTemplate("_py_os.path.abspath({0})")]
    public static extern string abspath(string path);

    [CanonicalApi("PythonSharp.System.IO.FilePath.GetDirectoryName", "PythonSharp.OS.OS.Path.DirName")]
    [InlineTemplate("_py_os.path.dirname({0})")]
    public static extern string dirname(string path);

    [CanonicalApi("PythonSharp.System.IO.FilePath.GetFileName", "PythonSharp.OS.OS.Path.BaseName")]
    [InlineTemplate("_py_os.path.basename({0})")]
    public static extern string basename(string path);

    [CanonicalApi("PythonSharp.System.IO.FilePath.SplitExtension", "PythonSharp.OS.OS.Path.SplitExt")]
    [InlineTemplate("_py_os.path.splitext({0})")]
    public static extern (string root, string ext) splitext(string path);
}

[SurfaceLevel(2)]
[MapsTo("_py_os")]
public static primitive class os
{
    [CanonicalApi("PythonSharp.System.IO.EnvironmentVariables.Variables", "PythonSharp.OS.OS.Environ")]
    [InlineTemplate("_py_os.environ")]
    public static extern EnvironmentVariableMap environ { get; }

    [CanonicalApi("PythonSharp.System.IO.FilePath.DirectorySeparator", "PythonSharp.OS.OS.Sep")]
    [InlineTemplate("_py_os.sep")]
    public static extern string sep { get; }

    [InlineTemplate("_py_os.path")]
    public static extern OsPathModule path { get; }

    [CanonicalApi("PythonSharp.System.IO.EnvironmentVariables.GetVariableOrDefault", "PythonSharp.OS.OS.GetEnv")]
    [InlineTemplate("_py_os.getenv({0}, {1})")]
    public static extern string? getenv(string key, string? @default = null);

    [CanonicalApi("PythonSharp.System.IO.DirectoryOperations.GetCurrentWorkingDirectory", "PythonSharp.OS.OS.GetCwd")]
    [InlineTemplate("_py_os.getcwd()")]
    public static extern string getcwd();

    [CanonicalApi("PythonSharp.System.IO.DirectoryOperations.ListEntryNames", "PythonSharp.OS.OS.ListDir")]
    [InlineTemplate("_py_os.listdir({0})")]
    public static extern List<string> listdir(string path = ".");

    [CanonicalApi("PythonSharp.System.IO.DirectoryOperations.CreateDirectoryRecursive", "PythonSharp.OS.OS.MakeDirs")]
    [InlineTemplate("_py_os.makedirs({0}, exist_ok={1})")]
    public static extern void makedirs(string name, bool exist_ok = true);

    [CanonicalApi("PythonSharp.System.IO.FileOperations.DeleteFile", "PythonSharp.OS.OS.Remove")]
    [InlineTemplate("_py_os.remove({0})")]
    public static extern void remove(string path);

    [CanonicalApi("PythonSharp.System.IO.FileOperations.RenameEntry", "PythonSharp.OS.OS.Rename")]
    [InlineTemplate("_py_os.rename({0}, {1})")]
    public static extern void rename(string src, string dst);
}

[SurfaceLevel(2)]
[MapsTo("_py_shutil")]
public static primitive class shutil
{
    [CanonicalApi("PythonSharp.System.IO.FileOperations.CopyFileWithMetadata", "PythonSharp.OS.Shutil.Copy2")]
    [InlineTemplate("_py_shutil.copy2({0}, {1})")]
    public static extern string copy2(string src, string dst);

    [CanonicalApi("PythonSharp.System.IO.DirectoryOperations.CopyDirectoryTreeRecursively", "PythonSharp.OS.Shutil.CopyTree")]
    [InlineTemplate("_py_shutil.copytree({0}, {1}, dirs_exist_ok={2})")]
    public static extern string copytree(string src, string dst, bool dirs_exist_ok = true);

    [CanonicalApi("PythonSharp.System.IO.DirectoryOperations.DeleteDirectoryTreeRecursively", "PythonSharp.OS.Shutil.RmTree")]
    [InlineTemplate("_py_shutil.rmtree({0}, ignore_errors={1})")]
    public static extern void rmtree(string path, bool ignore_errors = false);

    [CanonicalApi("PythonSharp.System.IO.FileOperations.MoveEntry", "PythonSharp.OS.Shutil.Move")]
    [InlineTemplate("_py_shutil.move({0}, {1})")]
    public static extern string move(string src, string dst);
}

```

### `stdlib/01_python_stdlib/os_shutil/02_os.csharp.d.ps`

```csharp
namespace PythonSharp.OS;

using PythonSharp.Core;
using PythonSharp.System.IO;
extern using os as _py_os;
extern using shutil as _py_shutil;

[SurfaceLevel(3)]
[MapsTo("_py_os.path")]
public static primitive class OsPathBridgeModule
{
    [CanonicalApi("PythonSharp.System.IO.FilePath.Combine")]
    [InlineTemplate("_py_os.path.join({0}, {1})")]
    public static extern string Join(string path1, string path2);

    [CanonicalApi("PythonSharp.System.IO.FilePath.CombineThree")]
    [InlineTemplate("_py_os.path.join({0}, {1}, {2})")]
    public static extern string Join(string path1, string path2, string path3);

    [CanonicalApi("PythonSharp.System.IO.FileSystemEntry.ExistsAtPath")]
    [InlineTemplate("_py_os.path.exists({0})")]
    public static extern bool Exists(string path);

    [CanonicalApi("PythonSharp.System.IO.FileSystemEntry.IsRegularFile")]
    [InlineTemplate("_py_os.path.isfile({0})")]
    public static extern bool IsFile(string path);

    [CanonicalApi("PythonSharp.System.IO.FileSystemEntry.IsDirectory")]
    [InlineTemplate("_py_os.path.isdir({0})")]
    public static extern bool IsDir(string path);

    [CanonicalApi("PythonSharp.System.IO.FilePath.GetAbsolutePath")]
    [InlineTemplate("_py_os.path.abspath({0})")]
    public static extern string AbsPath(string path);

    [CanonicalApi("PythonSharp.System.IO.FilePath.GetDirectoryName")]
    [InlineTemplate("_py_os.path.dirname({0})")]
    public static extern string DirName(string path);

    [CanonicalApi("PythonSharp.System.IO.FilePath.GetFileName")]
    [InlineTemplate("_py_os.path.basename({0})")]
    public static extern string BaseName(string path);

    [CanonicalApi("PythonSharp.System.IO.FilePath.SplitExtension")]
    [InlineTemplate("_py_os.path.splitext({0})")]
    public static extern (string Root, string Extension) SplitExt(string path);
}

[SurfaceLevel(3)]
[MapsTo("_py_os")]
public static primitive class OS
{
    [CanonicalApi("PythonSharp.System.IO.EnvironmentVariables.Variables")]
    [InlineTemplate("_py_os.environ")]
    public static extern EnvironmentVariableMap Environ { get; }

    [CanonicalApi("PythonSharp.System.IO.FilePath.DirectorySeparator")]
    [InlineTemplate("_py_os.sep")]
    public static extern string Sep { get; }

    [InlineTemplate("_py_os.path")]
    public static extern OsPathBridgeModule Path { get; }

    [CanonicalApi("PythonSharp.System.IO.EnvironmentVariables.GetVariableOrDefault")]
    [InlineTemplate("_py_os.getenv({0}, {1})")]
    public static extern string? GetEnv(string key, string? defaultValue = null);

    [CanonicalApi("PythonSharp.System.IO.DirectoryOperations.GetCurrentWorkingDirectory")]
    [InlineTemplate("_py_os.getcwd()")]
    public static extern string GetCwd();

    [CanonicalApi("PythonSharp.System.IO.DirectoryOperations.ListEntryNames")]
    [InlineTemplate("_py_os.listdir({0})")]
    public static extern List<string> ListDir(string path = ".");

    [CanonicalApi("PythonSharp.System.IO.DirectoryOperations.CreateDirectoryRecursive")]
    [InlineTemplate("_py_os.makedirs({0}, exist_ok={1})")]
    public static extern void MakeDirs(string path, bool existOk = true);

    [CanonicalApi("PythonSharp.System.IO.FileOperations.DeleteFile")]
    [InlineTemplate("_py_os.remove({0})")]
    public static extern void Remove(string path);

    [CanonicalApi("PythonSharp.System.IO.FileOperations.RenameEntry")]
    [InlineTemplate("_py_os.rename({0}, {1})")]
    public static extern void Rename(string sourcePath, string destinationPath);
}

[SurfaceLevel(3)]
[MapsTo("_py_shutil")]
public static primitive class Shutil
{
    [CanonicalApi("PythonSharp.System.IO.FileOperations.CopyFileWithMetadata")]
    [InlineTemplate("_py_shutil.copy2({0}, {1})")]
    public static extern string Copy2(string sourcePath, string destinationPath);

    [CanonicalApi("PythonSharp.System.IO.DirectoryOperations.CopyDirectoryTreeRecursively")]
    [InlineTemplate("_py_shutil.copytree({0}, {1}, dirs_exist_ok={2})")]
    public static extern string CopyTree(string sourceDir, string destinationDir, bool dirsExistOk = true);

    [CanonicalApi("PythonSharp.System.IO.DirectoryOperations.DeleteDirectoryTreeRecursively")]
    [InlineTemplate("_py_shutil.rmtree({0}, ignore_errors={1})")]
    public static extern void RmTree(string directoryPath, bool ignoreErrors = false);

    [CanonicalApi("PythonSharp.System.IO.FileOperations.MoveEntry")]
    [InlineTemplate("_py_shutil.move({0}, {1})")]
    public static extern string Move(string sourcePath, string destinationPath);
}

```

### `stdlib/01_python_stdlib/os_shutil/03_io.enterprise.d.ps`

```csharp
namespace PythonSharp.System.IO;

using PythonSharp.Core;
extern using os as _py_os;
extern using shutil as _py_shutil;

[SurfaceLevel(1)]
public static primitive class EnvironmentVariables
{
    [InlineTemplate("_py_os.environ")]
    public static extern EnvironmentVariableMap Variables { get; }

    [InlineTemplate("_py_os.getenv({0}, {1})")]
    public static extern string? GetVariableOrDefault(string variableName, string? defaultValue = null);

    [InlineTemplate("_py_os.environ[{0}]")]
    public static extern string GetRequiredVariable(string variableName);
}

[SurfaceLevel(1)]
public static primitive class FilePath
{
    [InlineTemplate("_py_os.sep")]
    public static extern string DirectorySeparator { get; }

    [InlineTemplate("_py_os.path.join({0}, {1})")]
    public static extern string Combine(string firstSegment, string secondSegment);

    [InlineTemplate("_py_os.path.join({0}, {1}, {2})")]
    public static extern string CombineThree(string firstSegment, string secondSegment, string thirdSegment);

    [InlineTemplate("_py_os.path.abspath({0})")]
    public static extern string GetAbsolutePath(string relativeOrAnyPath);

    [InlineTemplate("_py_os.path.dirname({0})")]
    public static extern string GetDirectoryName(string filePath);

    [InlineTemplate("_py_os.path.basename({0})")]
    public static extern string GetFileName(string filePath);

    [InlineTemplate("_py_os.path.splitext({0})")]
    public static extern (string PathWithoutExtension, string Extension) SplitExtension(string filePath);
}

[SurfaceLevel(1)]
public static primitive class FileSystemEntry
{
    [InlineTemplate("_py_os.path.exists({0})")]
    public static extern bool ExistsAtPath(string targetPath);

    [InlineTemplate("_py_os.path.isfile({0})")]
    public static extern bool IsRegularFile(string targetPath);

    [InlineTemplate("_py_os.path.isdir({0})")]
    public static extern bool IsDirectory(string targetPath);
}

[SurfaceLevel(1)]
public static primitive class DirectoryOperations
{
    [InlineTemplate("_py_os.getcwd()")]
    public static extern string GetCurrentWorkingDirectory();

    [InlineTemplate("_py_os.listdir({0})")]
    public static extern List<string> ListEntryNames(string directoryPath = ".");

    [InlineTemplate("_py_os.makedirs({0}, exist_ok={1})")]
    public static extern void CreateDirectoryRecursive(string directoryPath, bool ignoreIfAlreadyExists = true);

    [InlineTemplate("_py_shutil.copytree({0}, {1}, dirs_exist_ok={2})")]
    public static extern string CopyDirectoryTreeRecursively(string sourceDirectoryPath, string destinationDirectoryPath, bool overwriteExistingDirectories = true);

    [InlineTemplate("_py_shutil.rmtree({0}, ignore_errors={1})")]
    public static extern void DeleteDirectoryTreeRecursively(string directoryPath, bool ignoreErrors = false);
}

[SurfaceLevel(1)]
public static primitive class FileOperations
{
    [InlineTemplate("_py_shutil.copy2({0}, {1})")]
    public static extern string CopyFileWithMetadata(string sourceFilePath, string destinationFilePath);

    [InlineTemplate("_py_shutil.move({0}, {1})")]
    public static extern string MoveEntry(string sourcePath, string destinationPath);

    [InlineTemplate("_py_os.rename({0}, {1})")]
    public static extern void RenameEntry(string currentPath, string newPath);

    [InlineTemplate("_py_os.remove({0})")]
    public static extern void DeleteFile(string filePath);
}

```

---

## 2. `sys` (Process Arguments, Standard Streams, Interpreter Version & Exit)

Provides Triple-Surface bindings for `sys.argv`, `sys.stdout`, `sys.stderr`, `sys.path`, `sys.platform`, and `sys.exit`.

### `stdlib/01_python_stdlib/sys/00_sys.primitives.d.ps`

```csharp
namespace PythonSharp.System.Runtime;

using PythonSharp.Core;
extern using sys as _py_sys;

[MapsTo("typing.TextIO")]
[RuntimeType("object")]
public primitive class TextOutputStream : IDisposable
{
    // --- Surface 1: Self-Documenting Enterprise Methods ---
    [MapsTo("write")]
    public extern int WriteRawText(string textContent);

    [MapsTo("flush")]
    public extern void FlushBuffer();

    [MapsTo("close")]
    public extern void Dispose();

    // --- Surface 3: C#-Standardized Methods ---
    [CanonicalApi("PythonSharp.System.Runtime.TextOutputStream.WriteRawText")]
    [MapsTo("write")]
    public extern int Write(string text);

    [CanonicalApi("PythonSharp.System.Runtime.TextOutputStream.FlushBuffer")]
    [MapsTo("flush")]
    public extern void Flush();

    // --- Surface 2: Raw Python snake_case Methods ---
    [CanonicalApi("PythonSharp.System.Runtime.TextOutputStream.WriteRawText", "Write")]
    [MapsTo("write")]
    public extern int write(string s);

    [CanonicalApi("PythonSharp.System.Runtime.TextOutputStream.FlushBuffer", "Flush")]
    [MapsTo("flush")]
    public extern void flush();
}

[MapsTo("sys.version_info")]
[RuntimeType("tuple")]
public primitive struct PythonVersionInfo
{
    [InlineTemplate("int({self}.major)")]
    public extern int MajorVersion { get; }

    [CanonicalApi("PythonSharp.System.Runtime.PythonVersionInfo.MajorVersion")]
    [InlineTemplate("int({self}.major)")]
    public extern int Major { get; }

    [CanonicalApi("PythonSharp.System.Runtime.PythonVersionInfo.MajorVersion", "Major")]
    [InlineTemplate("int({self}.major)")]
    public extern int major { get; }

    [InlineTemplate("int({self}.minor)")]
    public extern int MinorVersion { get; }

    [CanonicalApi("PythonSharp.System.Runtime.PythonVersionInfo.MinorVersion")]
    [InlineTemplate("int({self}.minor)")]
    public extern int Minor { get; }

    [CanonicalApi("PythonSharp.System.Runtime.PythonVersionInfo.MinorVersion", "Minor")]
    [InlineTemplate("int({self}.minor)")]
    public extern int minor { get; }

    [InlineTemplate("int({self}.micro)")]
    public extern int PatchVersion { get; }

    [CanonicalApi("PythonSharp.System.Runtime.PythonVersionInfo.PatchVersion")]
    [InlineTemplate("int({self}.micro)")]
    public extern int Micro { get; }

    [CanonicalApi("PythonSharp.System.Runtime.PythonVersionInfo.PatchVersion", "Micro")]
    [InlineTemplate("int({self}.micro)")]
    public extern int micro { get; }
}

```

### `stdlib/01_python_stdlib/sys/01_sys.raw.d.ps`

```csharp
namespace sys;

using PythonSharp.Core;
using PythonSharp.System.Runtime;
extern using sys as _py_sys;

[SurfaceLevel(2)]
[MapsTo("_py_sys")]
public static primitive class sys
{
    [CanonicalApi("PythonSharp.System.Runtime.ProcessContext.CommandLineArguments", "PythonSharp.Sys.Sys.Argv")]
    [InlineTemplate("_py_sys.argv")]
    public static extern List<string> argv { get; }

    [CanonicalApi("PythonSharp.System.Runtime.ProcessContext.ModuleSearchPaths", "PythonSharp.Sys.Sys.Path")]
    [InlineTemplate("_py_sys.path")]
    public static extern List<string> path { get; }

    [CanonicalApi("PythonSharp.System.Runtime.ProcessContext.OperatingSystemPlatform", "PythonSharp.Sys.Sys.Platform")]
    [InlineTemplate("_py_sys.platform")]
    public static extern string platform { get; }

    [CanonicalApi("PythonSharp.System.Runtime.ProcessContext.InterpreterVersionInfo", "PythonSharp.Sys.Sys.VersionInfo")]
    [InlineTemplate("_py_sys.version_info")]
    public static extern PythonVersionInfo version_info { get; }

    [CanonicalApi("PythonSharp.System.Runtime.StandardStreams.StandardOutput", "PythonSharp.Sys.Sys.Stdout")]
    [InlineTemplate("_py_sys.stdout")]
    public static extern TextOutputStream stdout { get; }

    [CanonicalApi("PythonSharp.System.Runtime.StandardStreams.StandardError", "PythonSharp.Sys.Sys.Stderr")]
    [InlineTemplate("_py_sys.stderr")]
    public static extern TextOutputStream stderr { get; }

    [CanonicalApi("PythonSharp.System.Runtime.ProcessContext.TerminateProcess", "PythonSharp.Sys.Sys.Exit")]
    [InlineTemplate("_py_sys.exit({0})")]
    public static extern void exit(int status = 0);
}

```

### `stdlib/01_python_stdlib/sys/02_sys.csharp.d.ps`

```csharp
namespace PythonSharp.Sys;

using PythonSharp.Core;
using PythonSharp.System.Runtime;
extern using sys as _py_sys;

[SurfaceLevel(3)]
[MapsTo("_py_sys")]
public static primitive class Sys
{
    [CanonicalApi("PythonSharp.System.Runtime.ProcessContext.CommandLineArguments")]
    [InlineTemplate("_py_sys.argv")]
    public static extern List<string> Argv { get; }

    [CanonicalApi("PythonSharp.System.Runtime.ProcessContext.ModuleSearchPaths")]
    [InlineTemplate("_py_sys.path")]
    public static extern List<string> Path { get; }

    [CanonicalApi("PythonSharp.System.Runtime.ProcessContext.OperatingSystemPlatform")]
    [InlineTemplate("_py_sys.platform")]
    public static extern string Platform { get; }

    [CanonicalApi("PythonSharp.System.Runtime.ProcessContext.InterpreterVersionInfo")]
    [InlineTemplate("_py_sys.version_info")]
    public static extern PythonVersionInfo VersionInfo { get; }

    [CanonicalApi("PythonSharp.System.Runtime.StandardStreams.StandardOutput")]
    [InlineTemplate("_py_sys.stdout")]
    public static extern TextOutputStream Stdout { get; }

    [CanonicalApi("PythonSharp.System.Runtime.StandardStreams.StandardError")]
    [InlineTemplate("_py_sys.stderr")]
    public static extern TextOutputStream Stderr { get; }

    [CanonicalApi("PythonSharp.System.Runtime.ProcessContext.TerminateProcess")]
    [InlineTemplate("_py_sys.exit({0})")]
    public static extern void Exit(int exitCode = 0);
}

```

### `stdlib/01_python_stdlib/sys/03_runtime.enterprise.d.ps`

```csharp
namespace PythonSharp.System.Runtime;

using PythonSharp.Core;
extern using sys as _py_sys;

[SurfaceLevel(1)]
public static primitive class ProcessContext
{
    [InlineTemplate("_py_sys.argv")]
    public static extern List<string> CommandLineArguments { get; }

    [InlineTemplate("_py_sys.path")]
    public static extern List<string> ModuleSearchPaths { get; }

    [InlineTemplate("_py_sys.platform")]
    public static extern string OperatingSystemPlatform { get; }

    [InlineTemplate("_py_sys.version_info")]
    public static extern PythonVersionInfo InterpreterVersionInfo { get; }

    [InlineTemplate("_py_sys.exit({0})")]
    public static extern void TerminateProcess(int exitStatusCode = 0);
}

[SurfaceLevel(1)]
public static primitive class StandardStreams
{
    [InlineTemplate("_py_sys.stdout")]
    public static extern TextOutputStream StandardOutput { get; }

    [InlineTemplate("_py_sys.stderr")]
    public static extern TextOutputStream StandardError { get; }
}

```

---

## 3. `json` (JSON Document Parsing & Formatted Serialization)

Maps `json.loads` and `json.dumps` across `json` (Surface 2), `PythonSharp.Json` (Surface 3), and `PythonSharp.Serialization.Json` (Surface 1).

### `stdlib/01_python_stdlib/json/00_json.primitives.d.ps`

```csharp
namespace PythonSharp.Serialization.Json;

using PythonSharp.Core;
extern using json as _py_json;

[MapsTo("dict")]
[RuntimeType("dict")]
public primitive class JsonDocumentObject : IEnumerable<KeyValuePair<string, object>>
{
    [InlineTemplate("{self}[{0}]")]
    public extern object this[string propertyName]
    {
        get;
        [InlineTemplate("{self}[{0}] = {value}")] set;
    }

    [MapsTo("get")]
    public extern object? GetPropertyOrDefault(string propertyName, object? defaultValue = null);

    [CanonicalApi("PythonSharp.Serialization.Json.JsonDocumentObject.GetPropertyOrDefault")]
    [MapsTo("get")]
    public extern object? Get(string key, object? defaultValue = null);

    [CanonicalApi("PythonSharp.Serialization.Json.JsonDocumentObject.GetPropertyOrDefault", "Get")]
    [MapsTo("get")]
    public extern object? get(string key, object? defaultValue = null);

    [InlineTemplate("({0} in {self})")]
    public extern bool HasProperty(string propertyName);

    [MapsTo("keys")]
    public extern IEnumerable<string> PropertyNames();
}

```

### `stdlib/01_python_stdlib/json/01_json.raw.d.ps`

```csharp
namespace json;

using PythonSharp.Core;
using PythonSharp.Serialization.Json;
extern using json as _py_json;

[SurfaceLevel(2)]
[MapsTo("_py_json")]
public static primitive class json
{
    [CanonicalApi("PythonSharp.Serialization.Json.JsonSerializer.DeserializeFromString", "PythonSharp.Json.Json.Loads")]
    [InlineTemplate("_py_json.loads({0})")]
    public static extern JsonDocumentObject loads(string s);

    [CanonicalApi("PythonSharp.Serialization.Json.JsonSerializer.DeserializeTypedFromString", "PythonSharp.Json.Json.Loads")]
    [InlineTemplate("_py_json.loads({0})")]
    public static extern T loads<T>(string s);

    [CanonicalApi("PythonSharp.Serialization.Json.JsonSerializer.SerializeToString", "PythonSharp.Json.Json.Dumps")]
    [InlineTemplate("_py_json.dumps({0})")]
    public static extern string dumps(object obj);

    [CanonicalApi("PythonSharp.Serialization.Json.JsonSerializer.SerializeFormatted", "PythonSharp.Json.Json.Dumps")]
    [InlineTemplate("_py_json.dumps({0}, indent={1}, sort_keys={2})")]
    public static extern string dumps(object obj, int indent, bool sort_keys = false);
}

```

### `stdlib/01_python_stdlib/json/02_json.csharp.d.ps`

```csharp
namespace PythonSharp.Json;

using PythonSharp.Core;
using PythonSharp.Serialization.Json;
extern using json as _py_json;

[SurfaceLevel(3)]
[MapsTo("_py_json")]
public static primitive class Json
{
    [CanonicalApi("PythonSharp.Serialization.Json.JsonSerializer.DeserializeFromString")]
    [InlineTemplate("_py_json.loads({0})")]
    public static extern JsonDocumentObject Loads(string rawJson);

    [CanonicalApi("PythonSharp.Serialization.Json.JsonSerializer.DeserializeTypedFromString")]
    [InlineTemplate("_py_json.loads({0})")]
    public static extern T Loads<T>(string rawJson);

    [CanonicalApi("PythonSharp.Serialization.Json.JsonSerializer.SerializeToString")]
    [InlineTemplate("_py_json.dumps({0})")]
    public static extern string Dumps(object value);

    [CanonicalApi("PythonSharp.Serialization.Json.JsonSerializer.SerializeFormatted")]
    [InlineTemplate("_py_json.dumps({0}, indent={1}, sort_keys={2})")]
    public static extern string Dumps(object value, int indent, bool sortKeys = false);
}

```

### `stdlib/01_python_stdlib/json/03_serialization.enterprise.d.ps`

```csharp
namespace PythonSharp.Serialization.Json;

using PythonSharp.Core;
extern using json as _py_json;

[SurfaceLevel(1)]
[MapsTo("_py_json")]
public static primitive class JsonSerializer
{
    [InlineTemplate("_py_json.loads({0})")]
    public static extern JsonDocumentObject DeserializeFromString(string jsonText);

    [InlineTemplate("_py_json.loads({0})")]
    public static extern T DeserializeTypedFromString<T>(string jsonText);

    [InlineTemplate("_py_json.dumps({0})")]
    public static extern string SerializeToString(object payload);

    [InlineTemplate("_py_json.dumps({0}, indent={1}, sort_keys={2})")]
    public static extern string SerializeFormatted(object payload, int indentSpaces = 2, bool sortKeysAlphabetically = false);
}

```

---

## 4. `re` (Regular Expression Matching, Substitution & Compiled Patterns)

Maps `re.Match` and `re.Pattern` alongside `re` (Surface 2), `PythonSharp.Re` (Surface 3), and `PythonSharp.Text.RegularExpressions` (Surface 1).

### `stdlib/01_python_stdlib/re/00_re.primitives.d.ps`

```csharp
namespace PythonSharp.Text.RegularExpressions;

using PythonSharp.Core;
extern using re as _py_re;

[MapsTo("re.Match")]
[RuntimeType("re.Match")]
public primitive class RegexMatch
{
    // --- Surface 1: Self-Documenting Enterprise Methods ---
    [InlineTemplate("{self}.group({0})")]
    public extern string GetCapturedGroup(int groupIndex = 0);

    [MapsTo("groups")]
    public extern List<string> GetAllCapturedGroups();

    [MapsTo("span")]
    public extern (int StartIndex, int EndIndex) GetMatchSpan();

    // --- Surface 3: C#-Standardized Methods ---
    [CanonicalApi("PythonSharp.Text.RegularExpressions.RegexMatch.GetCapturedGroup")]
    [MapsTo("group")]
    public extern string Group(int index = 0);

    [CanonicalApi("PythonSharp.Text.RegularExpressions.RegexMatch.GetAllCapturedGroups")]
    [MapsTo("groups")]
    public extern List<string> Groups();

    [CanonicalApi("PythonSharp.Text.RegularExpressions.RegexMatch.GetMatchSpan")]
    [MapsTo("span")]
    public extern (int Start, int End) Span();

    // --- Surface 2: Raw Python snake_case Methods ---
    [CanonicalApi("PythonSharp.Text.RegularExpressions.RegexMatch.GetCapturedGroup", "Group")]
    [MapsTo("group")]
    public extern string @group(int index = 0);

    [CanonicalApi("PythonSharp.Text.RegularExpressions.RegexMatch.GetAllCapturedGroups", "Groups")]
    [MapsTo("groups")]
    public extern List<string> groups();

    [CanonicalApi("PythonSharp.Text.RegularExpressions.RegexMatch.GetMatchSpan", "Span")]
    [MapsTo("span")]
    public extern (int start, int end) span();
}

[MapsTo("re.Pattern")]
[RuntimeType("re.Pattern")]
public primitive class CompiledRegexPattern
{
    [MapsTo("search")]
    public extern RegexMatch? SearchFirstMatch(string inputText);

    [CanonicalApi("PythonSharp.Text.RegularExpressions.CompiledRegexPattern.SearchFirstMatch")]
    [MapsTo("search")]
    public extern RegexMatch? Search(string text);

    [CanonicalApi("PythonSharp.Text.RegularExpressions.CompiledRegexPattern.SearchFirstMatch", "Search")]
    [MapsTo("search")]
    public extern RegexMatch? search(string @string);

    [MapsTo("findall")]
    public extern List<string> FindAllMatches(string inputText);

    [CanonicalApi("PythonSharp.Text.RegularExpressions.CompiledRegexPattern.FindAllMatches")]
    [MapsTo("findall")]
    public extern List<string> FindAll(string text);

    [CanonicalApi("PythonSharp.Text.RegularExpressions.CompiledRegexPattern.FindAllMatches", "FindAll")]
    [MapsTo("findall")]
    public extern List<string> findall(string @string);

    [MapsTo("sub")]
    public extern string ReplaceMatches(string replacementText, string inputText);

    [CanonicalApi("PythonSharp.Text.RegularExpressions.CompiledRegexPattern.ReplaceMatches")]
    [MapsTo("sub")]
    public extern string Sub(string repl, string text);

    [CanonicalApi("PythonSharp.Text.RegularExpressions.CompiledRegexPattern.ReplaceMatches", "Sub")]
    [MapsTo("sub")]
    public extern string sub(string repl, string @string);
}

```

### `stdlib/01_python_stdlib/re/01_re.raw.d.ps`

```csharp
namespace re;

using PythonSharp.Core;
using PythonSharp.Text.RegularExpressions;
extern using re as _py_re;

[SurfaceLevel(2)]
[MapsTo("_py_re")]
public static primitive class re
{
    [CanonicalApi("PythonSharp.Text.RegularExpressions.RegexEngine.CompilePattern", "PythonSharp.Re.Re.Compile")]
    [InlineTemplate("_py_re.compile({0})")]
    public static extern CompiledRegexPattern compile(string pattern);

    [CanonicalApi("PythonSharp.Text.RegularExpressions.RegexEngine.MatchAtBeginning", "PythonSharp.Re.Re.Match")]
    [InlineTemplate("_py_re.match({0}, {1})")]
    public static extern RegexMatch? match(string pattern, string @string);

    [CanonicalApi("PythonSharp.Text.RegularExpressions.RegexEngine.SearchAnywhere", "PythonSharp.Re.Re.Search")]
    [InlineTemplate("_py_re.search({0}, {1})")]
    public static extern RegexMatch? search(string pattern, string @string);

    [CanonicalApi("PythonSharp.Text.RegularExpressions.RegexEngine.FindAllMatches", "PythonSharp.Re.Re.FindAll")]
    [InlineTemplate("_py_re.findall({0}, {1})")]
    public static extern List<string> findall(string pattern, string @string);

    [CanonicalApi("PythonSharp.Text.RegularExpressions.RegexEngine.ReplaceAllMatches", "PythonSharp.Re.Re.Sub")]
    [InlineTemplate("_py_re.sub({0}, {1}, {2})")]
    public static extern string sub(string pattern, string repl, string @string);

    [CanonicalApi("PythonSharp.Text.RegularExpressions.RegexEngine.SplitByPattern", "PythonSharp.Re.Re.Split")]
    [InlineTemplate("_py_re.split({0}, {1})")]
    public static extern List<string> split(string pattern, string @string);
}

```

### `stdlib/01_python_stdlib/re/02_re.csharp.d.ps`

```csharp
namespace PythonSharp.Re;

using PythonSharp.Core;
using PythonSharp.Text.RegularExpressions;
extern using re as _py_re;

[SurfaceLevel(3)]
[MapsTo("_py_re")]
public static primitive class Re
{
    [CanonicalApi("PythonSharp.Text.RegularExpressions.RegexEngine.CompilePattern")]
    [InlineTemplate("_py_re.compile({0})")]
    public static extern CompiledRegexPattern Compile(string pattern);

    [CanonicalApi("PythonSharp.Text.RegularExpressions.RegexEngine.MatchAtBeginning")]
    [InlineTemplate("_py_re.match({0}, {1})")]
    public static extern RegexMatch? Match(string pattern, string text);

    [CanonicalApi("PythonSharp.Text.RegularExpressions.RegexEngine.SearchAnywhere")]
    [InlineTemplate("_py_re.search({0}, {1})")]
    public static extern RegexMatch? Search(string pattern, string text);

    [CanonicalApi("PythonSharp.Text.RegularExpressions.RegexEngine.FindAllMatches")]
    [InlineTemplate("_py_re.findall({0}, {1})")]
    public static extern List<string> FindAll(string pattern, string text);

    [CanonicalApi("PythonSharp.Text.RegularExpressions.RegexEngine.ReplaceAllMatches")]
    [InlineTemplate("_py_re.sub({0}, {1}, {2})")]
    public static extern string Sub(string pattern, string replacement, string text);

    [CanonicalApi("PythonSharp.Text.RegularExpressions.RegexEngine.SplitByPattern")]
    [InlineTemplate("_py_re.split({0}, {1})")]
    public static extern List<string> Split(string pattern, string text);
}

```

### `stdlib/01_python_stdlib/re/03_regex.enterprise.d.ps`

```csharp
namespace PythonSharp.Text.RegularExpressions;

using PythonSharp.Core;
extern using re as _py_re;

[SurfaceLevel(1)]
[MapsTo("_py_re")]
public static primitive class RegexEngine
{
    [InlineTemplate("_py_re.compile({0})")]
    public static extern CompiledRegexPattern CompilePattern(string regexPattern);

    [InlineTemplate("_py_re.match({0}, {1})")]
    public static extern RegexMatch? MatchAtBeginning(string regexPattern, string inputText);

    [InlineTemplate("_py_re.search({0}, {1})")]
    public static extern RegexMatch? SearchAnywhere(string regexPattern, string inputText);

    [InlineTemplate("_py_re.findall({0}, {1})")]
    public static extern List<string> FindAllMatches(string regexPattern, string inputText);

    [InlineTemplate("_py_re.sub({0}, {1}, {2})")]
    public static extern string ReplaceAllMatches(string regexPattern, string replacementText, string inputText);

    [InlineTemplate("_py_re.split({0}, {1})")]
    public static extern List<string> SplitByPattern(string regexPattern, string inputText);
}

```

---

## 5. `time_datetime` (High-Resolution Clocks, Thread Sleep & UTC Timestamps)

Exposes `time.time()`, `time.perf_counter()`, `time.sleep()`, `datetime.datetime`, and `datetime.timedelta` across all three surfaces.

### `stdlib/01_python_stdlib/time_datetime/00_time.primitives.d.ps`

```csharp
namespace PythonSharp.System.Diagnostics;

using PythonSharp.Core;
extern using datetime as _py_dt;

[MapsTo("datetime.datetime")]
[RuntimeType("datetime.datetime")]
public primitive struct TimestampInstant
{
    [InlineTemplate("int({self}.year)")]
    public extern int Year { get; }

    [InlineTemplate("int({self}.month)")]
    public extern int Month { get; }

    [InlineTemplate("int({self}.day)")]
    public extern int Day { get; }

    // --- Surface 1: Self-Documenting Enterprise Methods ---
    [MapsTo("isoformat")]
    public extern string FormatAsIso8601();

    [MapsTo("timestamp")]
    public extern double ToUnixEpochSeconds();

    [MapsTo("strftime")]
    public extern string FormatWithPattern(string formatPattern);

    // --- Surface 3: C#-Standardized Methods ---
    [CanonicalApi("PythonSharp.System.Diagnostics.TimestampInstant.FormatAsIso8601")]
    [MapsTo("isoformat")]
    public extern string IsoFormat();

    [CanonicalApi("PythonSharp.System.Diagnostics.TimestampInstant.ToUnixEpochSeconds")]
    [MapsTo("timestamp")]
    public extern double Timestamp();

    [CanonicalApi("PythonSharp.System.Diagnostics.TimestampInstant.FormatWithPattern")]
    [MapsTo("strftime")]
    public extern string StrfTime(string format);

    // --- Surface 2: Raw Python snake_case Methods ---
    [CanonicalApi("PythonSharp.System.Diagnostics.TimestampInstant.FormatAsIso8601", "IsoFormat")]
    [MapsTo("isoformat")]
    public extern string isoformat();

    [CanonicalApi("PythonSharp.System.Diagnostics.TimestampInstant.ToUnixEpochSeconds", "Timestamp")]
    [MapsTo("timestamp")]
    public extern double timestamp();

    [CanonicalApi("PythonSharp.System.Diagnostics.TimestampInstant.FormatWithPattern", "StrfTime")]
    [MapsTo("strftime")]
    public extern string strftime(string format);
}

[MapsTo("datetime.timedelta")]
[RuntimeType("datetime.timedelta")]
public primitive struct DurationDelta
{
    [MapsTo("total_seconds")]
    public extern double TotalSeconds();

    [CanonicalApi("PythonSharp.System.Diagnostics.DurationDelta.TotalSeconds", "TotalSeconds")]
    [MapsTo("total_seconds")]
    public extern double total_seconds();
}

```

### `stdlib/01_python_stdlib/time_datetime/01_time.raw.d.ps`

```csharp
namespace time;

using PythonSharp.Core;
using PythonSharp.System.Diagnostics;
extern using time as _py_time;
extern using datetime as _py_dt;

[SurfaceLevel(2)]
[MapsTo("_py_time")]
public static primitive class time
{
    [CanonicalApi("PythonSharp.System.Diagnostics.SystemClock.GetUnixTimestampSeconds", "PythonSharp.Time.Time.NowEpoch")]
    [InlineTemplate("_py_time.time()")]
    public static extern double now_epoch();

    [CanonicalApi("PythonSharp.System.Diagnostics.SystemClock.GetHighResolutionSeconds", "PythonSharp.Time.Time.PerfCounter")]
    [InlineTemplate("_py_time.perf_counter()")]
    public static extern double perf_counter();

    [CanonicalApi("PythonSharp.System.Diagnostics.SystemClock.GetMonotonicSeconds", "PythonSharp.Time.Time.Monotonic")]
    [InlineTemplate("_py_time.monotonic()")]
    public static extern double monotonic();

    [CanonicalApi("PythonSharp.System.Diagnostics.SystemClock.SleepCurrentThreadSeconds", "PythonSharp.Time.Time.Sleep")]
    [InlineTemplate("_py_time.sleep({0})")]
    public static extern void sleep(double seconds);
}

[SurfaceLevel(2)]
[MapsTo("_py_dt.datetime")]
public static primitive class datetime
{
    [CanonicalApi("PythonSharp.System.Diagnostics.SystemClock.GetCurrentLocalTimestamp", "PythonSharp.Time.DateTimeClock.Now")]
    [InlineTemplate("_py_dt.datetime.now()")]
    public static extern TimestampInstant now();

    [CanonicalApi("PythonSharp.System.Diagnostics.SystemClock.GetCurrentUtcTimestamp", "PythonSharp.Time.DateTimeClock.UtcNow")]
    [InlineTemplate("_py_dt.datetime.now(_py_dt.timezone.utc)")]
    public static extern TimestampInstant utcnow();

    [CanonicalApi("PythonSharp.System.Diagnostics.SystemClock.ParseIso8601Timestamp", "PythonSharp.Time.DateTimeClock.FromIsoFormat")]
    [InlineTemplate("_py_dt.datetime.fromisoformat({0})")]
    public static extern TimestampInstant fromisoformat(string date_string);
}

```

### `stdlib/01_python_stdlib/time_datetime/02_time.csharp.d.ps`

```csharp
namespace PythonSharp.Time;

using PythonSharp.Core;
using PythonSharp.System.Diagnostics;
extern using time as _py_time;
extern using datetime as _py_dt;

[SurfaceLevel(3)]
[MapsTo("_py_time")]
public static primitive class Time
{
    [CanonicalApi("PythonSharp.System.Diagnostics.SystemClock.GetUnixTimestampSeconds")]
    [InlineTemplate("_py_time.time()")]
    public static extern double NowEpoch();

    [CanonicalApi("PythonSharp.System.Diagnostics.SystemClock.GetHighResolutionSeconds")]
    [InlineTemplate("_py_time.perf_counter()")]
    public static extern double PerfCounter();

    [CanonicalApi("PythonSharp.System.Diagnostics.SystemClock.GetMonotonicSeconds")]
    [InlineTemplate("_py_time.monotonic()")]
    public static extern double Monotonic();

    [CanonicalApi("PythonSharp.System.Diagnostics.SystemClock.SleepCurrentThreadSeconds")]
    [InlineTemplate("_py_time.sleep({0})")]
    public static extern void Sleep(double seconds);
}

[SurfaceLevel(3)]
[MapsTo("_py_dt.datetime")]
public static primitive class DateTimeClock
{
    [CanonicalApi("PythonSharp.System.Diagnostics.SystemClock.GetCurrentLocalTimestamp")]
    [InlineTemplate("_py_dt.datetime.now()")]
    public static extern TimestampInstant Now();

    [CanonicalApi("PythonSharp.System.Diagnostics.SystemClock.GetCurrentUtcTimestamp")]
    [InlineTemplate("_py_dt.datetime.now(_py_dt.timezone.utc)")]
    public static extern TimestampInstant UtcNow();

    [CanonicalApi("PythonSharp.System.Diagnostics.SystemClock.ParseIso8601Timestamp")]
    [InlineTemplate("_py_dt.datetime.fromisoformat({0})")]
    public static extern TimestampInstant FromIsoFormat(string isoString);
}

```

### `stdlib/01_python_stdlib/time_datetime/03_clock.enterprise.d.ps`

```csharp
namespace PythonSharp.System.Diagnostics;

using PythonSharp.Core;
extern using time as _py_time;
extern using datetime as _py_dt;

[SurfaceLevel(1)]
public static primitive class SystemClock
{
    [InlineTemplate("_py_time.time()")]
    public static extern double GetUnixTimestampSeconds();

    [InlineTemplate("_py_time.perf_counter()")]
    public static extern double GetHighResolutionSeconds();

    [InlineTemplate("_py_time.monotonic()")]
    public static extern double GetMonotonicSeconds();

    [InlineTemplate("_py_time.sleep({0})")]
    public static extern void SleepCurrentThreadSeconds(double durationSeconds);

    [InlineTemplate("_py_dt.datetime.now()")]
    public static extern TimestampInstant GetCurrentLocalTimestamp();

    [InlineTemplate("_py_dt.datetime.now(_py_dt.timezone.utc)")]
    public static extern TimestampInstant GetCurrentUtcTimestamp();

    [InlineTemplate("_py_dt.datetime.fromisoformat({0})")]
    public static extern TimestampInstant ParseIso8601Timestamp(string isoTimestampString);

    [InlineTemplate("_py_dt.timedelta(seconds={0})")]
    public static extern DurationDelta CreateDurationFromSeconds(double seconds);
}

```

---

## 6. `logging` (Structured Application Logging & Traceback Formatting)

Maps `logging.Logger`, `logging.getLogger`, `logging.basicConfig`, and `traceback.format_exc` across `logging` (Surface 2), `PythonSharp.Logging` (Surface 3), and `PythonSharp.Diagnostics.Logging` (Surface 1).

### `stdlib/01_python_stdlib/logging/00_logging.primitives.d.ps`

```csharp
namespace PythonSharp.Diagnostics.Logging;

using PythonSharp.Core;
extern using logging as _py_logging;

[MapsTo("logging.Logger")]
[RuntimeType("logging.Logger")]
public primitive class ApplicationLogger
{
    // --- Surface 1: Self-Documenting Enterprise Methods ---
    [MapsTo("debug")]
    public extern void LogDebugMessage(string message);

    [MapsTo("info")]
    public extern void LogInformationMessage(string message);

    [MapsTo("warning")]
    public extern void LogWarningMessage(string message);

    [MapsTo("error")]
    public extern void LogErrorMessage(string message);

    [MapsTo("critical")]
    public extern void LogCriticalMessage(string message);

    [MapsTo("exception")]
    public extern void LogExceptionWithTraceback(string message);

    [MapsTo("setLevel")]
    public extern void SetMinimumLogLevel(int severityLevel);

    // --- Surface 3: C#-Standardized Methods ---
    [CanonicalApi("PythonSharp.Diagnostics.Logging.ApplicationLogger.LogDebugMessage")]
    [MapsTo("debug")]
    public extern void Debug(string message);

    [CanonicalApi("PythonSharp.Diagnostics.Logging.ApplicationLogger.LogInformationMessage")]
    [MapsTo("info")]
    public extern void Info(string message);

    [CanonicalApi("PythonSharp.Diagnostics.Logging.ApplicationLogger.LogWarningMessage")]
    [MapsTo("warning")]
    public extern void Warning(string message);

    [CanonicalApi("PythonSharp.Diagnostics.Logging.ApplicationLogger.LogErrorMessage")]
    [MapsTo("error")]
    public extern void Error(string message);

    [CanonicalApi("PythonSharp.Diagnostics.Logging.ApplicationLogger.LogCriticalMessage")]
    [MapsTo("critical")]
    public extern void Critical(string message);

    [CanonicalApi("PythonSharp.Diagnostics.Logging.ApplicationLogger.LogExceptionWithTraceback")]
    [MapsTo("exception")]
    public extern void Exception(string message);

    [CanonicalApi("PythonSharp.Diagnostics.Logging.ApplicationLogger.SetMinimumLogLevel")]
    [MapsTo("setLevel")]
    public extern void SetLevel(int level);

    // --- Surface 2: Raw Python snake_case Methods ---
    [CanonicalApi("PythonSharp.Diagnostics.Logging.ApplicationLogger.LogDebugMessage", "Debug")]
    [MapsTo("debug")]
    public extern void debug(string msg);

    [CanonicalApi("PythonSharp.Diagnostics.Logging.ApplicationLogger.LogInformationMessage", "Info")]
    [MapsTo("info")]
    public extern void info(string msg);

    [CanonicalApi("PythonSharp.Diagnostics.Logging.ApplicationLogger.LogWarningMessage", "Warning")]
    [MapsTo("warning")]
    public extern void warning(string msg);

    [CanonicalApi("PythonSharp.Diagnostics.Logging.ApplicationLogger.LogErrorMessage", "Error")]
    [MapsTo("error")]
    public extern void error(string msg);

    [CanonicalApi("PythonSharp.Diagnostics.Logging.ApplicationLogger.LogCriticalMessage", "Critical")]
    [MapsTo("critical")]
    public extern void critical(string msg);

    [CanonicalApi("PythonSharp.Diagnostics.Logging.ApplicationLogger.LogExceptionWithTraceback", "Exception")]
    [MapsTo("exception")]
    public extern void exception(string msg);
}

```

### `stdlib/01_python_stdlib/logging/01_logging.raw.d.ps`

```csharp
namespace logging;

using PythonSharp.Core;
using PythonSharp.Diagnostics.Logging;
extern using logging as _py_logging;
extern using traceback as _py_tb;

[SurfaceLevel(2)]
[MapsTo("_py_logging")]
public static primitive class logging
{
    [InlineTemplate("_py_logging.DEBUG")]
    public static extern int DEBUG { get; }

    [InlineTemplate("_py_logging.INFO")]
    public static extern int INFO { get; }

    [InlineTemplate("_py_logging.WARNING")]
    public static extern int WARNING { get; }

    [InlineTemplate("_py_logging.ERROR")]
    public static extern int ERROR { get; }

    [CanonicalApi("PythonSharp.Diagnostics.Logging.LoggerFactory.GetNamedLogger", "PythonSharp.Logging.Logging.GetLogger")]
    [InlineTemplate("_py_logging.getLogger({0})")]
    public static extern ApplicationLogger getLogger(string? name = null);

    [CanonicalApi("PythonSharp.Diagnostics.Logging.LoggerFactory.ConfigureRootLogger", "PythonSharp.Logging.Logging.BasicConfig")]
    [InlineTemplate("_py_logging.basicConfig(level={0})")]
    public static extern void basicConfig(int level = 20);
}

[SurfaceLevel(2)]
[MapsTo("_py_tb")]
public static primitive class traceback
{
    [CanonicalApi("PythonSharp.Diagnostics.Logging.TracebackFormatter.FormatCurrentExceptionTraceback", "PythonSharp.Logging.Traceback.FormatExc")]
    [InlineTemplate("_py_tb.format_exc()")]
    public static extern string format_exc();
}

```

### `stdlib/01_python_stdlib/logging/02_logging.csharp.d.ps`

```csharp
namespace PythonSharp.Logging;

using PythonSharp.Core;
using PythonSharp.Diagnostics.Logging;
extern using logging as _py_logging;
extern using traceback as _py_tb;

[SurfaceLevel(3)]
[MapsTo("_py_logging")]
public static primitive class Logging
{
    [InlineTemplate("_py_logging.DEBUG")]
    public static extern int DebugLevel { get; }

    [InlineTemplate("_py_logging.INFO")]
    public static extern int InfoLevel { get; }

    [InlineTemplate("_py_logging.WARNING")]
    public static extern int WarningLevel { get; }

    [InlineTemplate("_py_logging.ERROR")]
    public static extern int ErrorLevel { get; }

    [CanonicalApi("PythonSharp.Diagnostics.Logging.LoggerFactory.GetNamedLogger")]
    [InlineTemplate("_py_logging.getLogger({0})")]
    public static extern ApplicationLogger GetLogger(string? name = null);

    [CanonicalApi("PythonSharp.Diagnostics.Logging.LoggerFactory.ConfigureRootLogger")]
    [InlineTemplate("_py_logging.basicConfig(level={0})")]
    public static extern void BasicConfig(int level = 20);
}

[SurfaceLevel(3)]
[MapsTo("_py_tb")]
public static primitive class Traceback
{
    [CanonicalApi("PythonSharp.Diagnostics.Logging.TracebackFormatter.FormatCurrentExceptionTraceback")]
    [InlineTemplate("_py_tb.format_exc()")]
    public static extern string FormatExc();
}

```

### `stdlib/01_python_stdlib/logging/03_logging.enterprise.d.ps`

```csharp
namespace PythonSharp.Diagnostics.Logging;

using PythonSharp.Core;
extern using logging as _py_logging;
extern using traceback as _py_tb;

[SurfaceLevel(1)]
[MapsTo("_py_logging")]
public static primitive class LoggerFactory
{
    [InlineTemplate("_py_logging.getLogger({0})")]
    public static extern ApplicationLogger GetNamedLogger(string? categoryName = null);

    [InlineTemplate("_py_logging.basicConfig(level={0})")]
    public static extern void ConfigureRootLogger(int minimumSeverityLevel = 20);
}

[SurfaceLevel(1)]
[MapsTo("_py_tb")]
public static primitive class TracebackFormatter
{
    [InlineTemplate("_py_tb.format_exc()")]
    public static extern string FormatCurrentExceptionTraceback();
}

```

---

## 7. `urllib_http` (HTTP Requests, URL Parsing & Query Encoding)

Covers the `urllib_http` standard library bundle from Milestone U2 (`urllib.request.urlopen`, `urllib.parse.urlencode`, `urllib.parse.urljoin`).

### `stdlib/01_python_stdlib/urllib_http/00_urllib.primitives.d.ps`

```csharp
namespace PythonSharp.Net.Http;

using PythonSharp.Core;
extern using urllib.request as _py_urllib_req;

[MapsTo("http.client.HTTPResponse")]
[RuntimeType("object")]
public primitive class HttpResponseStream : IDisposable
{
    [InlineTemplate("int({self}.status)")]
    public extern int StatusCode { get; }

    [CanonicalApi("PythonSharp.Net.Http.HttpResponseStream.StatusCode")]
    [InlineTemplate("int({self}.status)")]
    public extern int Status { get; }

    [CanonicalApi("PythonSharp.Net.Http.HttpResponseStream.StatusCode", "Status")]
    [InlineTemplate("int({self}.status)")]
    public extern int status { get; }

    // --- Surface 1: Self-Documenting Enterprise Methods ---
    [InlineTemplate("{self}.read().decode('utf-8')")]
    public extern string ReadResponseTextUtf8();

    [MapsTo("read")]
    public extern Bytes ReadResponseBytes();

    [MapsTo("close")]
    public extern void Dispose();

    // --- Surface 3: C#-Standardized Methods ---
    [CanonicalApi("PythonSharp.Net.Http.HttpResponseStream.ReadResponseTextUtf8")]
    [InlineTemplate("{self}.read().decode('utf-8')")]
    public extern string ReadText();

    [CanonicalApi("PythonSharp.Net.Http.HttpResponseStream.ReadResponseBytes")]
    [MapsTo("read")]
    public extern Bytes Read();

    // --- Surface 2: Raw Python snake_case Methods ---
    [CanonicalApi("PythonSharp.Net.Http.HttpResponseStream.ReadResponseBytes", "Read")]
    [MapsTo("read")]
    public extern Bytes read();
}

```

### `stdlib/01_python_stdlib/urllib_http/01_urllib.raw.d.ps`

```csharp
namespace urllib;

using PythonSharp.Core;
using PythonSharp.Net.Http;
extern using urllib.request as _py_req;
extern using urllib.parse as _py_parse;

[SurfaceLevel(2)]
[MapsTo("_py_req")]
public static primitive class RequestModule
{
    [CanonicalApi("PythonSharp.Net.Http.HttpClientOperations.OpenUrlStream", "PythonSharp.Urllib.Urllib.Request.UrlOpen")]
    [InlineTemplate("_py_req.urlopen({0}, timeout={1})")]
    public static extern HttpResponseStream urlopen(string url, double timeout = 30.0);
}

[SurfaceLevel(2)]
[MapsTo("_py_parse")]
public static primitive class ParseModule
{
    [CanonicalApi("PythonSharp.Net.Http.UrlEncodingOperations.EncodeQueryParameters", "PythonSharp.Urllib.Urllib.Parse.UrlEncode")]
    [InlineTemplate("_py_parse.urlencode({0})")]
    public static extern string urlencode(Dict<string, string> query);

    [CanonicalApi("PythonSharp.Net.Http.UrlEncodingOperations.CombineBaseAndRelativeUrl", "PythonSharp.Urllib.Urllib.Parse.UrlJoin")]
    [InlineTemplate("_py_parse.urljoin({0}, {1})")]
    public static extern string urljoin(string @base, string url);
}

[SurfaceLevel(2)]
public static primitive class urllib
{
    [InlineTemplate("_py_req")]
    public static extern RequestModule request { get; }

    [InlineTemplate("_py_parse")]
    public static extern ParseModule parse { get; }
}

```

### `stdlib/01_python_stdlib/urllib_http/02_urllib.csharp.d.ps`

```csharp
namespace PythonSharp.Urllib;

using PythonSharp.Core;
using PythonSharp.Net.Http;
extern using urllib.request as _py_req;
extern using urllib.parse as _py_parse;

[SurfaceLevel(3)]
[MapsTo("_py_req")]
public static primitive class UrllibRequestModule
{
    [CanonicalApi("PythonSharp.Net.Http.HttpClientOperations.OpenUrlStream")]
    [InlineTemplate("_py_req.urlopen({0}, timeout={1})")]
    public static extern HttpResponseStream UrlOpen(string url, double timeoutSeconds = 30.0);
}

[SurfaceLevel(3)]
[MapsTo("_py_parse")]
public static primitive class UrllibParseModule
{
    [CanonicalApi("PythonSharp.Net.Http.UrlEncodingOperations.EncodeQueryParameters")]
    [InlineTemplate("_py_parse.urlencode({0})")]
    public static extern string UrlEncode(Dict<string, string> queryParameters);

    [CanonicalApi("PythonSharp.Net.Http.UrlEncodingOperations.CombineBaseAndRelativeUrl")]
    [InlineTemplate("_py_parse.urljoin({0}, {1})")]
    public static extern string UrlJoin(string baseUrl, string relativeUrl);
}

[SurfaceLevel(3)]
public static primitive class Urllib
{
    [InlineTemplate("_py_req")]
    public static extern UrllibRequestModule Request { get; }

    [InlineTemplate("_py_parse")]
    public static extern UrllibParseModule Parse { get; }
}

```

### `stdlib/01_python_stdlib/urllib_http/03_http.enterprise.d.ps`

```csharp
namespace PythonSharp.Net.Http;

using PythonSharp.Core;
extern using urllib.request as _py_req;
extern using urllib.parse as _py_parse;

[SurfaceLevel(1)]
[MapsTo("_py_req")]
public static primitive class HttpClientOperations
{
    [InlineTemplate("_py_req.urlopen({0}, timeout={1})")]
    public static extern HttpResponseStream OpenUrlStream(string targetUrl, double timeoutSeconds = 30.0);
}

[SurfaceLevel(1)]
[MapsTo("_py_parse")]
public static primitive class UrlEncodingOperations
{
    [InlineTemplate("_py_parse.urlencode({0})")]
    public static extern string EncodeQueryParameters(Dict<string, string> queryParameterMap);

    [InlineTemplate("_py_parse.urljoin({0}, {1})")]
    public static extern string CombineBaseAndRelativeUrl(string baseUrl, string relativePath);
}

```

---

## 8. `contextlib_subprocess` (Dynamic ExitStacks & External Process Execution)

Covers Target 18 (`contextlib.ExitStack` $\leftrightarrow$ `PythonSharp.Core.ResourceManagement`) and Milestone U2 (`subprocess.run`).

### `stdlib/01_python_stdlib/contextlib_subprocess/00_contextlib.primitives.d.ps`

```csharp
namespace PythonSharp.System.Processes;

using PythonSharp.Core;
extern using contextlib as _py_ctx;
extern using subprocess as _py_sub;

[MapsTo("contextlib.ExitStack")]
[RuntimeType("contextlib.ExitStack")]
public primitive class DisposableResourceStack : IDisposable
{
    // --- Surface 1: Self-Documenting Enterprise Methods ---
    [MapsTo("enter_context")]
    public extern T EnterManagedContext<T>(T contextManager);

    [MapsTo("close")]
    public extern void CloseAllResources();

    [MapsTo("close")]
    public extern void Dispose();

    // --- Surface 3: C#-Standardized Methods ---
    [CanonicalApi("PythonSharp.System.Processes.DisposableResourceStack.EnterManagedContext")]
    [MapsTo("enter_context")]
    public extern T EnterContext<T>(T cm);

    [CanonicalApi("PythonSharp.System.Processes.DisposableResourceStack.CloseAllResources")]
    [MapsTo("close")]
    public extern void Close();

    // --- Surface 2: Raw Python snake_case Methods ---
    [CanonicalApi("PythonSharp.System.Processes.DisposableResourceStack.EnterManagedContext", "EnterContext")]
    [MapsTo("enter_context")]
    public extern T enter_context<T>(T cm);

    [CanonicalApi("PythonSharp.System.Processes.DisposableResourceStack.CloseAllResources", "Close")]
    [MapsTo("close")]
    public extern void close();
}

[MapsTo("subprocess.CompletedProcess")]
[RuntimeType("subprocess.CompletedProcess")]
public primitive class CompletedProcessResult
{
    [InlineTemplate("int({self}.returncode)")]
    public extern int ExitStatusCode { get; }

    [CanonicalApi("PythonSharp.System.Processes.CompletedProcessResult.ExitStatusCode")]
    [InlineTemplate("int({self}.returncode)")]
    public extern int ReturnCode { get; }

    [CanonicalApi("PythonSharp.System.Processes.CompletedProcessResult.ExitStatusCode", "ReturnCode")]
    [InlineTemplate("int({self}.returncode)")]
    public extern int returncode { get; }

    [InlineTemplate("str({self}.stdout)")]
    public extern string StandardOutputText { get; }

    [CanonicalApi("PythonSharp.System.Processes.CompletedProcessResult.StandardOutputText")]
    [InlineTemplate("str({self}.stdout)")]
    public extern string Stdout { get; }

    [CanonicalApi("PythonSharp.System.Processes.CompletedProcessResult.StandardOutputText", "Stdout")]
    [InlineTemplate("str({self}.stdout)")]
    public extern string stdout { get; }

    [InlineTemplate("str({self}.stderr)")]
    public extern string StandardErrorText { get; }

    [CanonicalApi("PythonSharp.System.Processes.CompletedProcessResult.StandardErrorText")]
    [InlineTemplate("str({self}.stderr)")]
    public extern string Stderr { get; }

    [CanonicalApi("PythonSharp.System.Processes.CompletedProcessResult.StandardErrorText", "Stderr")]
    [InlineTemplate("str({self}.stderr)")]
    public extern string stderr { get; }
}

```

### `stdlib/01_python_stdlib/contextlib_subprocess/01_contextlib.raw.d.ps`

```csharp
namespace contextlib;

using PythonSharp.Core;
using PythonSharp.System.Processes;
extern using contextlib as _py_ctx;
extern using subprocess as _py_sub;

[SurfaceLevel(2)]
[MapsTo("_py_ctx")]
public static primitive class contextlib
{
    [CanonicalApi("PythonSharp.System.Processes.ResourceManagement.CreateExitStack", "PythonSharp.ContextLib.ContextLib.ExitStack")]
    [InlineTemplate("_py_ctx.ExitStack()")]
    public static extern DisposableResourceStack ExitStack();
}

[SurfaceLevel(2)]
[MapsTo("_py_sub")]
public static primitive class subprocess
{
    [CanonicalApi("PythonSharp.System.Processes.SubprocessRunner.RunCommandCapturingOutput", "PythonSharp.ContextLib.Subprocess.Run")]
    [InlineTemplate("_py_sub.run({0}, capture_output={1}, text={2}, check={3})")]
    public static extern CompletedProcessResult run(List<string> args, bool capture_output = true, bool text = true, bool check = false);
}

```

### `stdlib/01_python_stdlib/contextlib_subprocess/02_contextlib.csharp.d.ps`

```csharp
namespace PythonSharp.ContextLib;

using PythonSharp.Core;
using PythonSharp.System.Processes;
extern using contextlib as _py_ctx;
extern using subprocess as _py_sub;

[SurfaceLevel(3)]
[MapsTo("_py_ctx")]
public static primitive class ContextLib
{
    [CanonicalApi("PythonSharp.System.Processes.ResourceManagement.CreateExitStack")]
    [InlineTemplate("_py_ctx.ExitStack()")]
    public static extern DisposableResourceStack ExitStack();
}

[SurfaceLevel(3)]
[MapsTo("_py_sub")]
public static primitive class Subprocess
{
    [CanonicalApi("PythonSharp.System.Processes.SubprocessRunner.RunCommandCapturingOutput")]
    [InlineTemplate("_py_sub.run({0}, capture_output={1}, text={2}, check={3})")]
    public static extern CompletedProcessResult Run(List<string> arguments, bool captureOutput = true, bool text = true, bool check = false);
}

```

### `stdlib/01_python_stdlib/contextlib_subprocess/03_processes.enterprise.d.ps`

```csharp
namespace PythonSharp.System.Processes;

using PythonSharp.Core;
extern using contextlib as _py_ctx;
extern using subprocess as _py_sub;

[SurfaceLevel(1)]
[MapsTo("_py_ctx")]
public static primitive class ResourceManagement
{
    [InlineTemplate("_py_ctx.ExitStack()")]
    public static extern DisposableResourceStack CreateExitStack();
}

[SurfaceLevel(1)]
[MapsTo("_py_sub")]
public static primitive class SubprocessRunner
{
    [InlineTemplate("_py_sub.run({0}, capture_output={1}, text={2}, check={3})")]
    public static extern CompletedProcessResult RunCommandCapturingOutput(
        List<string> commandArguments,
        bool captureStandardStreams = true,
        bool decodeStreamsAsUtf8 = true,
        bool throwOnNonZeroExit = false);
}

```

---

## 9. `pathlib_hashlib_uuid` (Object-Oriented Paths, Cryptographic Digests & UUIDs)

Provides object-oriented `pathlib.Path`, `hashlib.sha256`, and `uuid.uuid4` used across modern Python data and web applications.

### `stdlib/01_python_stdlib/pathlib_hashlib_uuid/00_pathlib.primitives.d.ps`

```csharp
namespace PythonSharp.System.Security;

using PythonSharp.Core;
extern using pathlib as _py_pathlib;
extern using hashlib as _py_hashlib;

[MapsTo("pathlib.Path")]
[RuntimeType("pathlib.Path")]
public primitive class FileSystemPath
{
    [InlineTemplate("str({self}.name)")]
    public extern string FileName { get; }

    [CanonicalApi("PythonSharp.System.Security.FileSystemPath.FileName")]
    [InlineTemplate("str({self}.name)")]
    public extern string Name { get; }

    [CanonicalApi("PythonSharp.System.Security.FileSystemPath.FileName", "Name")]
    [InlineTemplate("str({self}.name)")]
    public extern string name { get; }

    [InlineTemplate("str({self}.suffix)")]
    public extern string FileExtension { get; }

    [CanonicalApi("PythonSharp.System.Security.FileSystemPath.FileExtension")]
    [InlineTemplate("str({self}.suffix)")]
    public extern string Suffix { get; }

    [CanonicalApi("PythonSharp.System.Security.FileSystemPath.FileExtension", "Suffix")]
    [InlineTemplate("str({self}.suffix)")]
    public extern string suffix { get; }

    [InlineTemplate("{self}.parent")]
    public extern FileSystemPath ParentDirectory { get; }

    [CanonicalApi("PythonSharp.System.Security.FileSystemPath.ParentDirectory")]
    [InlineTemplate("{self}.parent")]
    public extern FileSystemPath Parent { get; }

    [CanonicalApi("PythonSharp.System.Security.FileSystemPath.ParentDirectory", "Parent")]
    [InlineTemplate("{self}.parent")]
    public extern FileSystemPath parent { get; }

    // --- Surface 1: Self-Documenting Enterprise Methods ---
    [InlineTemplate("({self} / {0})")]
    public extern FileSystemPath JoinChildPath(string childSegment);

    [MapsTo("exists")]
    public extern bool ExistsOnDisk();

    [MapsTo("read_text")]
    public extern string ReadAllTextUtf8(string encoding = "utf-8");

    [MapsTo("write_text")]
    public extern int WriteAllTextUtf8(string content, string encoding = "utf-8");

    // --- Surface 3: C#-Standardized Methods ---
    [CanonicalApi("PythonSharp.System.Security.FileSystemPath.JoinChildPath")]
    [InlineTemplate("({self} / {0})")]
    public extern FileSystemPath JoinPath(string child);

    [CanonicalApi("PythonSharp.System.Security.FileSystemPath.ExistsOnDisk")]
    [MapsTo("exists")]
    public extern bool Exists();

    [CanonicalApi("PythonSharp.System.Security.FileSystemPath.ReadAllTextUtf8")]
    [MapsTo("read_text")]
    public extern string ReadText(string encoding = "utf-8");

    [CanonicalApi("PythonSharp.System.Security.FileSystemPath.WriteAllTextUtf8")]
    [MapsTo("write_text")]
    public extern int WriteText(string data, string encoding = "utf-8");

    // --- Surface 2: Raw Python snake_case Methods ---
    [CanonicalApi("PythonSharp.System.Security.FileSystemPath.ExistsOnDisk", "Exists")]
    [MapsTo("exists")]
    public extern bool exists();

    [CanonicalApi("PythonSharp.System.Security.FileSystemPath.ReadAllTextUtf8", "ReadText")]
    [MapsTo("read_text")]
    public extern string read_text(string encoding = "utf-8");

    [CanonicalApi("PythonSharp.System.Security.FileSystemPath.WriteAllTextUtf8", "WriteText")]
    [MapsTo("write_text")]
    public extern int write_text(string data, string encoding = "utf-8");
}

[MapsTo("hashlib._Hash")]
[RuntimeType("object")]
public primitive class CryptographicHashDigest
{
    [MapsTo("hexdigest")]
    public extern string ComputeHexadecimalDigest();

    [CanonicalApi("PythonSharp.System.Security.CryptographicHashDigest.ComputeHexadecimalDigest")]
    [MapsTo("hexdigest")]
    public extern string HexDigest();

    [CanonicalApi("PythonSharp.System.Security.CryptographicHashDigest.ComputeHexadecimalDigest", "HexDigest")]
    [MapsTo("hexdigest")]
    public extern string hexdigest();
}

```

### `stdlib/01_python_stdlib/pathlib_hashlib_uuid/01_pathlib.raw.d.ps`

```csharp
namespace pathlib;

using PythonSharp.Core;
using PythonSharp.System.Security;
extern using pathlib as _py_pathlib;
extern using hashlib as _py_hashlib;
extern using uuid as _py_uuid;

[SurfaceLevel(2)]
[MapsTo("_py_pathlib")]
public static primitive class pathlib
{
    [CanonicalApi("PythonSharp.System.Security.PathObjectFactory.CreateFileSystemPath", "PythonSharp.Pathlib.Pathlib.Path")]
    [InlineTemplate("_py_pathlib.Path({0})")]
    public static extern FileSystemPath Path(string pathSegment);
}

[SurfaceLevel(2)]
[MapsTo("_py_hashlib")]
public static primitive class hashlib
{
    [CanonicalApi("PythonSharp.System.Security.CryptographicHasher.ComputeSha256FromBytes", "PythonSharp.Pathlib.Hashlib.Sha256")]
    [InlineTemplate("_py_hashlib.sha256({0})")]
    public static extern CryptographicHashDigest sha256(Bytes data);
}

[SurfaceLevel(2)]
[MapsTo("_py_uuid")]
public static primitive class uuid
{
    [CanonicalApi("PythonSharp.System.Security.UniqueIdentifierGenerator.GenerateRandomUuidV4String", "PythonSharp.Pathlib.Uuid.Uuid4String")]
    [InlineTemplate("str(_py_uuid.uuid4())")]
    public static extern string uuid4();
}

```

### `stdlib/01_python_stdlib/pathlib_hashlib_uuid/02_pathlib.csharp.d.ps`

```csharp
namespace PythonSharp.Pathlib;

using PythonSharp.Core;
using PythonSharp.System.Security;
extern using pathlib as _py_pathlib;
extern using hashlib as _py_hashlib;
extern using uuid as _py_uuid;

[SurfaceLevel(3)]
[MapsTo("_py_pathlib")]
public static primitive class Pathlib
{
    [CanonicalApi("PythonSharp.System.Security.PathObjectFactory.CreateFileSystemPath")]
    [InlineTemplate("_py_pathlib.Path({0})")]
    public static extern FileSystemPath Path(string pathString);
}

[SurfaceLevel(3)]
[MapsTo("_py_hashlib")]
public static primitive class Hashlib
{
    [CanonicalApi("PythonSharp.System.Security.CryptographicHasher.ComputeSha256FromBytes")]
    [InlineTemplate("_py_hashlib.sha256({0})")]
    public static extern CryptographicHashDigest Sha256(Bytes data);
}

[SurfaceLevel(3)]
[MapsTo("_py_uuid")]
public static primitive class Uuid
{
    [CanonicalApi("PythonSharp.System.Security.UniqueIdentifierGenerator.GenerateRandomUuidV4String")]
    [InlineTemplate("str(_py_uuid.uuid4())")]
    public static extern string Uuid4String();
}

```

### `stdlib/01_python_stdlib/pathlib_hashlib_uuid/03_security.enterprise.d.ps`

```csharp
namespace PythonSharp.System.Security;

using PythonSharp.Core;
extern using pathlib as _py_pathlib;
extern using hashlib as _py_hashlib;
extern using uuid as _py_uuid;

[SurfaceLevel(1)]
[MapsTo("_py_pathlib")]
public static primitive class PathObjectFactory
{
    [InlineTemplate("_py_pathlib.Path({0})")]
    public static extern FileSystemPath CreateFileSystemPath(string pathString);
}

[SurfaceLevel(1)]
[MapsTo("_py_hashlib")]
public static primitive class CryptographicHasher
{
    [InlineTemplate("_py_hashlib.sha256({0})")]
    public static extern CryptographicHashDigest ComputeSha256FromBytes(Bytes payloadBytes);

    [InlineTemplate("_py_hashlib.sha256({0}.encode('utf-8')).hexdigest()")]
    public static extern string ComputeSha256HexFromString(string utf8Text);
}

[SurfaceLevel(1)]
[MapsTo("_py_uuid")]
public static primitive class UniqueIdentifierGenerator
{
    [InlineTemplate("str(_py_uuid.uuid4())")]
    public static extern string GenerateRandomUuidV4String();
}

```

---

Would you like me to also generate the modularized `stdlib/00_core/` six-file split (`00_attributes.d.ps`, `01_contracts.d.ps`, `02_primitives.d.ps`, `03_builtins.raw.d.ps`, `04_builtins.csharp.d.ps`, and `05_core.enterprise.d.ps`) so the entire `stdlib/` tree (`00_core/`, `01_python_stdlib/`, and `02_scientific_and_ai/`) is complete?
