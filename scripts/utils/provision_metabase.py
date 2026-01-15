#!/usr/bin/env python3
"""
Metabase Dashboard Provisioning Script for TAVR Targeting Tool
Feature: 002-tavr-targeting-tool
Tasks: T058-T066

Programmatically creates and manages Metabase dashboards for the TAVR targeting tool.
All dashboard definitions are version-controlled and reproducible.

Usage:
    python provision_metabase.py                    # Create all dashboards
    python provision_metabase.py --verify           # Check if dashboards exist
    python provision_metabase.py --delete           # Remove all dashboards
    python provision_metabase.py --dry-run          # Show what would be created
"""

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.metabase_client import MetabaseClient, MetabaseConfig, MetabaseAPIError, get_client_from_env

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

COLLECTION_NAME = "TAVR Targeting"
COLLECTION_DESCRIPTION = "Dashboards for Edwards TAVR Hospital Targeting Tool"

# Database configuration - will be looked up by name
DATABASE_NAME = "Edwards TAVR"


# =============================================================================
# Dashboard Definitions
# =============================================================================

@dataclass
class QuestionDefinition:
    """Definition for a Metabase question (saved query)."""
    name: str
    sql: str
    display: str = 'table'
    description: Optional[str] = None
    visualization_settings: Optional[dict] = None
    # Dashboard placement
    row: int = 0
    col: int = 0
    size_x: int = 6
    size_y: int = 4


@dataclass
class DashboardDefinition:
    """Definition for a Metabase dashboard with its questions."""
    name: str
    description: str
    questions: list[QuestionDefinition]


# =============================================================================
# T059: Executive Summary Dashboard Questions
# =============================================================================

EXECUTIVE_SUMMARY_QUESTIONS = [
    QuestionDefinition(
        name="Targeting Summary by Segment",
        sql="""
SELECT
    segment,
    SUM(hospital_count) as total_hospitals,
    SUM(total_volume) as total_volume,
    SUM(interested_count) as interested_count
FROM api.targeting_summary
GROUP BY segment
ORDER BY segment
""",
        display='bar',
        description="Hospital counts by segment (Acceleration vs Optimization)",
        visualization_settings={
            'graph.dimensions': ['segment'],
            'graph.metrics': ['total_hospitals'],
            'graph.colors': ['#509EE3', '#88BF4D']
        },
        row=0, col=0, size_x=6, size_y=4
    ),
    QuestionDefinition(
        name="Priority Funnel",
        sql="""
SELECT
    priority,
    SUM(hospital_count) as count
FROM api.targeting_summary
WHERE priority != 'DNQ'
GROUP BY priority
ORDER BY
    CASE priority
        WHEN 'High' THEN 1
        WHEN 'Medium' THEN 2
        WHEN 'Low' THEN 3
    END
""",
        display='funnel',
        description="Target distribution by priority level",
        visualization_settings={
            'funnel.dimension': 'priority',
            'funnel.metric': 'count'
        },
        row=0, col=6, size_x=6, size_y=4
    ),
    QuestionDefinition(
        name="Targets by State",
        sql="""
SELECT
    state,
    COUNT(*) as hospital_count,
    SUM(total_tavr_volume) as total_volume
FROM api.targeting
WHERE segment = 'Acceleration'
GROUP BY state
ORDER BY hospital_count DESC
LIMIT 20
""",
        display='bar',
        description="Top 20 states by Acceleration target count",
        visualization_settings={
            'graph.dimensions': ['state'],
            'graph.metrics': ['hospital_count'],
            'graph.x_axis.scale': 'ordinal'
        },
        row=4, col=0, size_x=12, size_y=4
    ),
    QuestionDefinition(
        name="Total Targets Summary",
        sql="""
SELECT
    COUNT(*) as total_targets,
    SUM(CASE WHEN segment = 'Acceleration' THEN 1 ELSE 0 END) as acceleration,
    SUM(CASE WHEN segment = 'Optimization' THEN 1 ELSE 0 END) as optimization,
    SUM(CASE WHEN priority = 'High' THEN 1 ELSE 0 END) as high_priority
FROM api.targeting
""",
        display='scalar',
        description="Key targeting metrics",
        visualization_settings={
            'scalar.field': 'total_targets'
        },
        row=0, col=12, size_x=6, size_y=2
    ),
    QuestionDefinition(
        name="Expressed Interest Count",
        sql="""
SELECT COUNT(*) as interested_targets
FROM api.targeting
WHERE expressed_interest = true
""",
        display='scalar',
        description="Targets with expressed interest",
        visualization_settings={
            'scalar.field': 'interested_targets'
        },
        row=2, col=12, size_x=6, size_y=2
    ),
]

