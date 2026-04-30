from pathlib import Path


def build_markdown(py_files: list[Path]) -> str:
    sections: list[str] = []
    for py_file in py_files:
        content = py_file.read_text(encoding="utf-8")
        sections.append(f"```{py_file.resolve()}\n{content.rstrip()}\n```")
    return "\n\n".join(sections) + ("\n" if sections else "")


def is_ignored_dir_name(name: str) -> bool:
    return name.startswith(".") or name == "__pycache__"


def is_ignored_file_name(name: str) -> bool:
    return name.startswith(".")


def collect_target_dirs(src_dir: Path, output_dir: Path) -> list[Path]:
    target_dirs: list[Path] = []
    for item in sorted(src_dir.iterdir(), key=lambda path: path.name):
        if not item.is_dir():
            continue
        if item.resolve() == output_dir.resolve():
            continue
        if is_ignored_dir_name(item.name):
            continue
        if not any(item.glob("*.py")):
            continue
        target_dirs.append(item)
    return target_dirs


def collect_all_py_files(src_dir: Path) -> list[Path]:
    py_files: list[Path] = []
    for item in sorted(src_dir.rglob("*.py"), key=lambda path: str(path).lower()):
        if any(is_ignored_dir_name(part) for part in item.parts):
            continue
        py_files.append(item)
    return py_files


def build_tree_lines(root: Path, level: int = 0) -> list[str]:
    indent = "  " * level
    lines = [f"{indent}{root.name}/"]
    entries = sorted(root.iterdir(), key=lambda path: (not path.is_dir(), path.name.lower()))
    dirs = [entry for entry in entries if entry.is_dir() and not is_ignored_dir_name(entry.name)]
    files = [entry for entry in entries if entry.is_file() and not is_ignored_file_name(entry.name)]
    for directory in dirs:
        lines.extend(build_tree_lines(directory, level + 1))
    for index, file in enumerate(files):
        branch = "└──" if index == len(files) - 1 else "├──"
        lines.append(f"{'  ' * (level + 1)}{branch} {file.name}")
    return lines


def cleanup_old_outputs(output_dir: Path, keep_names: set[str]) -> None:
    for md_file in output_dir.glob("*.md"):
        if md_file.name in keep_names:
            continue
        md_file.unlink()


def main() -> None:
    output_dir = Path(__file__).resolve().parent
    src_dir = output_dir.parent
    keep_names = {"文件树.md", "统一代码.md"}
    cleanup_old_outputs(output_dir, keep_names)
    py_files = collect_all_py_files(src_dir)
    unified_code = build_markdown(py_files)
    unified_code_file = output_dir / "统一代码.md"
    unified_code_file.write_text(unified_code, encoding="utf-8")
    print(f"已生成: {unified_code_file}")
    tree_file = output_dir / "文件树.md"
    tree_content = "\n".join(build_tree_lines(src_dir)) + "\n"
    tree_file.write_text(tree_content, encoding="utf-8")
    print(f"已生成: {tree_file}")


if __name__ == "__main__":
    main()
