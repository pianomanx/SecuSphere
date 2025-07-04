from vr import db
from vr.assets import assets
from vr.admin.functions import _auth_user, _entity_permissions_filter, _entity_page_permissions_filter
from vr.admin.functions import db_connection_handler
from flask import render_template, session, redirect, url_for, request
from flask_login import login_required
from vr.assets.model.supportcontacts import SupportContacts, SupportContactsSchema, SupportContactsSchema
from sqlalchemy import text
from vr.functions.table_functions import load_table, update_table
from math import ceil
from vr.assets.model.businessapplications import BusinessApplications
from vr.assets.model.apptosupportcontactassociations import AppToSupportContactAssociations


NAV = {
    'CAT': { "name": "Support", "url": "sourcecode.dashboard"}
}


@assets.route("/contacts/<id>")
@login_required
def contacts(id):
    try:
        NAV['curpage'] = {"name": "Contacts"}
        NAV['subcat'] = ""
        NAV['subsubcat'] = ""
        user, status, user_roles = _auth_user(session, NAV['CAT']['name'])
        if status == 401:
            return redirect(url_for('admin.login'))
        elif status == 403:
            return render_template('403.html', user=user, NAV=NAV)

        key = 'BusinessApplications.ID'
        val = id
        filter_list = f"{key} = :val"

        new_dict = {
            'db_name': 'SupportContacts',
            "sort_field": "ID"
        }

        if request.method == 'POST':
            # sort
            page, per_page, orderby_dict, orderby = update_table(request, new_dict)
        else:
            page, per_page, orderby_dict, orderby = load_table(new_dict)

        # Validate and sanitize the orderby value
        allowed_columns = ["ID", "AddDate", "Assignment", "CUID", "Name", "Email", "Role", "ApplicationName"]
        allowed_directions = ["asc", "desc"]
        orderby_parts = orderby.split()
        if len(orderby_parts) == 2 and orderby_parts[0] in allowed_columns and orderby_parts[1].lower() in allowed_directions:
            order_column = getattr(SupportContacts, orderby_parts[0], None)
            order_direction = orderby_parts[1].lower()
            if order_column and order_direction == "asc":
                sanitized_orderby = order_column.asc()
            elif order_column and order_direction == "desc":
                sanitized_orderby = order_column.desc()
            else:
                sanitized_orderby = SupportContacts.ID.asc()  # Default order
        else:
            sanitized_orderby = SupportContacts.ID.asc()  # Default order

        versions = SupportContacts.query\
            .with_entities(
            SupportContacts.ID,
            AppToSupportContactAssociations.AddDate,
            SupportContacts.Assignment,
            SupportContacts.CUID,
            SupportContacts.Name,
            SupportContacts.Email,
            SupportContacts.Role,

            BusinessApplications.ApplicationName
        ) \
            .join(AppToSupportContactAssociations, AppToSupportContactAssociations.SupportContactID==SupportContacts.ID) \
            .join(BusinessApplications, AppToSupportContactAssociations.ApplicationID == BusinessApplications.ID, isouter=True) \
            .filter(text(filter_list).params(val=val)) \
            .order_by(sanitized_orderby) \
            .yield_per(per_page) \
            .paginate(page=page, per_page=per_page, error_out=False)

        pg_cnt = ceil((versions.total / per_page))
        schema = SupportContactsSchema(many=True)
        assets = schema.dump(versions.items)

        NAV['appbar'] = 'contacts'
        app = BusinessApplications.query.filter(text('ID = :id').params(id=id)).first()
        app_data = {'ID': id, 'ApplicationName': app.ApplicationName, 'Component': app.ApplicationAcronym}

        table_details = {
            "pg_cnt": pg_cnt,
            "page": int(page),
            "item_tot": versions.total,
            "per_page": per_page,
            "orderby": orderby,
            "rec_start": (int(page) - 1) * per_page + 1 if int(page) != 1 else 1,
            "rec_end": int(page) * per_page if (int(page) * per_page) < versions.total else versions.total
        }

        return render_template('assets/contacts.html', app_data=app_data, entities=assets, user=user, NAV=NAV,
                               table_details= table_details)
    except RuntimeError:
        return render_template('500.html'), 500


@assets.route('/add_contact/<appid>', methods=['POST'])
@login_required
def add_contact(appid):
    all = request.form
    role = all['role']
    name = all['name']
    uniqueid = all['uniqueid']
    email = all['email']
    contact = SupportContacts(
        CUID=uniqueid,
        Name=name,
        Email=email,
        Role=role
    )
    db.session.add(contact)
    db_connection_handler(db)
    contact_id = contact.ID
    association = AppToSupportContactAssociations(
        ApplicationID = appid,
        SupportContactID = contact_id
    )
    db.session.add(association)
    db_connection_handler(db)
    return '200', 200


@assets.route('/delete_contact', methods=['POST'])
@login_required
def delete_contact():
    all = request.form
    contact_id = all['contact_id']
    contacts = SupportContacts.query.filter(text("ID=:contact_id")).params(contact_id=contact_id).all()
    for contact in contacts:
        db.session.delete(contact)
    db_connection_handler(db)
    return '200', 200
