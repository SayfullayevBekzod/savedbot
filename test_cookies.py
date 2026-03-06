#!/usr/bin/env python3
"""
Test and monitor cookie management system.
Cookies tizimini test qilish va monitoring qilish uchun.
"""

import os
import sys
import asyncio
from typing import Dict

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.services.antiban import antiban_service


def print_header(title: str):
    """Print formatted header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def check_cookie_files():
    """Check available cookie files."""
    print_header("🔍 COOKIE FILES STATUS")
    
    print("📂 Checking for cookies...\n")
    
    # Check cookies.txt
    if os.path.exists("cookies.txt"):
        size = os.path.getsize("cookies.txt")
        print(f"  ✅ cookies.txt - {size:,} bytes")
    else:
        print(f"  ❌ cookies.txt - NOT FOUND")
    
    # Check cookies/ directory
    if os.path.exists("cookies/"):
        files = [f for f in os.listdir("cookies/") if f.endswith(".txt")]
        if files:
            print(f"\n  ✅ cookies/ directory - {len(files)} file(s):")
            for f in sorted(files):
                path = os.path.join("cookies/", f)
                size = os.path.getsize(path)
                print(f"     - {f} ({size:,} bytes)")
        else:
            print(f"\n  ❌ cookies/ - directory exists but EMPTY")
    else:
        print(f"\n  ❌ cookies/ - directory NOT FOUND")
    
    print()


def show_cookie_manager_status():
    """Show cookie manager status."""
    print_header("📊 COOKIE MANAGER STATUS")
    
    status = antiban_service.get_cookie_status()
    
    print(f"  Total Cookies:    {status['total_cookies']}")
    print(f"  Working Cookies:  {status['working_cookies']} ✅")
    print(f"  Failed Cookies:   {status['failed_cookies']} ❌")
    
    if status['total_cookies'] > 0:
        print(f"\n  📋 Cookie Details:\n")
        for cookie_path, info in status['cookies'].items():
            status_icon = "✅" if not info.get('failed') else "❌"
            print(f"    {status_icon} {cookie_path}")
            print(f"       - Failed: {info.get('failed')}")
            print(f"       - Fail Count: {info.get('fail_count')}")
            if info.get('last_error'):
                print(f"       - Last Error: {info.get('last_error')[:60]}...")
            print()
    else:
        print("\n  ⚠️  NO COOKIES FOUND!")
        print("     Please add cookies.txt or files to cookies/ directory")
    print()


def test_get_cookie():
    """Test getting a random cookie."""
    print_header("🎯 TEST: Get Random Cookie")
    
    cookie = antiban_service.get_random_cookie_file()
    if cookie:
        print(f"  ✅ Got cookie: {cookie}\n")
        return cookie
    else:
        print(f"  ❌ No cookie available!\n")
        return None


def test_mark_cookie_failed(cookie: str):
    """Test marking cookie as failed."""
    if not cookie:
        print_header("⏭️  SKIP: Mark Cookie Failed (no cookie)")
        print("  Skipping because no cookie available\n")
        return
    
    print_header("🔴 TEST: Mark Cookie as Failed")
    
    print(f"  Marking as failed: {cookie}\n")
    antiban_service.mark_cookie_failed(cookie, "Test: Connection timeout")
    
    status = antiban_service.get_cookie_status()
    for path, info in status['cookies'].items():
        if path == cookie:
            print(f"  Status: {'❌ FAILED' if info.get('failed') else '✅ WORKING'}")
            print(f"  Fail Count: {info.get('fail_count')}")
            if info.get('last_error'):
                print(f"  Last Error: {info.get('last_error')}")
    print()


def test_mark_cookie_working(cookie: str):
    """Test marking cookie as working."""
    if not cookie:
        print_header("⏭️  SKIP: Mark Cookie Working (no cookie)")
        print("  Skipping because no cookie available\n")
        return
    
    print_header("🟢 TEST: Mark Cookie as Working")
    
    print(f"  Marking as working: {cookie}\n")
    antiban_service.mark_cookie_working(cookie)
    
    status = antiban_service.get_cookie_status()
    for path, info in status['cookies'].items():
        if path == cookie:
            print(f"  Status: {'❌ FAILED' if info.get('failed') else '✅ WORKING'}")
            print(f"  Fail Count: {info.get('fail_count')}")
    print()


def test_cookie_refresh():
    """Test cookie refresh on new files."""
    print_header("🔄 TEST: Cookie Refresh")
    
    print("  Current cookies loaded:")
    status = antiban_service.get_cookie_status()
    print(f"  Total: {status['total_cookies']}")
    
    print("\n  Note: If you add new cookies.txt or files to cookies/")
    print("        they will be automatically detected on next get_next_cookie() call")
    print()


def generate_test_report():
    """Generate complete test report."""
    print("\n")
    print("╔" + "═"*58 + "╗")
    print("║" + " "*10 + "COOKIE MANAGEMENT SYSTEM - TEST REPORT" + " "*10 + "║")
    print("╚" + "═"*58 + "╝")
    
    # Run all tests
    check_cookie_files()
    show_cookie_manager_status()
    
    cookie = test_get_cookie()
    test_mark_cookie_failed(cookie)
    test_mark_cookie_working(cookie)
    test_cookie_refresh()
    
    # Final status
    print_header("✨ TEST SUMMARY")
    
    status = antiban_service.get_cookie_status()
    
    if status['total_cookies'] == 0:
        print("  ⚠️  WARNING: No cookies found!")
        print("  \n  To use the cookie system, please:")
        print("    1. Create cookies.txt in project root, OR")
        print("    2. Create cookies/ directory and add .txt files there")
        print("\n  Example:")
        print("    d:\\Work\\savedbot\\cookies.txt")
        print("    OR")
        print("    d:\\Work\\savedbot\\cookies\\cookies1.txt")
        print("                      \\cookies2.txt")
    else:
        print(f"  ✅ System Ready!")
        print(f"  \n  {status['working_cookies']} working cookie(s) available")
        if status['failed_cookies'] > 0:
            print(f"  {status['failed_cookies']} failed cookie(s) - will retry later")
    
    print("\n  📖 For more info, read: COOKIE_MANAGEMENT.md")
    print("  🚀 Quick start: COOKIES_QUICK_START.md")
    print()


if __name__ == "__main__":
    try:
        generate_test_report()
    except Exception as e:
        print(f"\n❌ ERROR during testing: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
