#!/usr/bin/env python
"""
CLI tool for administering whiteboard boards.
Usage: python cli.py [command] [options]
"""
import argparse
import json
import os
import sys
import requests
from urllib.parse import urljoin

# Import setup module for token management
try:
    from setup import get_admin_token
    SETUP_AVAILABLE = True
except ImportError:
    SETUP_AVAILABLE = False

# Configuration
DEFAULT_BASE_URL = os.environ.get('WHITEBOARD_URL', 'http://localhost:5050')


def get_api_token():
    """Get the API token from environment or setup config."""
    # 1. Check environment variable first
    env_token = os.environ.get('ADMIN_API_TOKEN')
    if env_token and env_token != 'dev-admin-token-change-in-production':
        return env_token
    
    # 2. Try to get from setup config
    if SETUP_AVAILABLE:
        return get_admin_token()
    
    # 3. Fallback to dev token
    return 'dev-admin-token-change-in-production'


API_TOKEN = get_api_token()


class WhiteboardCLI:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
    
    def _request(self, method: str, endpoint: str, data: dict = None) -> dict:
        """Make an API request."""
        url = urljoin(self.base_url, f'/api{endpoint}')
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                json=data,
                timeout=10
            )
            return {
                'status': response.status_code,
                'data': response.json() if response.text else {}
            }
        except requests.exceptions.ConnectionError:
            return {'status': 0, 'error': f'Cannot connect to {self.base_url}'}
        except Exception as e:
            return {'status': 0, 'error': str(e)}
    
    def list_boards(self) -> None:
        """List all boards."""
        result = self._request('GET', '/boards')
        
        if result.get('error'):
            print(f"Error: {result['error']}")
            return
        
        if result['status'] != 200:
            print(f"Error {result['status']}: {result['data']}")
            return
        
        boards = result['data'].get('boards', [])
        count = result['data'].get('count', 0)
        
        print(f"\nBoards ({count} total)\n" + "=" * 60)
        
        if not boards:
            print("No boards found.")
            return
        
        for b in boards:
            status = "[active]" if b.get('is_active', True) else "[inactive]"
            print(f"\n{status} {b['name']}")
            print(f"   ID:    {b['id']}")
            print(f"   Token: {b['access_token'][:20]}...")
            print(f"   URL:   {self.base_url}/board/{b['access_token']}")
            print(f"   Created: {b['created_at']}")
    
    def create_board(self, name: str) -> None:
        """Create a new board."""
        result = self._request('POST', '/boards', {'name': name})
        
        if result.get('error'):
            print(f"Error: {result['error']}")
            return
        
        if result['status'] != 201:
            print(f"Error {result['status']}: {result['data']}")
            return
        
        board = result['data'].get('board', {})
        url = result['data'].get('url', '')
        
        print(f"\nBoard created successfully!\n" + "=" * 60)
        print(f"   Name:  {board['name']}")
        print(f"   ID:    {board['id']}")
        print(f"   Token: {board['access_token']}")
        print(f"\nAccess URL:\n   {url}")
    
    def get_board(self, board_id: str) -> None:
        """Get board details."""
        result = self._request('GET', f'/boards/{board_id}')
        
        if result.get('error'):
            print(f"Error: {result['error']}")
            return
        
        if result['status'] != 200:
            print(f"Error {result['status']}: {result['data']}")
            return
        
        data = result['data']
        board = data.get('board', {})
        
        print(f"\nBoard Details\n" + "=" * 60)
        print(f"   Name:     {board['name']}")
        print(f"   ID:       {board['id']}")
        print(f"   Token:    {board['access_token']}")
        print(f"   Active:   {'Yes' if board.get('is_active', True) else 'No'}")
        print(f"   Strokes:  {data.get('stroke_count', 0)}")
        print(f"   Images:   {data.get('image_count', 0)}")
        print(f"   Created:  {board['created_at']}")
        print(f"   Updated:  {board['updated_at']}")
        print(f"\nAccess URL:\n   {data.get('url', '')}")
    
    def update_board(self, board_id: str, name: str = None, active: bool = None) -> None:
        """Update a board."""
        data = {}
        if name is not None:
            data['name'] = name
        if active is not None:
            data['is_active'] = active
        
        if not data:
            print("Nothing to update. Use --name or --active/--inactive")
            return
        
        result = self._request('PATCH', f'/boards/{board_id}', data)
        
        if result.get('error'):
            print(f"Error: {result['error']}")
            return
        
        if result['status'] != 200:
            print(f"Error {result['status']}: {result['data']}")
            return
        
        board = result['data'].get('board', {})
        print(f"\nBoard updated!\n" + "=" * 60)
        print(f"   Name:   {board['name']}")
        print(f"   Active: {'Yes' if board.get('is_active', True) else 'No'}")
    
    def delete_board(self, board_id: str, force: bool = False) -> None:
        """Delete a board."""
        if not force:
            confirm = input(f"Delete board {board_id}? This cannot be undone. [y/N]: ")
            if confirm.lower() != 'y':
                print("Cancelled.")
                return
        
        result = self._request('DELETE', f'/boards/{board_id}')
        
        if result.get('error'):
            print(f"Error: {result['error']}")
            return
        
        if result['status'] != 200:
            print(f"Error {result['status']}: {result['data']}")
            return
        
        print(f"Board {board_id} deleted.")
    
    def regenerate_token(self, board_id: str) -> None:
        """Regenerate board access token."""
        confirm = input(f"Regenerate token for {board_id}? Old links will stop working. [y/N]: ")
        if confirm.lower() != 'y':
            print("Cancelled.")
            return
        
        result = self._request('POST', f'/boards/{board_id}/regenerate-token')
        
        if result.get('error'):
            print(f"Error: {result['error']}")
            return
        
        if result['status'] != 200:
            print(f"Error {result['status']}: {result['data']}")
            return
        
        board = result['data'].get('board', {})
        url = result['data'].get('url', '')
        
        print(f"\nToken regenerated!\n" + "=" * 60)
        print(f"   New Token: {board['access_token']}")
        print(f"\nNew Access URL:\n   {url}")
    
    def clear_board(self, board_id: str, force: bool = False) -> None:
        """Clear all strokes and images from a board."""
        if not force:
            confirm = input(f"Clear all content from board {board_id}? [y/N]: ")
            if confirm.lower() != 'y':
                print("Cancelled.")
                return
        
        # Delete strokes
        result = self._request('DELETE', f'/boards/{board_id}/strokes')
        if result['status'] == 200:
            print(f"Deleted {result['data'].get('deleted', 0)} strokes")
        
        # Delete images
        result = self._request('DELETE', f'/boards/{board_id}/images')
        if result['status'] == 200:
            print(f"Deleted {result['data'].get('deleted', 0)} images")


