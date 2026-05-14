# save_project.py
"""
Сохраняет архитектуру проекта и все Python скрипты в один файл
"""

import os
from pathlib import Path
from datetime import datetime
import sys


def should_include_file(filepath):
    """Проверяет, нужно ли включать файл"""
    exclude_dirs = ['.venv', '__pycache__', '.git', '.idea', 'data', 'logs', 'models']
    exclude_extensions = ['.pyc', '.pyo', '.so', '.dll', '.exe']

    path = Path(filepath)

    # Проверяем исключённые директории
    for ex_dir in exclude_dirs:
        if ex_dir in path.parts:
            return False

    # Проверяем расширения
    if path.suffix in exclude_extensions:
        return False

    # Включаем Python файлы и конфиги
    return path.suffix in ['.py', '.txt', '.md', '.yaml', '.yml', '.json', '.sh', '.cfg', '.ini']


def get_project_structure(directory, prefix=""):
    """Рекурсивно собирает структуру проекта"""
    structure = []
    items = sorted(directory.iterdir())

    for i, item in enumerate(items):
        is_last = i == len(items) - 1
        current_prefix = "└── " if is_last else "├── "
        next_prefix = "    " if is_last else "│   "

        if item.is_dir():
            # Пропускаем исключённые директории
            if item.name in ['.venv', '__pycache__', '.git', '.idea', 'data']:
                continue
            structure.append(f"{prefix}{current_prefix}{item.name}/")
            structure.extend(get_project_structure(item, prefix + next_prefix))
        elif item.is_file():
            if should_include_file(item):
                structure.append(f"{prefix}{current_prefix}{item.name}")

    return structure


def read_file_content(filepath):
    """Читает содержимое файла"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with open(filepath, 'r', encoding='cp1251') as f:
                return f.read()
        except:
            return "[Не удалось прочитать файл (кодировка не поддерживается)]"
    except Exception as e:
        return f"[Ошибка чтения: {e}]"


def collect_all_python_files(directory):
    """Собирает все Python файлы в проекте"""
    python_files = []

    for root, dirs, files in os.walk(directory):
        # Пропускаем исключённые директории
        if '.venv' in dirs:
            dirs.remove('.venv')
        if '__pycache__' in dirs:
            dirs.remove('__pycache__')
        if '.git' in dirs:
            dirs.remove('.git')
        if 'data' in dirs:
            dirs.remove('data')

        for file in files:
            if file.endswith('.py'):
                filepath = Path(root) / file
                python_files.append(filepath)

    return sorted(python_files)


def save_project_archive(output_file="project_archive.txt"):
    """Сохраняет структуру и все скрипты в один файл"""

    project_root = Path(__file__).parent
    output_path = project_root / output_file

    print(f"📁 Сохранение архитектуры проекта в {output_file}...")
    print("=" * 80)

    with open(output_path, 'w', encoding='utf-8') as f:
        # Заголовок
        f.write("=" * 80 + "\n")
        f.write(f"АРХИВ ПРОЕКТА: stock-analyzer\n")
        f.write(f"Дата создания: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")

        # Структура проекта
        f.write("=" * 80 + "\n")
        f.write("СТРУКТУРА ПРОЕКТА\n")
        f.write("=" * 80 + "\n\n")

        structure = get_project_structure(project_root)
        for line in structure:
            f.write(line + "\n")

        f.write("\n\n")

        # Содержимое всех Python файлов
        f.write("=" * 80 + "\n")
        f.write("СОДЕРЖИМОЕ PYTHON ФАЙЛОВ\n")
        f.write("=" * 80 + "\n\n")

        python_files = collect_all_python_files(project_root)

        for i, filepath in enumerate(python_files, 1):
            rel_path = filepath.relative_to(project_root)
            print(f"   [{i}/{len(python_files)}] {rel_path}")

            f.write(f"\n{'─' * 80}\n")
            f.write(f"ФАЙЛ: {rel_path}\n")
            f.write(f"{'─' * 80}\n\n")

            content = read_file_content(filepath)
            f.write(content)
            f.write("\n\n")

    print(f"\n✅ Архив сохранён: {output_path}")
    print(f"   Размер: {output_path.stat().st_size / 1024 / 1024:.2f} MB")
    print(f"   Всего файлов: {len(python_files)}")

    return output_path


def main():
    """Основная функция"""
    print("\n" + "=" * 80)
    print("🚀 АРХИВАТОР ПРОЕКТА")
    print("=" * 80)

    try:
        output_file = save_project_archive()
        print(f"\n📄 Открой файл: {output_file}")
        print("   Для просмотра можно использовать:")
        print("   less project_archive.txt")
        print("   cat project_archive.txt | head -n 100")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()