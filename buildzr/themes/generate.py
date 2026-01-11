#!/usr/bin/env python3
"""
Generate Python theme modules from Structurizr theme JSON files.

Usage:
    # From URLs file
    python -m buildzr.themes.generate --urls-file buildzr/themes/themes.txt

    # From command line arguments
    python -m buildzr.themes.generate \\
        https://static.structurizr.com/themes/amazon-web-services-2023.01.31/theme.json \\
        https://static.structurizr.com/themes/google-cloud-platform-v1.5/theme.json

    # Or run directly
    ./buildzr/themes/generate.py --urls-file buildzr/themes/themes.txt
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple, Any
from urllib.request import urlopen


def fetch_theme(url: str) -> Dict[str, Any]:
    """Fetch theme JSON from URL."""
    with urlopen(url) as response:
        return json.loads(response.read().decode('utf-8')) # type: ignore[no-any-return]


def theme_name_to_module_name(name: str) -> str:
    """
    Convert theme name to Python module name.

    Examples:
        "Amazon Web Services" -> "aws"
        "Google Cloud Platform" -> "google_cloud"
        "Microsoft Azure" -> "azure"
        "Kubernetes" -> "kubernetes"
    """
    # Common mappings
    mappings = {
        'amazon web services': 'aws',
        'google cloud platform': 'google_cloud',
        'microsoft azure': 'azure',
        'kubernetes': 'kubernetes',
        'oracle cloud infrastructure': 'oracle_cloud',
    }

    lower_name = name.lower()
    if lower_name in mappings:
        return mappings[lower_name]

    # Fallback: convert to snake_case
    result = re.sub(r'[^a-zA-Z0-9]+', '_', name.lower())
    result = re.sub(r'_+', '_', result)
    return result.strip('_')


def theme_name_to_class_prefix(name: str) -> str:
    """
    Convert theme name to class name prefix.

    Examples:
        "Amazon Web Services" -> "AWS"
        "Google Cloud Platform" -> "GOOGLE_CLOUD"
        "Microsoft Azure" -> "AZURE"
    """
    module_name = theme_name_to_module_name(name)
    return module_name.upper()


def extract_version_from_url(url: str) -> str:
    """
    Extract version string from theme URL.

    Examples:
        ".../amazon-web-services-2023.01.31/theme.json" -> "2023_01_31"
        ".../google-cloud-platform-v1.5/theme.json" -> "V1_5"
        ".../kubernetes-v0.3/theme.json" -> "V0_3"
    """
    # Try date format: YYYY.MM.DD
    match = re.search(r'-(\d{4}\.\d{2}\.\d{2})/', url)
    if match:
        return match.group(1).replace('.', '_')

    # Try version format: vX.Y or vX.Y.Z
    match = re.search(r'-v([\d.]+)/', url)
    if match:
        return 'V' + match.group(1).replace('.', '_')

    # Fallback
    return 'LATEST'


def tag_to_identifier(tag: str, prefix_to_remove: str) -> str:
    """
    Convert theme tag to Python identifier.

    Examples:
        "Amazon Web Services - EC2 Instance" -> "EC2_INSTANCE"
        "Amazon Web Services - Route 53" -> "ROUTE_53"
        "Google Cloud Platform - Cloud Run" -> "CLOUD_RUN"
    """
    # Remove the common prefix (e.g., "Amazon Web Services - ")
    name = tag
    if prefix_to_remove and tag.startswith(prefix_to_remove):
        name = tag[len(prefix_to_remove):].strip()

    # Replace non-alphanumeric with underscore
    name = re.sub(r'[^a-zA-Z0-9]+', '_', name)

    # Remove consecutive underscores
    name = re.sub(r'_+', '_', name)

    # Uppercase and strip
    return name.upper().strip('_')


def resolve_icon_url(theme_url: str, icon_path: str) -> str:
    """
    Resolve relative icon path to full URL.

    Example:
        theme_url: "https://static.structurizr.com/themes/aws-2023.01.31/theme.json"
        icon_path: "Arch_Amazon-EC2_48.png"
        -> "https://static.structurizr.com/themes/aws-2023.01.31/Arch_Amazon-EC2_48.png"
    """
    if not icon_path:
        return ''

    # If already a full URL, return as-is
    if icon_path.startswith('http://') or icon_path.startswith('https://'):
        return icon_path

    # Get base URL (remove /theme.json)
    base_url = theme_url.rsplit('/', 1)[0]
    return f'{base_url}/{icon_path}'


def generate_theme_class(
    class_name: str,
    theme_url: str,
    theme_data: dict,
) -> List[str]:
    """Generate Python code for a single theme class."""
    lines = []

    theme_name = theme_data.get('name', 'Unknown')
    theme_description = theme_data.get('description', '')
    version = extract_version_from_url(theme_url)

    lines.append(f'class {class_name}:')
    lines.append(f'    """')
    lines.append(f'    {theme_name} theme (version {version.replace("_", ".")}).')
    if theme_description:
        lines.append(f'')
        lines.append(f'    {theme_description}')
    lines.append(f'    """')
    lines.append(f'')
    lines.append(f'    THEME_URL = "{theme_url}"')
    lines.append(f'    THEME_NAME = "{theme_name}"')
    lines.append(f'')

    # Determine prefix to remove from tags
    prefix_to_remove = f'{theme_name} - '

    # Track identifiers to handle duplicates
    seen_identifiers: Dict[str, int] = {}

    elements = theme_data.get('elements', [])
    for element in elements:
        tag = element.get('tag', '')
        if not tag:
            continue

        identifier = tag_to_identifier(tag, prefix_to_remove)
        if not identifier:
            continue

        # Handle duplicates by appending a number
        if identifier in seen_identifiers:
            seen_identifiers[identifier] += 1
            identifier = f'{identifier}_{seen_identifiers[identifier]}'
        else:
            seen_identifiers[identifier] = 1

        stroke = element.get('stroke', '')
        color = element.get('color', '')
        icon = resolve_icon_url(theme_url, element.get('icon', ''))

        lines.append(f'    {identifier} = ThemeElement(')
        lines.append(f'        tag="{tag}",')
        lines.append(f'        stroke="{stroke}",')
        lines.append(f'        color="{color}",')
        lines.append(f'        icon_url="{icon}",')
        lines.append(f'    )')
        lines.append(f'')

    # Add all_elements classmethod
    lines.append(f'    @classmethod')
    lines.append(f'    def all_elements(cls) -> list:')
    lines.append(f'        """Return all theme elements."""')
    lines.append(f'        from buildzr.themes.base import ThemeElement')
    lines.append(f'        return [v for v in cls.__dict__.values() if isinstance(v, ThemeElement)]')
    lines.append(f'')

    return lines