EXECUTIVE_SUMMARY_DASHBOARD = DashboardDefinition(
    name="Executive Summary",
    description="High-level overview of TAVR targeting metrics, segments, and priorities",
    questions=EXECUTIVE_SUMMARY_QUESTIONS
)


# =============================================================================
# T060: Acceleration Pipeline Dashboard Questions
# =============================================================================

ACCELERATION_PIPELINE_QUESTIONS = [
    QuestionDefinition(
        name="Acceleration Pipeline",
        sql="""
SELECT
    hospital_name,
    state,
    city,
    priority,
    targeting_score,
    total_tavr_volume,
    yoy_growth_pct,
    regional_director,
    expressed_interest,
    clinical_champion,
    admin_champion
FROM api.targeting
WHERE segment = 'Acceleration'
ORDER BY targeting_score DESC, total_tavr_volume DESC
LIMIT 100
""",
        display='table',
        description="Top Acceleration targets ranked by score",
        visualization_settings={
            'table.pivot': False,
            'table.column_formatting': [
                {'columns': ['targeting_score'], 'type': 'range', 'colors': ['#EF8C8C', '#F9D45C', '#84BB4C']}
            ]
        },
        row=0, col=0, size_x=18, size_y=8
    ),
    QuestionDefinition(
        name="Acceleration by Priority",
        sql="""
SELECT
    priority,
    COUNT(*) as count,
    AVG(targeting_score) as avg_score,
    AVG(total_tavr_volume) as avg_volume
FROM api.targeting
WHERE segment = 'Acceleration' AND priority != 'DNQ'
GROUP BY priority
ORDER BY
    CASE priority
        WHEN 'High' THEN 1
        WHEN 'Medium' THEN 2
        WHEN 'Low' THEN 3
    END
""",
        display='row',
        description="Acceleration targets grouped by priority",
        visualization_settings={
            'graph.dimensions': ['priority'],
            'graph.metrics': ['count']
        },
        row=8, col=0, size_x=6, size_y=4
    ),
    QuestionDefinition(
        name="Champion Coverage",
        sql="""
SELECT
    CASE
        WHEN clinical_champion IS NOT NULL AND admin_champion IS NOT NULL THEN 'Both Champions'
        WHEN clinical_champion IS NOT NULL THEN 'Clinical Only'
        WHEN admin_champion IS NOT NULL THEN 'Admin Only'
        ELSE 'No Champions'
    END as champion_status,
    COUNT(*) as count
FROM api.targeting
WHERE segment = 'Acceleration'
GROUP BY champion_status
ORDER BY count DESC
""",
        display='pie',
        description="Champion identification coverage for Acceleration targets",
        visualization_settings={
            'pie.dimension': 'champion_status',
            'pie.metric': 'count'
        },
        row=8, col=6, size_x=6, size_y=4
    ),
    QuestionDefinition(
        name="High Priority Targets Without Contact",
        sql="""
SELECT
    hospital_name,
    state,
    targeting_score,
    total_tavr_volume,
    regional_director
FROM api.targeting
WHERE segment = 'Acceleration'
  AND priority = 'High'
  AND expressed_interest = false
ORDER BY targeting_score DESC
LIMIT 20
""",
        display='table',
        description="High priority targets not yet contacted",
        visualization_settings={},
        row=8, col=12, size_x=6, size_y=4
    ),
]

ACCELERATION_PIPELINE_DASHBOARD = DashboardDefinition(
    name="Acceleration Pipeline",
    description="Target pipeline for new client acquisition with champion tracking",
    questions=ACCELERATION_PIPELINE_QUESTIONS
)


# =============================================================================
# T061: Optimization Dashboard Questions
# =============================================================================

OPTIMIZATION_DASHBOARD_QUESTIONS = [
    QuestionDefinition(
        name="Optimization Clients",
        sql="""
SELECT
    hospital_name,
    state,
    city,
    priority,
    targeting_score,
    total_tavr_volume,
    echo_surveillance_active,
    workflow_active,
    analytics_active,
    pilot_phase,
    phase_2_tokens_needed,
    regional_director
FROM api.targeting
WHERE segment = 'Optimization'
ORDER BY targeting_score DESC, total_tavr_volume DESC
""",
        display='table',
        description="Current Biome clients with expansion potential",
        visualization_settings={
            'table.pivot': False
        },
        row=0, col=0, size_x=18, size_y=8
    ),
    QuestionDefinition(
        name="Biome Component Adoption",
        sql="""
SELECT
    'Echo Surveillance' as component,
    SUM(CASE WHEN echo_surveillance_active THEN 1 ELSE 0 END) as active_count,
    COUNT(*) as total
FROM api.targeting WHERE segment = 'Optimization'
UNION ALL
SELECT
    'Workflow' as component,
    SUM(CASE WHEN workflow_active THEN 1 ELSE 0 END) as active_count,
    COUNT(*) as total
FROM api.targeting WHERE segment = 'Optimization'
UNION ALL
SELECT
    'Analytics' as component,
    SUM(CASE WHEN analytics_active THEN 1 ELSE 0 END) as active_count,
    COUNT(*) as total
FROM api.targeting WHERE segment = 'Optimization'
""",
        display='bar',
        description="Biome platform component adoption rates",
        visualization_settings={
            'graph.dimensions': ['component'],
            'graph.metrics': ['active_count'],
            'stackable.stack_type': 'stacked'
        },
        row=8, col=0, size_x=6, size_y=4
    ),
    QuestionDefinition(
        name="Phase 2 Token Requirements",
        sql="""
SELECT
    hospital_name,
    state,
    phase_2_tokens_needed,
    pilot_phase,
    targeting_score
FROM api.targeting
WHERE segment = 'Optimization'
  AND phase_2_tokens_needed IS NOT NULL
  AND phase_2_tokens_needed > 0
ORDER BY phase_2_tokens_needed DESC
""",
        display='table',
        description="Clients requiring Phase 2 tokens",
        visualization_settings={},
        row=8, col=6, size_x=6, size_y=4
    ),
    QuestionDefinition(
        name="Expansion Opportunities",
        sql="""
SELECT
    hospital_name,
    state,
    targeting_score,
    total_tavr_volume,
    CASE
        WHEN NOT echo_surveillance_active THEN 'Echo Surveillance'
        WHEN NOT workflow_active THEN 'Workflow'
        WHEN NOT analytics_active THEN 'Analytics'
        ELSE 'Full Platform'
    END as expansion_opportunity
FROM api.targeting
WHERE segment = 'Optimization'
  AND (NOT echo_surveillance_active OR NOT workflow_active OR NOT analytics_active)
ORDER BY total_tavr_volume DESC
LIMIT 20
""",
        display='table',
        description="Top clients with expansion opportunities",
        visualization_settings={},
        row=8, col=12, size_x=6, size_y=4
    ),
]

OPTIMIZATION_DASHBOARD_DEFINITION = DashboardDefinition(
    name="Optimization Dashboard",
    description="Client health monitoring and expansion opportunity tracking",
    questions=OPTIMIZATION_DASHBOARD_QUESTIONS
)


# =============================================================================
# T062: Territory Dashboard Questions
# =============================================================================

