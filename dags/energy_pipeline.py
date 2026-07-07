from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

default_args = {
    "owner": "data",
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
}

SCRIPTS = "/opt/airflow/scripts"
DBT_DIR = "/opt/airflow/energy_analytics"
DBT_PROFILES = "/opt/airflow/energy_analytics"

with DAG(
    dag_id="energy_pipeline",
    description="ODRE → Postgres → dbt star schema",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule="@daily",
    catchup=False,
    max_active_runs=1,
    tags=["france-energy", "elt"],
) as dag:

    extract = BashOperator(
        task_id="extract",
        bash_command=f"python {SCRIPTS}/extract.py",
    )

    preprocess = BashOperator(
        task_id="preprocess",
        bash_command=f"python {SCRIPTS}/preprocess.py",
    )

    load = BashOperator(
        task_id="load",
        bash_command=f"python {SCRIPTS}/load.py",
    )

    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=(
            f"cd {DBT_DIR} && "
            f"dbt build --profiles-dir {DBT_PROFILES} --target dev"
        ),
        retries=0,  # dbt failures are deterministic; don't retry
    )

    extract >> preprocess >> load >> dbt_build