def generate_module(
    module_name: str,
    class_prefix: str,
    theme_urls: List[str],
    output_dir: Path,
) -> Tuple[str, List[str]]:
    """
    Generate a Python module for a theme (possibly with multiple versions).

    Returns:
        Tuple of (default_alias, list_of_class_names)
    """
    lines = [
        '"""',
        f'{class_prefix.replace("_", " ").title()} theme constants.',
        '',
        'Auto-generated by buildzr.themes.generate - DO NOT EDIT.',
        '"""',
        '',
        'from buildzr.themes.base import ThemeElement',
        '',
        '',
    ]

    class_names = []

    # Sort URLs to have newest versions first (for default alias)
    sorted_urls = sorted(theme_urls, reverse=True)

    for url in sorted_urls:
        print(f'  Fetching: {url}')
        theme_data = fetch_theme(url)
        version = extract_version_from_url(url)
        class_name = f'{class_prefix}_{version}'
        class_names.append(class_name)

        class_lines = generate_theme_class(class_name, url, theme_data)
        lines.extend(class_lines)
        lines.append('')

    # Add default alias (first class = newest version)
    if class_names:
        default_alias = class_prefix
        lines.append(f'# Default alias - latest version')
        lines.append(f'{default_alias} = {class_names[0]}')
        lines.append('')

    output_file = output_dir / f'{module_name}.py'
    output_file.write_text('\n'.join(lines))
    print(f'  Generated: {output_file}')

    return class_prefix, class_names


