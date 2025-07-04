import requests
from math import ceil
from sqlalchemy.sql.expression import case
from vr.vulns import vulns
from vr.admin.functions import _auth_user, _entity_permissions_filter, _entity_page_permissions_filter
from sqlalchemy import text, func
from flask import render_template, session, redirect, url_for, request
from flask_login import login_required
from vr.assets.model.businessapplications import BusinessApplications, MakeBusinessApplicationsSchema, BusinessApplicationsSchema
from vr.vulns.model.vulnerabilities import Vulnerabilities, VulnerabilitiesSchema
from vr.vulns.model.vulnerabilityscans import VulnerabilityScans, VulnerabilityScansSchema
from vr.functions.table_functions import load_table, update_table
from requests.auth import HTTPBasicAuth
from vr.assets.model.applicationprofiles import ApplicationProfiles, ApplicationProfilesSchema
from vr import app


NAV = {
    'CAT': { "name": "Testing", "url": "sourcecode.dashboard"}
}

@vulns.route("/vulnerability_scans/<id>", methods=['GET', 'POST'])
@login_required
def vulnerability_scans(id):
    try:
        NAV['curpage'] = {"name": "Vulnerability Scans"}
        admin_role = 'Application Admin'
        role_req = ['Application Admin', 'Application Viewer']
        perm_entity = 'Application'
        user, status, user_roles = _auth_user(session, NAV['CAT']['name'], role_requirements=role_req,
                                              permissions_entity=perm_entity)
        status = _entity_page_permissions_filter(id, user_roles, session, admin_role)

        if status == 401:
            return redirect(url_for('admin.login'))
        elif status == 403:
            return render_template('403.html', user=user, NAV=NAV)

        key = 'VulnerabilityScans.ApplicationId'
        filter_list = f"{key} = :application_id"
        new_dict = {
            'db_name': 'VulnerabilityScans',
            "sort_field": "ID"
        }
        if request.method == 'POST':
            # sort
            page, per_page, orderby_dict, orderby = update_table(request, new_dict)
            allowed_columns = ["ID", "ScanName", "ScanType", "ScanTargets", "ScanStartDate", "issue_cnt", "open_issue_cnt", "closed_issue_cnt", "ra_issue_cnt"]
            allowed_directions = ["asc", "desc"]
            if orderby_dict.get("column") in allowed_columns and orderby_dict.get("direction") in allowed_directions:
                column = getattr(VulnerabilityScans, orderby_dict['column'], None)
                direction = orderby_dict['direction']
                orderby = column.asc() if direction == "asc" else column.desc()
            else:
                orderby = VulnerabilityScans.ID.asc()  # Default order
        else:
            page, per_page, orderby_dict, orderby = load_table(new_dict)

        vuln_all = VulnerabilityScans.query \
            .with_entities(VulnerabilityScans.ID, VulnerabilityScans.ScanName, VulnerabilityScans.ScanType,
                           VulnerabilityScans.ScanTargets, VulnerabilityScans.ScanStartDate,
                           func.count(Vulnerabilities.VulnerabilityID).label('issue_cnt'),
                           func.sum(case((Vulnerabilities.Status.like("Open-%"), 1), else_=0)).label('open_issue_cnt'),
                           func.sum(case((Vulnerabilities.Status.like("Closed-%"), 1), else_=0)).label('closed_issue_cnt'),
                           func.sum(case((Vulnerabilities.Status.like("Open-RiskAccepted%"), 1), else_=0)).label('ra_issue_cnt')
                           ) \
            .join(Vulnerabilities, Vulnerabilities.InitialScanId == VulnerabilityScans.ID, isouter=True) \
            .group_by(VulnerabilityScans.ID) \
            .filter(text(filter_list).params(application_id=id)) \
            .order_by(orderby) \
            .yield_per(per_page) \
            .paginate(page=page, per_page=per_page, error_out=False)
        pg_cnt = ceil((vuln_all.total / per_page))
        schema = VulnerabilityScansSchema(many=True)
        assets = schema.dump(vuln_all.items)

        NAV['appbar'] = 'scans'
        app = BusinessApplications.query.filter(text('ID = :id').params(id=id)).first()
        app_data = {'ID': id, 'ApplicationName': app.ApplicationName, 'Component': app.ApplicationAcronym}
        table_details = {
            "pg_cnt": pg_cnt,
            "page": int(page),
            "item_tot": vuln_all.total,
            "per_page": per_page,
            "orderby": orderby,
            "rec_start": (int(page) - 1) * per_page + 1 if int(page) != 1 else 1,
            "rec_end": int(page) * per_page if (int(page) * per_page) < vuln_all.total else vuln_all.total
        }
        return render_template('vulns/vulnerability_scans.html',  entities=assets, app_data=app_data, user=user, NAV=NAV,
                               table_details= table_details)
    except RuntimeError:
        return render_template('500.html'), 500


