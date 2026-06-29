FROM apache/airflow:3.2.2

# Install dbt + your pipeline dependencies into the Airflow image.
# Runs as the airflow user (pip installs go to the airflow venv).
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt