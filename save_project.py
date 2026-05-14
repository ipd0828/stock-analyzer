# save_project.py
"""
Сохраняет архитектуру проекта и все Python скрипты в один файл
Только файлы самого проекта stock-analyzer, без внешних зависимостей
"""

import os
from pathlib import Path
from datetime import datetime
import sys


def should_include_file(filepath):
    """Проверяет, нужно ли включать файл"""
    # Исключаем только бинарные и временные файлы
    exclude_extensions = ['.pyc', '.pyo', '.so', '.dll', '.exe', '.pyd', '.bin']

    path = Path(filepath)

    # Проверяем расширения
    if path.suffix in exclude_extensions:
        return False

    # Включаем только нужные типы файлов
    return path.suffix in ['.py', '.txt', '.md', '.yaml', '.yml', '.json', '.sh', '.cfg', '.ini']


def should_include_dir(dirpath):
    """Проверяет, нужно ли включать директорию в структуру"""
    path = Path(dirpath)

    # Директории, которые полностью исключаем из структуры
    exclude_dirs = {
        # Виртуальное окружение и кэш
        '.venv', 'venv', 'env', '__pycache__', '.pytest_cache', '.mypy_cache',
        # Git и IDE
        '.git', '.idea', '.vscode', '.cursor',
        # Данные и логи
        'data', 'logs', 'models', 'checkpoints', 'outputs',
        # Внешние фреймворки
        'llama.cpp', 'unsloth', 'build', 'dist', 'node_modules',
        # Кэш huggingface
        '.cache', 'huggingface',
        # Документация и изображения
        'analysis_plots',
    }

    # Проверяем, не находится ли путь внутри исключённой директории
    for part in path.parts:
        if part in exclude_dirs:
            return False

    return True


def get_project_structure(directory, prefix=""):
    """Рекурсивно собирает структуру проекта"""
    structure = []

    try:
        items = sorted(directory.iterdir())
    except PermissionError:
        return structure

    # Фильтруем директории
    filtered_items = []
    for item in items:
        if item.is_dir():
            if should_include_dir(item):
                filtered_items.append(item)
        elif item.is_file():
            if should_include_file(item):
                filtered_items.append(item)

    for i, item in enumerate(filtered_items):
        is_last = i == len(filtered_items) - 1
        current_prefix = "└── " if is_last else "├── "
        next_prefix = "    " if is_last else "│   "

        if item.is_dir():
            structure.append(f"{prefix}{current_prefix}{item.name}/")
            structure.extend(get_project_structure(item, prefix + next_prefix))
        else:
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


def collect_project_files(directory):
    """Собирает все Python файлы только из папок проекта"""
    python_files = []

    # Только папки проекта
    project_dirs = ['src', 'scripts', 'config']

    for proj_dir in project_dirs:
        dir_path = Path(directory) / proj_dir
        if not dir_path.exists():
            continue

        for root, dirs, files in os.walk(dir_path):
            # Фильтруем директории
            dirs[:] = [d for d in dirs if should_include_dir(Path(root) / d)]

            for file in files:
                if file.endswith('.py'):
                    filepath = Path(root) / file
                    python_files.append(filepath)

    # Добавляем корневые файлы проекта
    root_files = [
        'save_project.py',
        'requirements.txt',
        'requirements_old.txt',
        'README.md',
    ]

    for root_file in root_files:
        filepath = Path(directory) / root_file
        if filepath.exists():
            if root_file.endswith('.py'):
                python_files.append(filepath)

    return sorted(python_files)


def collect_config_files(directory):
    """Собирает конфигурационные файлы"""
    config_files = []

    # Ищем в корне проекта
    root = Path(directory)
    for file in root.glob('*'):
        if file.is_file():
            if file.suffix in ['.yaml', '.yml', '.json', '.cfg', '.ini']:
                config_files.append(file)

    return sorted(config_files)


def save_project_archive(output_file="project_archive.txt"):
    """Сохраняет структуру и все скрипты проекта в один файл"""

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
        f.write("СОДЕРЖИМОЕ ФАЙЛОВ ПРОЕКТА\n")
        f.write("=" * 80 + "\n\n")

        # Собираем файлы проекта
        python_files = collect_project_files(project_root)
        config_files = collect_config_files(project_root)

        all_files = python_files + config_files

        for i, filepath in enumerate(all_files, 1):
            rel_path = filepath.relative_to(project_root)
            print(f"   [{i}/{len(all_files)}] {rel_path}")

            f.write(f"\n{'─' * 80}\n")
            f.write(f"ФАЙЛ: {rel_path}\n")
            f.write(f"{'─' * 80}\n\n")

            content = read_file_content(filepath)
            f.write(content)
            f.write("\n\n")

    print(f"\n✅ Архив сохранён: {output_path}")
    print(f"   Размер: {output_path.stat().st_size / 1024 / 1024:.2f} MB")
    print(f"   Всего файлов: {len(all_files)}")
    print(f"   Python файлов: {len(python_files)}")
    print(f"   Конфигурационных файлов: {len(config_files)}")

    return output_path


def main():
    """Основная функция"""
    print("\n" + "=" * 80)
    print("🚀 АРХИВАТОР ПРОЕКТА (только файлы проекта)")
    print("=" * 80)

    try:
        output_file = save_project_archive()
        print(f"\n📄 Архив содержит только файлы из папок:")
        print("   - src/")
        print("   - scripts/")
        print("   - config/")
        print("   - корневые файлы проекта")
        print(f"\n📂 Открой файл: {output_file}")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()