def generate_init(
    output_dir: Path,
    modules: Dict[str, Tuple[str, List[str]]],
) -> None:
    """Generate __init__.py for the generated package."""
    lines = [
        '"""',
        'Auto-generated theme modules.',
        '',
        'DO NOT EDIT - generated by buildzr.themes.generate',
        '"""',
        '',
    ]

    # Import default aliases
    for module_name, (default_alias, class_names) in sorted(modules.items()):
        lines.append(f'from .{module_name} import {default_alias}')

    lines.append('')

    # Import version-specific classes
    for module_name, (default_alias, class_names) in sorted(modules.items()):
        if len(class_names) > 1:
            classes_str = ', '.join(class_names)
            lines.append(f'from .{module_name} import {classes_str}')

    lines.append('')

    # __all__ export
    all_exports = []
    for module_name, (default_alias, class_names) in sorted(modules.items()):
        all_exports.append(default_alias)
        all_exports.extend(class_names)

    lines.append('__all__ = [')
    for export in all_exports:
        lines.append(f'    "{export}",')
    lines.append(']')
    lines.append('')

    output_file = output_dir / '__init__.py'
    output_file.write_text('\n'.join(lines))
    print(f'Generated: {output_file}')


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Generate Python theme modules from Structurizr theme JSON files.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        'urls',
        nargs='*',
        help='Theme JSON URLs to process',
    )
    parser.add_argument(
        '--urls-file',
        type=Path,
        help='File containing theme URLs (one per line)',
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path(__file__).parent / 'generated',
        help='Output directory for generated files (default: buildzr/themes/generated)',
    )

    args = parser.parse_args()

    # Collect URLs from all sources
    urls: List[str] = list(args.urls)

    if args.urls_file:
        if not args.urls_file.exists():
            print(f'Error: URLs file not found: {args.urls_file}', file=sys.stderr)
            sys.exit(1)

        with open(args.urls_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    urls.append(line)

    if not urls:
        print('Error: No URLs provided. Use positional arguments or --urls-file.', file=sys.stderr)
        sys.exit(1)

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Group URLs by theme name (for multi-version support)
    theme_groups: Dict[str, List[str]] = defaultdict(list)

    print('Fetching theme metadata...')
    for url in urls:
        try:
            theme_data = fetch_theme(url)
            theme_name = theme_data.get('name', 'Unknown')
            module_name = theme_name_to_module_name(theme_name)
            theme_groups[module_name].append(url)
            print(f'  {theme_name} -> {module_name}.py')
        except Exception as e:
            print(f'Warning: Failed to fetch {url}: {e}', file=sys.stderr)

    # Generate modules
    print('\nGenerating modules...')
    modules: Dict[str, Tuple[str, List[str]]] = {}

    for module_name, theme_urls in sorted(theme_groups.items()):
        # Get class prefix from first URL's theme name
        theme_data = fetch_theme(theme_urls[0])
        theme_name = theme_data.get('name', 'Unknown')
        class_prefix = theme_name_to_class_prefix(theme_name)

        print(f'\n{module_name}.py:')
        default_alias, class_names = generate_module(
            module_name,
            class_prefix,
            theme_urls,
            args.output_dir,
        )
        modules[module_name] = (default_alias, class_names)

    # Generate __init__.py
    print('\nGenerating __init__.py...')
    generate_init(args.output_dir, modules)

    print('\nDone!')


if __name__ == '__main__':
    main()