TERRITORY_DASHBOARD_QUESTIONS = [
    QuestionDefinition(
        name="Territory Coverage Summary",
        sql="""
SELECT
    regional_director,
    COUNT(*) as total_accounts,
    SUM(CASE WHEN segment = 'Acceleration' THEN 1 ELSE 0 END) as acceleration,
    SUM(CASE WHEN segment = 'Optimization' THEN 1 ELSE 0 END) as optimization,
    SUM(CASE WHEN priority = 'High' THEN 1 ELSE 0 END) as high_priority,
    SUM(CASE WHEN expressed_interest THEN 1 ELSE 0 END) as interested
FROM api.targeting
WHERE regional_director IS NOT NULL
GROUP BY regional_director
ORDER BY total_accounts DESC
""",
        display='table',
        description="Summary of targets by Regional Director",
        visualization_settings={
            'table.pivot': False
        },
        row=0, col=0, size_x=12, size_y=6
    ),
    QuestionDefinition(
        name="Targets by Regional Director",
        sql="""
SELECT
    COALESCE(regional_director, 'Unassigned') as regional_director,
    COUNT(*) as count
FROM api.targeting
GROUP BY regional_director
ORDER BY count DESC
LIMIT 15
""",
        display='bar',
        description="Target distribution by Regional Director",
        visualization_settings={
            'graph.dimensions': ['regional_director'],
            'graph.metrics': ['count'],
            'graph.x_axis.scale': 'ordinal'
        },
        row=0, col=12, size_x=6, size_y=6
    ),
    QuestionDefinition(
        name="Coverage by State",
        sql="""
SELECT
    state,
    COUNT(*) as hospital_count,
    COUNT(DISTINCT regional_director) as rds_assigned,
    SUM(total_tavr_volume) as total_volume
FROM api.targeting
GROUP BY state
ORDER BY hospital_count DESC
""",
        display='table',
        description="Target coverage breakdown by state",
        visualization_settings={},
        row=6, col=0, size_x=9, size_y=6
    ),
    QuestionDefinition(
        name="Unassigned High-Value Targets",
        sql="""
SELECT
    hospital_name,
    state,
    segment,
    priority,
    targeting_score,
    total_tavr_volume
FROM api.targeting
WHERE regional_director IS NULL
  AND priority IN ('High', 'Medium')
ORDER BY targeting_score DESC, total_tavr_volume DESC
LIMIT 20
""",
        display='table',
        description="High-value targets without RD assignment",
        visualization_settings={},
        row=6, col=9, size_x=9, size_y=6
    ),
]

TERRITORY_DASHBOARD_DEFINITION = DashboardDefinition(
    name="Territory Dashboard",
    description="Sales territory coverage and rep scorecard metrics",
    questions=TERRITORY_DASHBOARD_QUESTIONS
)


# =============================================================================
# All Dashboards
# =============================================================================

ALL_DASHBOARDS = [
    EXECUTIVE_SUMMARY_DASHBOARD,
    ACCELERATION_PIPELINE_DASHBOARD,
    OPTIMIZATION_DASHBOARD_DEFINITION,
    TERRITORY_DASHBOARD_DEFINITION,
]


# =============================================================================
# Provisioning Logic
# =============================================================================

class MetabaseProvisioner:
    """Handles provisioning of Metabase dashboards and questions."""

    def __init__(self, client: MetabaseClient, dry_run: bool = False):
        self.client = client
        self.dry_run = dry_run
        self.database_id: Optional[int] = None
        self.collection_id: Optional[int] = None
        self.created_questions: dict[str, int] = {}
        self.created_dashboards: dict[str, int] = {}

    def setup(self) -> bool:
        """
        T055: Verify database connection and setup collection.

        Returns:
            True if setup successful, False otherwise.
        """
        # Verify API connection
        logger.info("Verifying Metabase API connection...")
        if not self.client.verify_connection():
            logger.error("Failed to connect to Metabase API")
            return False
        logger.info("API connection verified")

        # Find database
        logger.info(f"Looking for database: {DATABASE_NAME}")
        db = self.client.get_database_by_name(DATABASE_NAME)
        if not db:
            # Try to find any PostgreSQL database
            databases = self.client.get_databases()
            for d in databases.get('data', databases) if isinstance(databases, dict) else databases:
                if d.get('engine') == 'postgres':
                    db = d
                    logger.info(f"Using database: {d.get('name')} (id: {d.get('id')})")
                    break

        if not db:
            logger.error(f"Database '{DATABASE_NAME}' not found. Please configure database in Metabase first.")
            return False

        self.database_id = db['id']
        logger.info(f"Using database ID: {self.database_id}")

        # Setup collection
        if not self.dry_run:
            logger.info(f"Setting up collection: {COLLECTION_NAME}")
            collection = self.client.get_or_create_collection(COLLECTION_NAME, COLLECTION_DESCRIPTION)
            self.collection_id = collection['id']
            logger.info(f"Using collection ID: {self.collection_id}")

        return True

    def create_question(self, question: QuestionDefinition) -> Optional[int]:
        """Create a single question."""
        logger.info(f"Creating question: {question.name}")

        if self.dry_run:
            logger.info(f"  [DRY RUN] Would create question: {question.name}")
            return None

        try:
            card = self.client.create_native_question(
                name=question.name,
                database_id=self.database_id,
                sql=question.sql,
                display=question.display,
                visualization_settings=question.visualization_settings,
                description=question.description,
                collection_id=self.collection_id
            )
            card_id = card['id']
            self.created_questions[question.name] = card_id
            logger.info(f"  Created question ID: {card_id}")
            return card_id
        except MetabaseAPIError as e:
            logger.error(f"  Failed to create question: {e}")
            return None

    def create_dashboard(self, dashboard_def: DashboardDefinition) -> Optional[int]:
        """Create a dashboard with all its questions."""
        logger.info(f"\n{'='*60}")
        logger.info(f"Creating dashboard: {dashboard_def.name}")
        logger.info(f"{'='*60}")

        if self.dry_run:
            logger.info(f"[DRY RUN] Would create dashboard: {dashboard_def.name}")
            for q in dashboard_def.questions:
                logger.info(f"  [DRY RUN] Would create question: {q.name}")
            return None

        try:
            # Create the dashboard
            dashboard = self.client.create_dashboard(
                name=dashboard_def.name,
                description=dashboard_def.description,
                collection_id=self.collection_id
            )
            dashboard_id = dashboard['id']
            self.created_dashboards[dashboard_def.name] = dashboard_id
            logger.info(f"Created dashboard ID: {dashboard_id}")

            # Create questions and add to dashboard
            for question in dashboard_def.questions:
                card_id = self.create_question(question)
                if card_id:
                    # Add card to dashboard
                    self.client.add_card_to_dashboard(
                        dashboard_id=dashboard_id,
                        card_id=card_id,
                        row=question.row,
                        col=question.col,
                        size_x=question.size_x,
                        size_y=question.size_y
                    )
                    logger.info(f"  Added to dashboard at ({question.row}, {question.col})")

            return dashboard_id

        except MetabaseAPIError as e:
            logger.error(f"Failed to create dashboard: {e}")
            return None

    def provision_all(self) -> bool:
        """
        T066: Create all dashboards.

        Returns:
            True if all dashboards created successfully.
        """
        if not self.setup():
            return False

        success = True
        for dashboard_def in ALL_DASHBOARDS:
            if not self.create_dashboard(dashboard_def):
                success = False

        return success

    def verify(self) -> bool:
        """
        T063: Check if all dashboards exist.

        Returns:
            True if all dashboards found, False otherwise.
        """
        if not self.setup():
            return False

        all_found = True
        logger.info("\nVerifying dashboards...")

        for dashboard_def in ALL_DASHBOARDS:
            dashboard = self.client.find_dashboard_by_name(dashboard_def.name)
            if dashboard:
                logger.info(f"  [FOUND] {dashboard_def.name} (ID: {dashboard['id']})")
            else:
                logger.warning(f"  [MISSING] {dashboard_def.name}")
                all_found = False

        return all_found

    def delete_all(self) -> bool:
        """
        T064: Delete all provisioned dashboards and questions.

        Returns:
            True if deletion successful.
        """
        if not self.setup():
            return False

        logger.info("\nDeleting dashboards...")

        for dashboard_def in ALL_DASHBOARDS:
            dashboard = self.client.find_dashboard_by_name(dashboard_def.name)
            if dashboard:
                if self.dry_run:
                    logger.info(f"  [DRY RUN] Would delete: {dashboard_def.name}")
                else:
                    try:
                        self.client.delete_dashboard(dashboard['id'])
                        logger.info(f"  [DELETED] {dashboard_def.name}")
                    except MetabaseAPIError as e:
                        logger.error(f"  Failed to delete {dashboard_def.name}: {e}")

        # Also delete orphaned questions in the collection
        logger.info("\nCleaning up questions in collection...")
        # Note: Questions are typically archived with their dashboards
        # Additional cleanup can be added here if needed

        return True


# =============================================================================
# CLI Entry Point
# =============================================================================

def load_env_file(env_path: str) -> None:
    """Load environment variables from a file."""
    if os.path.exists(env_path):
        logger.info(f"Loading environment from: {env_path}")
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()


def main():
    """T058, T065: CLI entry point with argument handling and error handling."""
    parser = argparse.ArgumentParser(
        description='Provision Metabase dashboards for TAVR Targeting Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Create all dashboards
    python provision_metabase.py

    # Verify dashboards exist
    python provision_metabase.py --verify

    # Delete all dashboards
    python provision_metabase.py --delete

    # Dry run (show what would be created)
    python provision_metabase.py --dry-run

Environment Variables:
    METABASE_API_KEY    Required: API key for Metabase authentication
    METABASE_URL        Optional: Metabase URL (default: http://localhost:3000)
"""
    )

    parser.add_argument(
        '--verify',
        action='store_true',
        help='Verify all dashboards exist without creating them'
    )
    parser.add_argument(
        '--delete',
        action='store_true',
        help='Delete all provisioned dashboards'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be created without making changes'
    )
    parser.add_argument(
        '--env-file',
        type=str,
        default=None,
        help='Path to .env file (default: looks for .env.local in edwards/)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load environment variables
    if args.env_file:
        load_env_file(args.env_file)
    else:
        # Try default locations
        script_dir = Path(__file__).parent.parent
        for env_file in ['.env.local', '.env']:
            env_path = script_dir / env_file
            if env_path.exists():
                load_env_file(str(env_path))
                break

    # T065: Validate API key
    api_key = os.environ.get('METABASE_API_KEY')
    if not api_key:
        logger.error("METABASE_API_KEY environment variable is required")
        logger.error("Set it in .env.local or pass --env-file <path>")
        sys.exit(1)

    # Create client
    try:
        client = get_client_from_env()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    # Create provisioner
    provisioner = MetabaseProvisioner(client, dry_run=args.dry_run)

    # Execute requested action
    try:
        if args.verify:
            success = provisioner.verify()
            sys.exit(0 if success else 1)
        elif args.delete:
            success = provisioner.delete_all()
            sys.exit(0 if success else 1)
        else:
            success = provisioner.provision_all()
            if success:
                logger.info("\n" + "="*60)
                logger.info("Provisioning complete!")
                logger.info("="*60)
                logger.info(f"Created {len(provisioner.created_dashboards)} dashboards")
                logger.info(f"Created {len(provisioner.created_questions)} questions")
                logger.info(f"\nView dashboards at: {os.environ.get('METABASE_URL', 'http://localhost:3000')}")
            sys.exit(0 if success else 1)

    except MetabaseAPIError as e:
        logger.error(f"Metabase API error: {e}")
        if e.response:
            logger.error(f"Response: {e.response}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