@vulns.route("/on_demand_testing", methods=['POST'])
@login_required
def on_demand_testing():
    NAV['curpage'] = {"name": "Vulnerability Scans"}
    admin_role = 'Application Admin'
    role_req = ['Application Admin', 'Application Viewer']
    perm_entity = 'Application'
    user, status, user_roles = _auth_user(session, NAV['CAT']['name'], role_requirements=role_req,
                                          permissions_entity=perm_entity)
    status = _entity_page_permissions_filter(id, user_roles, session, admin_role)

    if status == 401:
        return redirect(url_for('admin.login'))
    elif status == 403:
        return render_template('403.html', user=user, NAV=NAV)

    git_url = request.form.get('gitUrl')
    git_branch = request.form.get('gitBranch')
    app_name = request.form.get('app_name')
    tests = request.form.getlist('tests[]')
    if 'ALL' in tests:
        tests_to_run = 'ALL'
    else:
        tests_to_run = ','.join(tests)

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        'token': app.config['JENKINS_TOKEN'],
        'GIT_URL': git_url,
        'TESTS': tests_to_run.upper(),
        'GIT_BRANCH': git_branch,
        'APP_NAME': app_name
    }
    url = f"{app.config['JENKINS_HOST']}/job/{app.config['JENKINS_PROJECT']}/buildWithParameters"
    resp = requests.post(url, headers=headers, data=data, auth=HTTPBasicAuth(app.config['JENKINS_USER'], app.config['JENKINS_KEY']))

    return redirect(request.referrer)

@vulns.route("/opensource_testing")
@login_required
def opensource_testing():
    try:
        NAV['curpage'] = {"name": "Open Source Testing"}
        user, status, user_roles = _auth_user(session, 'No Role')
        if status == 401:
            return redirect(url_for('admin.login'))
        elif status == 403:
            return render_template('403.html', user=user, NAV=NAV)

        return render_template('testing/opensource_testing.html', user=user, NAV=NAV)
    except RuntimeError:
        return render_template('500.html'), 500



@vulns.route("/start_opensource_testing", methods=['POST'])
@login_required
def start_opensource_testing():
    NAV['curpage'] = {"name": "Vulnerability Scans"}
    admin_role = 'Application Admin'
    role_req = ['Application Admin', 'Application Viewer']
    perm_entity = 'Application'
    user, status, user_roles = _auth_user(session, NAV['CAT']['name'], role_requirements=role_req,
                                          permissions_entity=perm_entity)
    status = _entity_page_permissions_filter(id, user_roles, session, admin_role)

    if status == 401:
        return redirect(url_for('admin.login'))
    elif status == 403:
        return render_template('403.html', user=user, NAV=NAV)

    git_url = request.form.get('gitUrl')
    git_branch = request.form.get('gitBranch')
    app_name = request.form.get('app_name')

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        'token': app.config['JENKINS_TOKEN'],
        'GIT_URL': git_url,
        'GIT_BRANCH': git_branch,
        'APP_NAME': app_name,
        'PROFILE_APPLICATION': 'Y'
    }
    url = f"{app.config['JENKINS_HOST']}/job/{app.config['JENKINS_PROJECT']}/buildWithParameters"
    resp = requests.post(url, headers=headers, data=data, auth=HTTPBasicAuth(app.config['JENKINS_USER'], app.config['JENKINS_KEY']))

    return redirect(url_for('assets.all_applications'))


@vulns.route("/update_application_profile", methods=['POST'])
@login_required
def update_application_profile():
    NAV['curpage'] = {"name": "Vulnerability Scans"}
    admin_role = 'Application Admin'
    role_req = ['Application Admin', 'Application Viewer']
    perm_entity = 'Application'
    user, status, user_roles = _auth_user(session, NAV['CAT']['name'], role_requirements=role_req,
                                          permissions_entity=perm_entity)
    status = _entity_page_permissions_filter(id, user_roles, session, admin_role)

    if status == 401:
        return redirect(url_for('admin.login'))
    elif status == 403:
        return render_template('403.html', user=user, NAV=NAV)

    git_url = request.form.get('gitUrl')
    git_branch = request.form.get('gitBranch')
    app_name = request.form.get('app_name')
    tests_to_run = 'NONE,'

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        'token': app.config['JENKINS_TOKEN'],
        'GIT_URL': git_url,
        'TESTS': tests_to_run.upper(),
        'GIT_BRANCH': git_branch,
        'APP_NAME': app_name,
        'PROFILE_APPLICATION': 'Y',
        'PROFILE_ONLY': 'Y'
    }
    url = f"{app.config['JENKINS_HOST']}/job/{app.config['JENKINS_PROJECT']}/buildWithParameters"
    resp = requests.post(url, headers=headers, data=data, auth=HTTPBasicAuth(app.config['JENKINS_USER'], app.config['JENKINS_KEY']))

    return redirect(request.referrer)


@vulns.route("/application_profile/<app_id>")
@login_required
def application_profile(app_id):
    try:
        NAV['curpage'] = {"name": "Application Profile"}
        role_req = ['Admin']
        user, status, user_roles = _auth_user(session, NAV['CAT']['name'], role_requirements=role_req)
        if status == 401:
            return redirect(url_for('admin.login'))
        elif status == 403:
            return render_template('403.html', user=user, NAV=NAV)

        assets_all = ApplicationProfiles.query.filter(ApplicationProfiles.AppID==app_id).all()
        schema = ApplicationProfilesSchema(many=True)
        assets = schema.dump(
            filter(lambda t: t.ID != '', assets_all)
        )
        app = BusinessApplications.query.filter(text('ID=:app_id').params(app_id=app_id)).first()
        app_data = {'ID': app_id, 'ApplicationName': app.ApplicationName, 'Component': app.ApplicationAcronym, 'RepoURL': app.RepoURL}
        NAV['appbar'] = 'settings'
        return render_template('vulns/application_profile.html', entities=assets, user=user,
                               NAV=NAV, app_data=app_data)
    except RuntimeError:
        return render_template('500.html'), 500


