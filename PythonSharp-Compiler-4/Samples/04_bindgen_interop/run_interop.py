"""Sample 04: Native Python interop via ps-bindgen generated stubs."""

import sys
from pathlib import Path

# Add output directory and current directory to sys.path
base_dir = Path(__file__).parent
out_dir = base_dir / "dist"
sys.path.insert(0, str(base_dir))
sys.path.insert(0, str(out_dir))

from publishing import Article  # noqa: E402

if __name__ == "__main__":
    print("--- Creating PythonSharp Article Calling Native Python Code ---")
    title = "Why PythonSharp is Built for Fast Transpilation!"
    body = (
        "PythonSharp compiles modern C# statically into clean Python 3.11+ ASTs. "
        "With ps-bindgen, native Python libraries are called without any runtime overhead."
    )

    article = Article(title=title, body=body)

    slug = article.generate_slug()
    word_count = article.get_word_count()

    print(f"Title:       {title}")
    print(f"Slug:        {slug}")
    print(f"Word Count:  {word_count} words")