def main():
    parser = argparse.ArgumentParser(
        description='Whiteboard Admin CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli.py list                      List all boards
  python cli.py create "My Board"         Create a new board
  python cli.py get <board_id>            Get board details
  python cli.py update <id> --name "New"  Rename a board
  python cli.py update <id> --inactive    Deactivate a board
  python cli.py delete <board_id>         Delete a board
  python cli.py regen <board_id>          Regenerate access token
  python cli.py clear <board_id>          Clear board content

Environment variables:
  WHITEBOARD_URL     Base URL (default: http://localhost:5050)
  ADMIN_API_TOKEN    API token for authentication
        """
    )
    
    parser.add_argument('--url', '-u', default=DEFAULT_BASE_URL,
                        help='Base URL of the whiteboard server')
    parser.add_argument('--token', '-t', default=API_TOKEN,
                        help='Admin API token')
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # List boards
    subparsers.add_parser('list', aliases=['ls'], help='List all boards')
    
    # Create board
    create_parser = subparsers.add_parser('create', aliases=['new'], help='Create a new board')
    create_parser.add_argument('name', nargs='?', default='Untitled', help='Board name')
    
    # Get board
    get_parser = subparsers.add_parser('get', aliases=['show'], help='Get board details')
    get_parser.add_argument('board_id', help='Board ID')
    
    # Update board
    update_parser = subparsers.add_parser('update', aliases=['edit'], help='Update a board')
    update_parser.add_argument('board_id', help='Board ID')
    update_parser.add_argument('--name', '-n', help='New name')
    update_parser.add_argument('--active', action='store_true', help='Activate board')
    update_parser.add_argument('--inactive', action='store_true', help='Deactivate board')
    
    # Delete board
    delete_parser = subparsers.add_parser('delete', aliases=['rm'], help='Delete a board')
    delete_parser.add_argument('board_id', help='Board ID')
    delete_parser.add_argument('--force', '-f', action='store_true', help='Skip confirmation')
    
    # Regenerate token
    regen_parser = subparsers.add_parser('regen', aliases=['regenerate'], help='Regenerate access token')
    regen_parser.add_argument('board_id', help='Board ID')
    
    # Clear board
    clear_parser = subparsers.add_parser('clear', help='Clear all content from a board')
    clear_parser.add_argument('board_id', help='Board ID')
    clear_parser.add_argument('--force', '-f', action='store_true', help='Skip confirmation')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    cli = WhiteboardCLI(args.url, args.token)
    
    if args.command in ('list', 'ls'):
        cli.list_boards()
    
    elif args.command in ('create', 'new'):
        cli.create_board(args.name)
    
    elif args.command in ('get', 'show'):
        cli.get_board(args.board_id)
    
    elif args.command in ('update', 'edit'):
        active = None
        if args.active:
            active = True
        elif args.inactive:
            active = False
        cli.update_board(args.board_id, name=args.name, active=active)
    
    elif args.command in ('delete', 'rm'):
        cli.delete_board(args.board_id, force=args.force)
    
    elif args.command in ('regen', 'regenerate'):
        cli.regenerate_token(args.board_id)
    
    elif args.command == 'clear':
        cli.clear_board(args.board_id, force=args.force)


if __name__ == '__main__':
    main()
