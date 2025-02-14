import json
import subprocess
import tempfile

import grafana_api
from grafana_api.grafana_api import GrafanaClientError
from grafana_api.grafana_face import GrafanaFace

from redata import db_operations, settings
from redata.db_operations import metrics_session
from redata.grafana.channel import get_slack_notification_channel
from redata.grafana.home_dashboard import create_home_dashboard
from redata.grafana.source import get_postgres_datasource
from redata.grafana.table_dashboards import get_dashboard_for_table
from redata.models import DataSource
from redata.models.table import Table


def create_source_in_grafana(grafana_api):
    datasource = get_postgres_datasource()
    try:
        source = grafana_api.datasource.get_datasource_by_name(datasource["name"])
    except GrafanaClientError:
        print(grafana_api.datasource.create_datasource(datasource))


def create_notifcation_channels(grafana_api):
    channels = grafana_api.notifications.get_channels()
    if len(channels) == 0 and settings.REDATA_SLACK_NOTIFICATION_URL:
        channel = get_slack_notification_channel()
        print(grafana_api.notifications.create_channel(channel))


def create_dashboard_for_table(grafana_api, db, table):
    data = get_dashboard_for_table(db, table)

    response = grafana_api.dashboard.update_dashboard(
        dashboard={"dashboard": data, "folderID": 0, "overwrite": True}
    )
    print(f"Dashboard for table: {table.table_name} generated:", response)

    return {"table": table, "dashboard": response}


def star_home_dashboard(grafana_api, home_response):
    grafana_api.user.unstar_actual_user_dashboard(home_response["id"])
    # it's a bit hacky, unstaring so that starring doesn't throw an error
    response = grafana_api.user.star_actual_user_dashboard(home_response["id"])
    print(response)
    return response


def create_dashboards():
    grafana_api = GrafanaFace(
        auth=(settings.GF_SECURITY_ADMIN_USER, settings.GF_SECURITY_ADMIN_PASSWORD),
        host=f"{settings.GRAFANA_WEB_HOST}:{settings.GRAFANA_WEB_PORT}",
    )

    create_source_in_grafana(grafana_api)
    create_notifcation_channels(grafana_api)
    dashboards = []

    for db in DataSource.source_dbs():
        monitored_tables = Table.get_monitored_tables(db.name)
        for table in monitored_tables:
            dash_data = create_dashboard_for_table(grafana_api, db, table)
            table.grafana_url = dash_data["dashboard"]["url"]
            dashboards.append(dash_data)

    metrics_session.commit()
    home_response = create_home_dashboard(grafana_api, dashboards)
    star_home_dashboard(grafana_api, home_response)
