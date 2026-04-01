"""Thin entry-point alias for dk_data.ingestion.main.

CronJobs that were written before main.py became the canonical CLI use:
  python -m dk_data.ingestion.run --source <source_name>

This module simply delegates to main() so both invocation paths work.
"""

from dk_data.ingestion.main import main

if __name__ == "__main__":
    main()
