#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = [
#   "typer",
#   "httpx",
#   "rich",
#   "python-dotenv"
# ]
# ///

import os
import time
import json
from pathlib import Path
from typing import List, Dict, Any

import httpx
import typer
from rich.console import Console
from rich.table import Table
from rich.progress import track
from dotenv import load_dotenv

load_dotenv()

app = typer.Typer()
console = Console()


def read_packages_from_file(file_path: Path) -> List[str]:
    """Read package names from a file, one per line."""
    if not file_path.exists():
        console.print(f"[red]Error: File '{file_path}' not found.[/red]")
        raise typer.Exit(1)
    
    with open(file_path, 'r') as f:
        packages = [line.strip() for line in f if line.strip()]
    
    return packages


def get_package_stats(package_name: str, api_key: str) -> Dict[str, Any]:
    """Fetch package statistics from pepy.tech API."""
    url = f"https://api.pepy.tech/api/v2/projects/{package_name}"
    headers = {"X-API-Key": api_key}
    
    with httpx.Client() as client:
        response = client.get(url, headers=headers)
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            return {"error": f"Package '{package_name}' not found"}
        elif response.status_code == 401:
            return {"error": "Invalid API key"}
        elif response.status_code == 429:
            return {"error": "Rate limit exceeded"}
        else:
            return {"error": f"API error: {response.status_code}"}


def format_number(num: int) -> str:
    """Format large numbers with commas."""
    return f"{num:,}"


def get_recent_downloads(downloads: Dict[str, Dict[str, int]], days: int = 7) -> int:
    """Calculate total downloads for the most recent N days."""
    if not downloads:
        return 0
    
    # Sort dates and get the most recent ones
    sorted_dates = sorted(downloads.keys(), reverse=True)[:days]
    
    total = 0
    for date in sorted_dates:
        daily_downloads = downloads[date]
        total += sum(daily_downloads.values())
    
    return total


@app.command()
def main(
    packages_file: Path = typer.Argument(..., help="Path to file containing package names (one per line)"),
    show_versions: bool = typer.Option(False, "--show-versions", "-v", help="Show available versions for each package"),
    days: int = typer.Option(7, "--days", "-d", help="Number of recent days to show download stats for"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output results as JSON")
):
    """Fetch and display PyPI package download statistics using pepy.tech API."""
    
    # Check for API key
    api_key = os.environ.get("PEPY_API_KEY")
    if not api_key:
        console.print("[red]Error: PEPY_API_KEY environment variable not set.[/red]")
        console.print("Get your API key from: https://pepy.tech/")
        raise typer.Exit(1)
    
    # Read packages
    packages = read_packages_from_file(packages_file)
    
    if not json_output:
        console.print(f"[green]Found {len(packages)} packages to check[/green]\n")
    
    # If JSON output, collect all results
    if json_output:
        results = []
        total_all_time = 0
        total_recent = 0
        
        for package in packages:
            stats = get_package_stats(package, api_key)
            
            if "error" in stats:
                result = {
                    "package": package,
                    "error": stats["error"],
                    "total_downloads": None,
                    f"last_{days}_days": None
                }
            else:
                downloads = stats.get("total_downloads", 0)
                recent = get_recent_downloads(stats.get("downloads", {}), days)
                total_all_time += downloads
                total_recent += recent
                
                result = {
                    "package": package,
                    "total_downloads": downloads,
                    f"last_{days}_days": recent
                }
                if show_versions:
                    result["versions"] = stats.get("versions", [])
            
            results.append(result)
            time.sleep(6.1)  # Rate limiting
        
        output = {
            "packages": results,
            "summary": {
                "total_downloads_all_packages": total_all_time,
                f"total_last_{days}_days_all_packages": total_recent,
                "package_count": len(packages)
            }
        }
        print(json.dumps(output, indent=2))
    else:
        # Create results table for rich display
        table = Table(title="PyPI Package Download Statistics")
        table.add_column("Package", style="cyan", no_wrap=True)
        table.add_column("Total Downloads", justify="right", style="green")
        table.add_column(f"Last {days} Days", justify="right", style="yellow")
        table.add_column("Status", style="dim")
        
        if show_versions:
            table.add_column("Versions", style="magenta")
        
        # Track totals
        total_all_time = 0
        total_recent = 0
        successful_packages = 0
        
        # Fetch stats for each package
        for package in track(packages, description="Fetching package stats..."):
            stats = get_package_stats(package, api_key)
            
            if "error" in stats:
                table.add_row(
                    package,
                    "-",
                    "-",
                    f"[red]{stats['error']}[/red]",
                    "-" if show_versions else None
                )
            else:
                downloads = stats.get("total_downloads", 0)
                recent = get_recent_downloads(stats.get("downloads", {}), days)
                versions = stats.get("versions", [])
                
                total_all_time += downloads
                total_recent += recent
                successful_packages += 1
                
                row = [
                    package,
                    format_number(downloads),
                    format_number(recent),
                    "[green]✓[/green]"
                ]
                
                if show_versions:
                    # Show only the most recent 5 versions
                    version_str = ", ".join(versions[:5])
                    if len(versions) > 5:
                        version_str += f" (+{len(versions) - 5} more)"
                    row.append(version_str)
                
                table.add_row(*row)
            
            # Rate limiting: 10 requests per minute for free tier
            time.sleep(6.1)  # ~9.8 requests per minute to be safe
        
        # Add summary row
        table.add_section()
        table.add_row(
            f"[bold]TOTAL ({successful_packages} packages)[/bold]",
            f"[bold green]{format_number(total_all_time)}[/bold green]",
            f"[bold yellow]{format_number(total_recent)}[/bold yellow]",
            "",
            "" if show_versions else None
        )
        
        console.print(table)


if __name__ == "__main__":
    app()
