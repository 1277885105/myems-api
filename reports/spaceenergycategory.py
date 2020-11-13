import falcon
import simplejson as json
import mysql.connector
import config
from datetime import datetime, timedelta, timezone
import utilities
from decimal import *


class Reporting:
    @staticmethod
    def __init__():
        pass

    @staticmethod
    def on_options(req, resp):
        resp.status = falcon.HTTP_200

    ####################################################################################################################
    # PROCEDURES
    # Step 1: valid parameters
    # Step 2: query the space
    # Step 3: query energy categories
    # Step 4: query associated sensors
    # Step 5: query associated points
    # Step 6: query child spaces
    # Step 7: query base period energy input
    # Step 8: query reporting period energy input
    # Step 9: query associated sensors and points data
    # Step 10: query tariff data
    # Step 11: query child spaces energy input
    # Step 12: construct the report
    ####################################################################################################################
    @staticmethod
    def on_get(req, resp):
        print(req.params)
        space_id = req.params.get('spaceid')
        period_type = req.params.get('periodtype')
        base_period_begins_datetime = req.params.get('baseperiodbeginsdatetime')
        base_period_ends_datetime = req.params.get('baseperiodendsdatetime')
        reporting_period_begins_datetime = req.params.get('reportingperiodbeginsdatetime')
        reporting_period_ends_datetime = req.params.get('reportingperiodendsdatetime')

        ################################################################################################################
        # Step 1: valid parameters
        ################################################################################################################
        if space_id is None:
            raise falcon.HTTPError(falcon.HTTP_400, title='API.BAD_REQUEST', description='API.INVALID_SPACE_ID')
        else:
            space_id = str.strip(space_id)
            if not space_id.isdigit() or int(space_id) <= 0:
                raise falcon.HTTPError(falcon.HTTP_400, title='API.BAD_REQUEST', description='API.INVALID_SPACE_ID')

        if period_type is None:
            raise falcon.HTTPError(falcon.HTTP_400, title='API.BAD_REQUEST', description='API.INVALID_PERIOD_TYPE')
        else:
            period_type = str.strip(period_type)
            if period_type not in ['hourly', 'daily', 'monthly', 'yearly']:
                raise falcon.HTTPError(falcon.HTTP_400, title='API.BAD_REQUEST', description='API.INVALID_PERIOD_TYPE')

        timezone_offset = int(config.utc_offset[1:3]) * 60 + int(config.utc_offset[4:6])
        if config.utc_offset[0] == '-':
            timezone_offset = -timezone_offset

        base_start_datetime_utc = None
        if base_period_begins_datetime is not None and len(str.strip(base_period_begins_datetime)) > 0:
            base_period_begins_datetime = str.strip(base_period_begins_datetime)
            try:
                base_start_datetime_utc = datetime.strptime(base_period_begins_datetime, '%Y-%m-%dT%H:%M:%S')
            except ValueError:
                raise falcon.HTTPError(falcon.HTTP_400, title='API.BAD_REQUEST',
                                       description="API.INVALID_BASE_PERIOD_BEGINS_DATETIME")
            base_start_datetime_utc = base_start_datetime_utc.replace(tzinfo=timezone.utc) - \
                timedelta(minutes=timezone_offset)

        base_end_datetime_utc = None
        if base_period_ends_datetime is not None and len(str.strip(base_period_ends_datetime)) > 0:
            base_period_ends_datetime = str.strip(base_period_ends_datetime)
            try:
                base_end_datetime_utc = datetime.strptime(base_period_ends_datetime, '%Y-%m-%dT%H:%M:%S')
            except ValueError:
                raise falcon.HTTPError(falcon.HTTP_400, title='API.BAD_REQUEST',
                                       description="API.INVALID_BASE_PERIOD_ENDS_DATETIME")
            base_end_datetime_utc = base_end_datetime_utc.replace(tzinfo=timezone.utc) - \
                timedelta(minutes=timezone_offset)

        if base_start_datetime_utc is not None and base_end_datetime_utc is not None and \
                base_start_datetime_utc >= base_end_datetime_utc:
            raise falcon.HTTPError(falcon.HTTP_400, title='API.BAD_REQUEST',
                                   description='API.INVALID_BASE_PERIOD_ENDS_DATETIME')

        if reporting_period_begins_datetime is None:
            raise falcon.HTTPError(falcon.HTTP_400, title='API.BAD_REQUEST',
                                   description="API.INVALID_REPORTING_PERIOD_BEGINS_DATETIME")
        else:
            reporting_period_begins_datetime = str.strip(reporting_period_begins_datetime)
            try:
                reporting_start_datetime_utc = datetime.strptime(reporting_period_begins_datetime, '%Y-%m-%dT%H:%M:%S')
            except ValueError:
                raise falcon.HTTPError(falcon.HTTP_400, title='API.BAD_REQUEST',
                                       description="API.INVALID_REPORTING_PERIOD_BEGINS_DATETIME")
            reporting_start_datetime_utc = reporting_start_datetime_utc.replace(tzinfo=timezone.utc) - \
                timedelta(minutes=timezone_offset)

        if reporting_period_ends_datetime is None:
            raise falcon.HTTPError(falcon.HTTP_400, title='API.BAD_REQUEST',
                                   description="API.INVALID_REPORTING_PERIOD_ENDS_DATETIME")
        else:
            reporting_period_ends_datetime = str.strip(reporting_period_ends_datetime)
            try:
                reporting_end_datetime_utc = datetime.strptime(reporting_period_ends_datetime, '%Y-%m-%dT%H:%M:%S')
            except ValueError:
                raise falcon.HTTPError(falcon.HTTP_400, title='API.BAD_REQUEST',
                                       description="API.INVALID_REPORTING_PERIOD_ENDS_DATETIME")
            reporting_end_datetime_utc = reporting_end_datetime_utc.replace(tzinfo=timezone.utc) - \
                timedelta(minutes=timezone_offset)

        if reporting_start_datetime_utc >= reporting_end_datetime_utc:
            raise falcon.HTTPError(falcon.HTTP_400, title='API.BAD_REQUEST',
                                   description='API.INVALID_REPORTING_PERIOD_ENDS_DATETIME')

        ################################################################################################################
        # Step 2: query the space
        ################################################################################################################
        cnx_system = mysql.connector.connect(**config.myems_system_db)
        cursor_system = cnx_system.cursor()

        cnx_energy = mysql.connector.connect(**config.myems_energy_db)
        cursor_energy = cnx_energy.cursor()

        cursor_system.execute(" SELECT id, name, area, cost_center_id "
                              " FROM tbl_spaces "
                              " WHERE id = %s ", (space_id,))
        row_space = cursor_system.fetchone()
        if row_space is None:
            if cursor_system:
                cursor_system.close()
            if cnx_system:
                cnx_system.disconnect()

            if cursor_energy:
                cursor_energy.close()
            if cnx_energy:
                cnx_energy.disconnect()
            raise falcon.HTTPError(falcon.HTTP_404, title='API.NOT_FOUND', description='API.SPACE_NOT_FOUND')

        space = dict()
        space['id'] = row_space[0]
        space['name'] = row_space[1]
        space['area'] = row_space[2]
        space['cost_center_id'] = row_space[3]

        ################################################################################################################
        # Step 3: query energy categories
        ################################################################################################################
        energy_category_set = set()
        # query energy categories in base period
        cursor_energy.execute(" SELECT DISTINCT(energy_category_id) "
                              " FROM tbl_space_input_category_hourly "
                              " WHERE space_id = %s "
                              "     AND start_datetime_utc >= %s "
                              "     AND start_datetime_utc < %s ",
                              (space['id'], base_start_datetime_utc, base_end_datetime_utc))
        rows_energy_categories = cursor_energy.fetchall()
        if rows_energy_categories is not None or len(rows_energy_categories) > 0:
            for row_energy_category in rows_energy_categories:
                energy_category_set.add(row_energy_category[0])

        # query energy categories in reporting period
        cursor_energy.execute(" SELECT DISTINCT(energy_category_id) "
                              " FROM tbl_space_input_category_hourly "
                              " WHERE space_id = %s "
                              "     AND start_datetime_utc >= %s "
                              "     AND start_datetime_utc < %s ",
                              (space['id'], reporting_start_datetime_utc, reporting_end_datetime_utc))
        rows_energy_categories = cursor_energy.fetchall()
        if rows_energy_categories is not None or len(rows_energy_categories) > 0:
            for row_energy_category in rows_energy_categories:
                energy_category_set.add(row_energy_category[0])

        # query all energy categories in base period and reporting period
        cursor_system.execute(" SELECT id, name, unit_of_measure, kgce, kgco2e "
                              " FROM tbl_energy_categories "
                              " ORDER BY id ", )
        rows_energy_categories = cursor_system.fetchall()
        if rows_energy_categories is None or len(rows_energy_categories) == 0:
            if cursor_system:
                cursor_system.close()
            if cnx_system:
                cnx_system.disconnect()

            if cursor_energy:
                cursor_energy.close()
            if cnx_energy:
                cnx_energy.disconnect()
            raise falcon.HTTPError(falcon.HTTP_404,
                                   title='API.NOT_FOUND',
                                   description='API.ENERGY_CATEGORY_NOT_FOUND')
        energy_category_dict = dict()
        for row_energy_category in rows_energy_categories:
            if row_energy_category[0] in energy_category_set:
                energy_category_dict[row_energy_category[0]] = {"name": row_energy_category[1],
                                                                "unit_of_measure": row_energy_category[2],
                                                                "kgce": row_energy_category[3],
                                                                "kgco2e": row_energy_category[4]}

        ################################################################################################################
        # Step 4: query associated sensors
        ################################################################################################################
        point_list = list()
        cursor_system.execute(" SELECT po.id, po.name, po.units, po.object_type  "
                              " FROM tbl_spaces sp, tbl_sensors se, tbl_spaces_sensors spse, "
                              "      tbl_points po, tbl_sensors_points sepo "
                              " WHERE sp.id = %s AND sp.id = spse.space_id AND spse.sensor_id = se.id "
                              "       AND se.id = sepo.sensor_id AND sepo.point_id = po.id "
                              " ORDER BY po.id ", (space['id'], ))
        rows_points = cursor_system.fetchall()
        if rows_points is not None and len(rows_points) > 0:
            for row in rows_points:
                point_list.append({"id": row[0], "name": row[1], "units": row[2], "object_type": row[3]})

        ################################################################################################################
        # Step 5: query associated points
        ################################################################################################################
        cursor_system.execute(" SELECT po.id, po.name, po.units, po.object_type  "
                              " FROM tbl_spaces sp, tbl_spaces_points sppo, tbl_points po "
                              " WHERE sp.id = %s AND sp.id = sppo.space_id AND sppo.point_id = po.id "
                              " ORDER BY po.id ", (space['id'], ))
        rows_points = cursor_system.fetchall()
        if rows_points is not None and len(rows_points) > 0:
            for row in rows_points:
                point_list.append({"id": row[0], "name": row[1], "units": row[2], "object_type": row[3]})

        ################################################################################################################
        # Step 6: query child spaces
        ################################################################################################################
        child_space_list = list()
        cursor_system.execute(" SELECT id, name  "
                              " FROM tbl_spaces "
                              " WHERE parent_space_id = %s "
                              " ORDER BY id ", (space['id'], ))
        rows_child_spaces = cursor_system.fetchall()
        if rows_child_spaces is not None and len(rows_child_spaces) > 0:
            for row in rows_child_spaces:
                child_space_list.append({"id": row[0], "name": row[1]})

        ################################################################################################################
        # Step 7: query base period energy input
        ################################################################################################################
        base = dict()
        if energy_category_set is not None and len(energy_category_set) > 0:
            for energy_category_id in energy_category_set:
                kgce = energy_category_dict[energy_category_id]['kgce']
                kgco2e = energy_category_dict[energy_category_id]['kgco2e']

                base[energy_category_id] = dict()
                base[energy_category_id]['timestamps'] = list()
                base[energy_category_id]['values'] = list()
                base[energy_category_id]['subtotal'] = Decimal(0.0)
                base[energy_category_id]['subtotal_in_kgce'] = Decimal(0.0)
                base[energy_category_id]['subtotal_in_kgco2e'] = Decimal(0.0)

                cursor_energy.execute(" SELECT start_datetime_utc, actual_value "
                                      " FROM tbl_space_input_category_hourly "
                                      " WHERE space_id = %s "
                                      "     AND energy_category_id = %s "
                                      "     AND start_datetime_utc >= %s "
                                      "     AND start_datetime_utc < %s "
                                      " ORDER BY start_datetime_utc ",
                                      (space['id'],
                                       energy_category_id,
                                       base_start_datetime_utc,
                                       base_end_datetime_utc))
                rows_space_hourly = cursor_energy.fetchall()

                rows_space_periodically = utilities.aggregate_hourly_data_by_period(rows_space_hourly,
                                                                                    base_start_datetime_utc,
                                                                                    period_type)
                for row_space_periodically in rows_space_periodically:
                    current_datetime_local = row_space_periodically[0].replace(tzinfo=timezone.utc) + \
                                             timedelta(minutes=timezone_offset)
                    if period_type == 'hourly':
                        current_datetime = current_datetime_local.strftime('%Y-%m-%dT%H:%M:%S')
                    elif period_type == 'daily':
                        current_datetime = current_datetime_local.strftime('%Y-%m-%d')
                    elif period_type == 'monthly':
                        current_datetime = current_datetime_local.strftime('%Y-%m')
                    elif period_type == 'yearly':
                        current_datetime = current_datetime_local.strftime('%Y')

                    actual_value = Decimal(0.0) if row_space_periodically[1] is None else row_space_periodically[1]
                    base[energy_category_id]['timestamps'].append(current_datetime)
                    base[energy_category_id]['values'].append(actual_value)
                    base[energy_category_id]['subtotal'] += actual_value
                    base[energy_category_id]['subtotal_in_kgce'] += actual_value * kgce
                    base[energy_category_id]['subtotal_in_kgco2e'] += actual_value * kgco2e

        ################################################################################################################
        # Step 8: query reporting period energy input
        ################################################################################################################
        reporting = dict()
        if energy_category_set is not None and len(energy_category_set) > 0:
            for energy_category_id in energy_category_set:
                kgce = energy_category_dict[energy_category_id]['kgce']
                kgco2e = energy_category_dict[energy_category_id]['kgco2e']

                reporting[energy_category_id] = dict()
                reporting[energy_category_id]['timestamps'] = list()
                reporting[energy_category_id]['values'] = list()
                reporting[energy_category_id]['subtotal'] = Decimal(0.0)
                reporting[energy_category_id]['subtotal_in_kgce'] = Decimal(0.0)
                reporting[energy_category_id]['subtotal_in_kgco2e'] = Decimal(0.0)

                cursor_energy.execute(" SELECT start_datetime_utc, actual_value "
                                      " FROM tbl_space_input_category_hourly "
                                      " WHERE space_id = %s "
                                      "     AND energy_category_id = %s "
                                      "     AND start_datetime_utc >= %s "
                                      "     AND start_datetime_utc < %s "
                                      " ORDER BY start_datetime_utc ",
                                      (space['id'],
                                       energy_category_id,
                                       reporting_start_datetime_utc,
                                       reporting_end_datetime_utc))
                rows_space_hourly = cursor_energy.fetchall()

                rows_space_periodically = utilities.aggregate_hourly_data_by_period(rows_space_hourly,
                                                                                    reporting_start_datetime_utc,
                                                                                    period_type)
                for row_space_periodically in rows_space_periodically:
                    current_datetime_local = row_space_periodically[0].replace(tzinfo=timezone.utc) + \
                                             timedelta(minutes=timezone_offset)
                    if period_type == 'hourly':
                        current_datetime = current_datetime_local.strftime('%Y-%m-%dT%H:%M:%S')
                    elif period_type == 'daily':
                        current_datetime = current_datetime_local.strftime('%Y-%m-%d')
                    elif period_type == 'monthly':
                        current_datetime = current_datetime_local.strftime('%Y-%m')
                    elif period_type == 'yearly':
                        current_datetime = current_datetime_local.strftime('%Y')

                    actual_value = Decimal(0.0) if row_space_periodically[1] is None else row_space_periodically[1]
                    reporting[energy_category_id]['timestamps'].append(current_datetime)
                    reporting[energy_category_id]['values'].append(actual_value)
                    reporting[energy_category_id]['subtotal'] += actual_value
                    reporting[energy_category_id]['subtotal_in_kgce'] += actual_value * kgce
                    reporting[energy_category_id]['subtotal_in_kgco2e'] += actual_value * kgco2e

        ################################################################################################################
        # Step 9: query tariff data
        ################################################################################################################
        parameters_data = dict()
        parameters_data['names'] = list()
        parameters_data['timestamps'] = list()
        parameters_data['values'] = list()
        if energy_category_set is not None and len(energy_category_set) > 0:
            for energy_category_id in energy_category_set:
                energy_category_tariff_dict = utilities.get_energy_category_tariffs(space['cost_center_id'],
                                                                                    energy_category_id,
                                                                                    reporting_start_datetime_utc,
                                                                                    reporting_end_datetime_utc)
                tariff_timestamp_list = list()
                tariff_value_list = list()
                for k, v in energy_category_tariff_dict.items():
                    # convert k from utc to local
                    k = k + timedelta(minutes=timezone_offset)
                    tariff_timestamp_list.append(k.isoformat()[0:19][0:19])
                    tariff_value_list.append(v)

                parameters_data['names'].append('TARIFF-' + energy_category_dict[energy_category_id]['name'])
                parameters_data['timestamps'].append(tariff_timestamp_list)
                parameters_data['values'].append(tariff_value_list)

        ################################################################################################################
        # Step 10: query associated sensors and points data
        ################################################################################################################

        ################################################################################################################
        # Step 11: query child spaces data
        ################################################################################################################
        child_spaces_data = dict()
        if energy_category_set is not None and len(energy_category_set) > 0:
            for energy_category_id in energy_category_set:
                pass

        ################################################################################################################
        # Step 12: construct the report
        ################################################################################################################
        if cursor_system:
            cursor_system.close()
        if cnx_system:
            cnx_system.disconnect()

        if cursor_energy:
            cursor_energy.close()
        if cnx_energy:
            cnx_energy.disconnect()

        result = dict()

        result['space'] = dict()
        result['space']['name'] = space['name']
        result['space']['area'] = space['area']

        result['base_period'] = dict()
        result['base_period']['names'] = list()
        result['base_period']['units'] = list()
        result['base_period']['timestamps'] = list()
        result['base_period']['values'] = list()
        result['base_period']['subtotals'] = list()
        result['base_period']['subtotals_in_kgce'] = list()
        result['base_period']['subtotals_in_kgco2e'] = list()
        result['base_period']['subtotals_per_unit_area'] = list()
        result['base_period']['total_in_kgce'] = Decimal(0.0)
        result['base_period']['total_in_kgco2e'] = Decimal(0.0)
        if energy_category_set is not None and len(energy_category_set) > 0:
            for energy_category_id in energy_category_set:
                result['base_period']['names'].append(energy_category_dict[energy_category_id]['name'])
                result['base_period']['units'].append(energy_category_dict[energy_category_id]['unit_of_measure'])
                result['base_period']['timestamps'].append(base[energy_category_id]['timestamps'])
                result['base_period']['values'].append(base[energy_category_id]['values'])
                result['base_period']['subtotals'].append(base[energy_category_id]['subtotal'])
                result['base_period']['subtotals_in_kgce'].append(base[energy_category_id]['subtotal_in_kgce'])
                result['base_period']['subtotals_in_kgco2e'].append(base[energy_category_id]['subtotal_in_kgco2e'])
                result['base_period']['total_in_kgce'] += base[energy_category_id]['subtotal_in_kgce']
                result['base_period']['total_in_kgco2e'] += base[energy_category_id]['subtotal_in_kgco2e']

        result['reporting_period'] = dict()
        result['reporting_period']['names'] = list()
        result['reporting_period']['units'] = list()
        result['reporting_period']['timestamps'] = list()
        result['reporting_period']['values'] = list()
        result['reporting_period']['subtotals'] = list()
        result['reporting_period']['subtotals_in_kgce'] = list()
        result['reporting_period']['subtotals_in_kgco2e'] = list()
        result['reporting_period']['subtotals_per_unit_area'] = list()
        result['reporting_period']['increment_rates'] = list()
        result['reporting_period']['total_in_kgce'] = Decimal(0.0)
        result['reporting_period']['total_in_kgco2e'] = Decimal(0.0)
        result['reporting_period']['increment_rate_in_kgce'] = Decimal(0.0)
        result['reporting_period']['increment_rate_in_kgco2e'] = Decimal(0.0)

        if energy_category_set is not None and len(energy_category_set) > 0:
            for energy_category_id in energy_category_set:
                result['reporting_period']['names'].append(energy_category_dict[energy_category_id]['name'])
                result['reporting_period']['units'].append(energy_category_dict[energy_category_id]['unit_of_measure'])
                result['reporting_period']['timestamps'].append(reporting[energy_category_id]['timestamps'])
                result['reporting_period']['values'].append(reporting[energy_category_id]['values'])
                result['reporting_period']['subtotals'].append(reporting[energy_category_id]['subtotal'])
                result['reporting_period']['subtotals_in_kgce'].append(
                    reporting[energy_category_id]['subtotal_in_kgce'])
                result['reporting_period']['subtotals_in_kgco2e'].append(
                    reporting[energy_category_id]['subtotal_in_kgco2e'])
                result['reporting_period']['subtotals_per_unit_area'].append(
                    reporting[energy_category_id]['subtotal'] / space['area'] if space['area'] > 0.0 else None )
                result['reporting_period']['increment_rates'].append(
                    (reporting[energy_category_id]['subtotal'] - base[energy_category_id]['subtotal']) /
                    base[energy_category_id]['subtotal']
                    if base[energy_category_id]['subtotal'] > 0.0 else None)
                result['reporting_period']['total_in_kgce'] += reporting[energy_category_id]['subtotal_in_kgce']
                result['reporting_period']['total_in_kgco2e'] += reporting[energy_category_id]['subtotal_in_kgco2e']

        result['reporting_period']['total_in_kgco2e_per_unit_area'] = \
            result['reporting_period']['total_in_kgce'] / space['area'] if space['area'] > 0.0 else None

        result['reporting_period']['increment_rate_in_kgce'] = \
            (result['reporting_period']['total_in_kgce'] - result['base_period']['total_in_kgce']) / \
            result['base_period']['total_in_kgce'] \
            if result['base_period']['total_in_kgce'] > Decimal(0.0) else None

        result['reporting_period']['total_in_kgce_per_unit_area'] = \
            result['reporting_period']['total_in_kgco2e'] / space['area'] if space['area'] > 0.0 else None

        result['reporting_period']['increment_rate_in_kgco2e'] = \
            (result['reporting_period']['total_in_kgco2e'] - result['base_period']['total_in_kgco2e']) / \
            result['base_period']['total_in_kgco2e'] \
            if result['base_period']['total_in_kgco2e'] > Decimal(0.0) else None

        result['parameters'] = {
            "names": parameters_data['names'],
            "timestamps": parameters_data['timestamps'],
            "values": parameters_data['values']
        }

        # result = {
        #     "energy_categories": {
        #
        #     },
        #     "reporting_period": {
        #         "increment_rate":
        #             (reporting['total_in_category'] - base['total_in_category'])/base['total_in_category']
        #             if base['total_in_category'] > 0 else None,
        #         "total_in_category": reporting['total_in_category'],
        #         "total_in_kgce": reporting['total_in_kgce'],
        #         "total_in_kgco2e": reporting['total_in_kgco2e'],
        #         "timestamps": [reporting['timestamps'],
        #                        reporting['timestamps'],
        #                        reporting['timestamps']],
        #         "values": [reporting['values_in_category'],
        #                    reporting['values_in_kgce'],
        #                    reporting['values_in_kgco2e']],
        #     },
        #     "base_period": {
        #         "total_in_category": base['total_in_category'],
        #         "total_in_kgce": base['total_in_kgce'],
        #         "total_in_kgco2e": base['total_in_kgco2e'],
        #         "timestamps": [base['timestamps'],
        #                        base['timestamps'],
        #                        base['timestamps']],
        #         "values": [base['values_in_category'],
        #                    base['values_in_kgce'],
        #                    base['values_in_kgco2e']],
        #     },
        #     "child_spaces": {
        #         "total_in_category": reporting['total_in_category'],
        #         "total_in_kgce": reporting['total_in_kgce'],
        #         "total_in_kgco2e": reporting['total_in_kgco2e'],
        #         "timestamps": [reporting['timestamps'],
        #                        reporting['timestamps'],
        #                        reporting['timestamps']],
        #         "values": [reporting['values_in_category'],
        #                    reporting['values_in_kgce'],
        #                    reporting['values_in_kgco2e']],
        #     },
        # }

        resp.body = json.dumps(result)
