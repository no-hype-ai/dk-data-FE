"""
Metabase API Client for TAVR Targeting Tool
Feature: 002-tavr-targeting-tool
Tasks: T054-T057

Provides a reusable client for interacting with the Metabase REST API
to programmatically create and manage dashboards, questions, and database connections.
"""

import os
import logging
from typing import Optional
from dataclasses import dataclass
import requests

logger = logging.getLogger(__name__)


@dataclass
class MetabaseConfig:
    """Configuration for Metabase API connection."""
    base_url: str
    api_key: str
    timeout: int = 30


class MetabaseAPIError(Exception):
    """Exception raised for Metabase API errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, response: Optional[dict] = None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)


class MetabaseClient:
    """
    Client for interacting with Metabase REST API.

    T054: Create Metabase API client module
    T055: Implement database connection verification
    T056: Implement saved question (card) creation helper
    T057: Implement dashboard creation helper
    """

    def __init__(self, config: MetabaseConfig):
        """Initialize the Metabase client with configuration."""
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            'x-api-key': config.api_key,
            'Content-Type': 'application/json'
        })

    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make an authenticated request to the Metabase API."""
        url = f"{self.config.base_url}/api/{endpoint}"
        kwargs.setdefault('timeout', self.config.timeout)

        try:
            response = self.session.request(method, url, **kwargs)

            # Handle non-JSON responses
            if response.status_code == 204:
                return {}

            try:
                data = response.json()
            except ValueError:
                data = {'raw': response.text}

            if not response.ok:
                raise MetabaseAPIError(
                    f"API request failed: {response.status_code}",
                    status_code=response.status_code,
                    response=data
                )

            return data

        except requests.RequestException as e:
            raise MetabaseAPIError(f"Request failed: {e}")

    def get(self, endpoint: str, **kwargs) -> dict:
        """Make a GET request."""
        return self._request('GET', endpoint, **kwargs)

    def post(self, endpoint: str, json: dict = None, **kwargs) -> dict:
        """Make a POST request."""
        return self._request('POST', endpoint, json=json, **kwargs)

    def put(self, endpoint: str, json: dict = None, **kwargs) -> dict:
        """Make a PUT request."""
        return self._request('PUT', endpoint, json=json, **kwargs)

    def delete(self, endpoint: str, **kwargs) -> dict:
        """Make a DELETE request."""
        return self._request('DELETE', endpoint, **kwargs)

    # =========================================================================
    # T055: Database Connection Verification
    # =========================================================================

    def verify_connection(self) -> bool:
        """Verify the API connection is working."""
        try:
            self.get('user/current')
            return True
        except MetabaseAPIError:
            return False

    def get_databases(self) -> list[dict]:
        """Get all configured databases."""
        return self.get('database')

    def get_database_by_name(self, name: str) -> Optional[dict]:
        """Find a database by its display name."""
        databases = self.get_databases()
        for db in databases.get('data', databases):
            if db.get('name') == name:
                return db
        return None

    def get_database_tables(self, database_id: int) -> list[dict]:
        """Get tables/views for a database."""
        metadata = self.get(f'database/{database_id}/metadata')
        return metadata.get('tables', [])

    def get_table_by_name(self, database_id: int, schema: str, table_name: str) -> Optional[dict]:
        """Find a table by schema and name."""
        tables = self.get_database_tables(database_id)
        for table in tables:
            if table.get('schema') == schema and table.get('name') == table_name:
                return table
        return None

    # =========================================================================
    # T056: Saved Question (Card) Creation
    # =========================================================================

    def create_question(
        self,
        name: str,
        database_id: int,
        query: dict,
        display: str = 'table',
        visualization_settings: Optional[dict] = None,
        description: Optional[str] = None,
        collection_id: Optional[int] = None
    ) -> dict:
        """
        Create a saved question (card) in Metabase.

        Args:
            name: Display name for the question
            database_id: ID of the database to query
            query: Native SQL query or structured query dict
            display: Visualization type (table, bar, line, pie, scalar, etc.)
            visualization_settings: Chart configuration
            description: Optional description
            collection_id: Optional collection to save to

        Returns:
            Created card object
        """
        card_data = {
            'name': name,
            'dataset_query': {
                'database': database_id,
                'type': 'native' if isinstance(query, str) else 'query',
            },
            'display': display,
            'visualization_settings': visualization_settings or {}
        }

        if isinstance(query, str):
            card_data['dataset_query']['native'] = {'query': query}
        else:
            card_data['dataset_query']['query'] = query

        if description:
            card_data['description'] = description

        if collection_id:
            card_data['collection_id'] = collection_id

        return self.post('card', json=card_data)

    def create_native_question(
        self,
        name: str,
        database_id: int,
        sql: str,
        display: str = 'table',
        visualization_settings: Optional[dict] = None,
        description: Optional[str] = None,
        collection_id: Optional[int] = None
    ) -> dict:
        """
        Create a question using native SQL.

        Args:
            name: Display name for the question
            database_id: ID of the database to query
            sql: Raw SQL query
            display: Visualization type
            visualization_settings: Chart configuration
            description: Optional description
            collection_id: Optional collection to save to

        Returns:
            Created card object
        """
        card_data = {
            'name': name,
            'dataset_query': {
                'database': database_id,
                'type': 'native',
                'native': {
                    'query': sql
                }
            },
            'display': display,
            'visualization_settings': visualization_settings or {}
        }

        if description:
            card_data['description'] = description

        if collection_id:
            card_data['collection_id'] = collection_id

        return self.post('card', json=card_data)

    def get_question(self, card_id: int) -> dict:
        """Get a question by ID."""
        return self.get(f'card/{card_id}')

    def find_question_by_name(self, name: str, collection_id: Optional[int] = None) -> Optional[dict]:
        """Find a question by name, optionally within a specific collection."""
        params = {'q': name}
        if collection_id:
            params['collection_id'] = collection_id

        results = self.get('card', params=params)
        for card in results if isinstance(results, list) else results.get('data', []):
            if card.get('name') == name:
                return card
        return None

    def delete_question(self, card_id: int) -> None:
        """Delete a question by ID."""
        self.delete(f'card/{card_id}')

    # =========================================================================
    # T057: Dashboard Creation
    # =========================================================================

    def create_dashboard(
        self,
        name: str,
        description: Optional[str] = None,
        collection_id: Optional[int] = None,
        parameters: Optional[list] = None
    ) -> dict:
        """
        Create a new dashboard.

        Args:
            name: Dashboard display name
            description: Optional description
            collection_id: Optional collection to save to
            parameters: Optional dashboard-level parameters/filters

        Returns:
            Created dashboard object
        """
        dashboard_data = {
            'name': name,
        }

        if description:
            dashboard_data['description'] = description

        if collection_id:
            dashboard_data['collection_id'] = collection_id

        if parameters:
            dashboard_data['parameters'] = parameters

        return self.post('dashboard', json=dashboard_data)

    def get_dashboard(self, dashboard_id: int) -> dict:
        """Get a dashboard by ID."""
        return self.get(f'dashboard/{dashboard_id}')

    def find_dashboard_by_name(self, name: str, collection_id: Optional[int] = None) -> Optional[dict]:
        """Find a dashboard by name."""
        # Search in collections
        results = self.get('search', params={'q': name, 'models': 'dashboard'})
        for item in results.get('data', []):
            if item.get('name') == name:
                if collection_id is None or item.get('collection_id') == collection_id:
                    return self.get_dashboard(item['id'])
        return None

    def delete_dashboard(self, dashboard_id: int) -> None:
        """Delete a dashboard by ID."""
        self.delete(f'dashboard/{dashboard_id}')

    def add_card_to_dashboard(
        self,
        dashboard_id: int,
        card_id: int,
        row: int = 0,
        col: int = 0,
        size_x: int = 4,
        size_y: int = 4,
        parameter_mappings: Optional[list] = None
    ) -> dict:
        """
        Add a saved question (card) to a dashboard.

        Uses PUT /api/dashboard/:id with dashcards array (Metabase v0.50+ API).

        Args:
            dashboard_id: Target dashboard ID
            card_id: Question/card ID to add
            row: Row position (0-based)
            col: Column position (0-based)
            size_x: Width in grid units (1-18)
            size_y: Height in grid units
            parameter_mappings: Optional parameter mappings for filters

        Returns:
            Updated dashboard object
        """
        # Get existing dashboard to preserve existing cards
        dashboard = self.get_dashboard(dashboard_id)
        existing_dashcards = dashboard.get('dashcards', [])

        # Build new dashcard entry
        new_dashcard = {
            'id': -1,  # Negative ID signals new card
            'card_id': card_id,
            'row': row,
            'col': col,
            'size_x': size_x,
            'size_y': size_y,
        }

        if parameter_mappings:
            new_dashcard['parameter_mappings'] = parameter_mappings

        # Append to existing dashcards
        updated_dashcards = existing_dashcards + [new_dashcard]

        return self.put(f'dashboard/{dashboard_id}', json={'dashcards': updated_dashcards})

    def add_text_card_to_dashboard(
        self,
        dashboard_id: int,
        text: str,
        row: int = 0,
        col: int = 0,
        size_x: int = 4,
        size_y: int = 1
    ) -> dict:
        """
        Add a text/markdown card to a dashboard.

        Uses PUT /api/dashboard/:id with dashcards array (Metabase v0.50+ API).

        Args:
            dashboard_id: Target dashboard ID
            text: Markdown text content
            row: Row position
            col: Column position
            size_x: Width
            size_y: Height

        Returns:
            Updated dashboard object
        """
        # Get existing dashboard to preserve existing cards
        dashboard = self.get_dashboard(dashboard_id)
        existing_dashcards = dashboard.get('dashcards', [])

        new_dashcard = {
            'id': -1,
            'row': row,
            'col': col,
            'size_x': size_x,
            'size_y': size_y,
            'visualization_settings': {
                'virtual_card': {
                    'name': None,
                    'display': 'text',
                    'visualization_settings': {},
                    'dataset_query': {},
                    'archived': False
                },
                'text': text
            }
        }

        updated_dashcards = existing_dashcards + [new_dashcard]
        return self.put(f'dashboard/{dashboard_id}', json={'dashcards': updated_dashcards})

    # =========================================================================
    # Collection Management
    # =========================================================================

    def create_collection(
        self,
        name: str,
        description: Optional[str] = None,
        parent_id: Optional[int] = None
    ) -> dict:
        """Create a new collection."""
        collection_data = {
            'name': name,
        }

        if description:
            collection_data['description'] = description

        if parent_id:
            collection_data['parent_id'] = parent_id

        return self.post('collection', json=collection_data)

    def find_collection_by_name(self, name: str) -> Optional[dict]:
        """Find a collection by name."""
        collections = self.get('collection')
        for coll in collections:
            if coll.get('name') == name:
                return coll
        return None

    def get_or_create_collection(self, name: str, description: Optional[str] = None) -> dict:
        """Get existing collection or create a new one."""
        existing = self.find_collection_by_name(name)
        if existing:
            return existing
        return self.create_collection(name, description)


def get_client_from_env() -> MetabaseClient:
    """
    Create a MetabaseClient from environment variables.

    Required env vars:
        METABASE_API_KEY: API key for authentication

    Optional env vars:
        METABASE_URL: Base URL (default: http://localhost:3000)
    """
    api_key = os.environ.get('METABASE_API_KEY')
    if not api_key:
        raise ValueError("METABASE_API_KEY environment variable is required")

    base_url = os.environ.get('METABASE_URL', 'http://localhost:3000')

    config = MetabaseConfig(base_url=base_url, api_key=api_key)
    return MetabaseClient(config)
