__author__ = 'jhajagos'

import sqlalchemy as sa
import json
import os
import datetime
import time
import sys


def generate_date_stamp():
    return time.strftime("%Y%m%d", time.gmtime())

def build_dict_based_on_transaction_id_multi_class_query(rs, fields_of_interest, field_class_name,
                                                         transaction_id_field="transaction_id"):

    """

    Build a dict of lists to encode different classes that repeat. Example we

    test_type,r,d
    test1,45,1
    test1,44,3
    test1,45,1
    test1,44,3

    {"test1": [{"r": 45, "d":1}, {"r": 44, "d":3}], "test2":  [{"r": 21, "d":10, {"r": 25, "d": 4}]}

    The results in the table need to be sorted in a logical way

    :param rs: Query Result iterator
    :param fields_of_interest: Fields that want to be included in the file
    :param field_class_name: Field that we will use to split the results into separate classes
    :param transaction_id_field: The name of the ID field
    :return: None
    """
    l = 0

    results_dict = {}
    last_transaction_id = None
    last_class_name = None
    transaction_id_multi_class_dict = {}
    encounters_with_labs = 0
    multi_class_counts_dict = {}
    multi_class_list = []

    for r in rs:
        transaction_id = r[transaction_id_field]
        class_name = r[field_class_name]

        multi_class_dict = {}

        if last_class_name not in multi_class_counts_dict:
            multi_class_counts_dict[last_class_name] = 1
        else:
            multi_class_counts_dict[last_class_name] += 1

        for field in fields_of_interest:
            if r[field].__class__ == datetime.datetime:
                multi_class_dict[field] = r[field].strftime("%Y-%m-%d %H:%M")
            else:
                multi_class_dict[field] = r[field]

        if last_transaction_id is None:
            cases_to_process = ["start new list"]

        elif (last_transaction_id is not None) and last_transaction_id != transaction_id:
            cases_to_process = ["close last list",  "end transaction", "add current item to list"]

        else:
            if last_class_name != class_name:
                cases_to_process = ["close last list", "add current item to list"]
            else:
                cases_to_process = ["add current item to list"]

        for case_to_process in cases_to_process:

            if case_to_process == "add current item to list":
                multi_class_list += [multi_class_dict]

            elif case_to_process == "close last list":
                transaction_id_multi_class_dict[last_class_name] = multi_class_list
                multi_class_list = []

            elif case_to_process == "end transaction":
                encounters_with_labs += 1
                results_dict[last_transaction_id] = transaction_id_multi_class_dict

                transaction_id_multi_class_dict = {}

            elif cases_to_process == "start new list":
                multi_class_list += [multi_class_dict]

        last_class_name = class_name
        last_transaction_id = transaction_id
        l += 1

    if l > 0:
        transaction_id_multi_class_dict[last_class_name] = multi_class_list
        results_dict[last_transaction_id] = transaction_id_multi_class_dict

    return results_dict


def build_dict_based_on_transaction_id_query(rs, fields_of_interest, transaction_id_field="transaction_id"):
    """

    :param rs:
    :param fields_of_interest:
    :param transaction_id_field:
    :return: transaction_id_dict
    """

    transaction_id_dict = {}

    t = 0
    last_transaction_id = None
    transaction_code_list = []
    for r in rs:

        if t == 0:
            print(r.keys())

        transaction_id = r[transaction_id_field]
        single_dict = {}
        for field in fields_of_interest:
            if r[field].__class__ == datetime.datetime:
                single_dict[field] = r[field].strftime("%Y-%m-%d %H:%M")
            else:
                single_dict[field] = r[field]

        if last_transaction_id is None:
            transaction_code_list += [single_dict]

        elif transaction_id != last_transaction_id:
            transaction_id_dict[last_transaction_id] = transaction_code_list

            transaction_code_list = [single_dict]

        else:
            transaction_code_list += [single_dict]

        last_transaction_id = transaction_id
        t += 1

    if t > 0:
        transaction_id_dict[last_transaction_id] = transaction_code_list

    print("Number of rows read %s" % t)

    return transaction_id_dict


def execute_and_print(connection, query):
    print("Executing query:")
    print('   %s;' % query)
    rs = connection.execute(query)
    return rs


def main_json(mapping_json_name, run_time_json_name):
    with open(mapping_json_name, "r") as f:
        mapping_configuration = json.load(f)

    with open(run_time_json_name, "r") as f:
        runtime_configuration = json.load(f)

    configuration = {"mapping_config": mapping_configuration, "runtime_config": runtime_configuration}

    return main(configuration)


def main(configuration):
    """

    :param configuration:
    :return: None

    Writes out a file
    """

    connection_string = configuration["runtime_config"]["source_db_config"]["connection_string"]

    main_config = configuration["mapping_config"]["main_transactions"]
    runtime_config = configuration["runtime_config"]

    if "output_type" in runtime_config:
        output_type = runtime_config["output_type"]
    else:
        output_type = "json_file"

    if output_type == "json_file":
        results_dict_class = None
        results_dict = {}
    # elif output_type == "mongodb_collection":
    #     from mongodb_dict_like import DictMappingMongo
    #     from pymongo import MongoClient
    #
    #     results_dict_class = 1
    #     mongo_db_config = runtime_config["mongo_db_config"]
    #     mongo_connection_string = mongo_db_config["connection_string"]
    #     database_name = mongo_db_config["database_name"]
    #     collection_name = mongo_db_config["collection_name"]
    #
    #     mongo_client = MongoClient(mongo_connection_string)
    #     results_dict = DictMappingMongo(mongo_client, database_name, collection_name, "transaction_id")

    data_directory = runtime_config["json_file_config"]["data_directory"]
    base_file_name = runtime_config["json_file_config"]["base_file_name"]
    schema = main_config["schema"]

    engine = sa.create_engine(connection_string)
    print("Connecting to database")
    connection = engine.connect()
    print("Connected")

    refresh_transactions_table = runtime_config["source_db_config"]["refresh_transactions_table"]
    if schema is not None:
        main_transaction_table = schema + "." + '"' + main_config["table_name"] + '"' #TODO: Add proper escaping
    else:
        main_transaction_table = main_config["table_name"]

    main_transaction_query = 'select * from %s' % main_transaction_table

    if "where_criteria" in main_config and main_config["where_criteria"] is not None:
        main_transaction_query += " where %s" % main_config["where_criteria"]

    if "fields_to_order_by" in main_config and main_config["fields_to_order_by"] is not None:
        main_transaction_query += " order by"
        for field in main_config["fields_to_order_by"]:
            main_transaction_query += ' "%s",' % field

        main_transaction_query = main_transaction_query[:-1]

    transaction_id_field = main_config["transaction_id"]

    if "limit" in main_config and main_config["limit"] is not None:
        main_transaction_query += " limit %s" % main_config["limit"]

    query_count = '''select count(*) as counter from (%s) zzz'''
    rs = execute_and_print(connection, query_count % main_transaction_query)
    record_count = list(rs)[0][0]
    print(record_count)

    rs = execute_and_print(connection, main_transaction_query)
    print("Converting results")

    i = 0
    transactions_of_interest = []
    for r in rs:
        transaction_id = r[transaction_id_field]
        transactions_of_interest += [transaction_id]
        i += 1

    if schema is not None:
        transactions_of_interest_table = "%s.tmp_transactions_of_interest" % schema
    else:
        transactions_of_interest_table = "tmp_transactions_of_interest"

    drop_table_if_exists = "drop table if exists %s" % transactions_of_interest_table
    create_table_sql = "create table %s" % transactions_of_interest_table
    create_table_sql += " (transaction_id int8)" #TODO: Get transaction id in correct format

    if refresh_transactions_table:
        execute_and_print(connection, drop_table_if_exists)
        execute_and_print(connection, create_table_sql)

        i = 0
        for transaction_id in transactions_of_interest:
            insert_query = 'insert into %s values (%s)' % (transactions_of_interest_table, transaction_id)
            connection.execute(insert_query)

            i += 1
            if i % 1000 == 0:
                print("inserted %s records" % i)

        print("inserted %s records" % i)
        index_query = "create unique index idx_tmp_toi on %s(transaction_id)" % transactions_of_interest_table
        execute_and_print(connection, index_query)

    print("Extracting features")
    query_wrapper = 'select zzz.* from (%s) zzz join %s yyy on zzz."' + transaction_id_field + '"' +' = yyy.transaction_id'

    mappings = configuration["mapping_config"]["mappings"]

    for transaction_id in transactions_of_interest:
        transaction_dict = {}
        for mapping in mappings:
            current_dict = transaction_dict
            for part in mapping["path"]:
                if part in current_dict:
                    pass
                else:
                    current_dict[part] = {}

                current_dict = current_dict[part]
            current_dict[mapping["name"]] = None
        results_dict[transaction_id] = transaction_dict

    for mapping in mappings:
        if schema is not None:
            mapping_table_name = schema + "." + '"%s"' % mapping["table_name"]
        else:
            mapping_table_name = '"%s"' % mapping["table_name"]

        mapping_query = "select * from %s" % mapping_table_name
        if "fields_to_order_by" in mapping and mapping["fields_to_order_by"] is not None:
            mapping_query += " order by "
            for field in mapping["fields_to_order_by"]:
                mapping_query += ' "%s",' % field
            mapping_query = mapping_query[:-1]

        rs = execute_and_print(connection, query_wrapper % (mapping_query, transactions_of_interest_table))

        if mapping["type"] in ["one-to-one", "one-to-many"]:
            mapping_result_dict = build_dict_based_on_transaction_id_query(rs, mapping["fields_to_include"], transaction_id_field)
        else:
            mapping_result_dict = build_dict_based_on_transaction_id_multi_class_query(rs, mapping["fields_to_include"], mapping["group_by_field"], transaction_id_field)

        for transaction_id in mapping_result_dict:
            result_dict_to_align = mapping_result_dict[transaction_id]

            if mapping["type"] == "one-to-one":
                 result_dict_to_align = mapping_result_dict[transaction_id][0]
            else:
                 result_dict_to_align = mapping_result_dict[transaction_id]
            # Align to other transactions
            if transaction_id in results_dict:
                result_dict = results_dict[transaction_id]
                current_dict = result_dict
                for path in mapping["path"]:
                    current_dict = current_dict[path]

                current_dict[mapping["name"]] = result_dict_to_align

    #Write out order of keys
    output_key_order_file_name = os.path.join(data_directory, base_file_name + "_" + "key_order_" + generate_date_stamp() + ".json")
    transactions_of_interest_str = [str(x) for x in transactions_of_interest]
    print("")
    print('Writing key order: "%s"' % output_key_order_file_name)
    with open(output_key_order_file_name, "w") as fw:
        json.dump(transactions_of_interest_str, fw, indent=4, separators=(',', ': '))

    #Write dictionary out
    if results_dict_class is None:
        output_file_name = os.path.join(data_directory, base_file_name + "_" + generate_date_stamp() + ".json")
        print('Writing JSON file "%s"' % output_file_name)
        with open(output_file_name, "w") as fw:
            json.dump(results_dict, fw, sort_keys=True, indent=4, separators=(',', ': '))

        return output_file_name, output_key_order_file_name

if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("Usage: python build_document_mapping_from_db.py inpatient_config.json runtime_config.json")
    else:
        main_json(sys.argv[1], sys.argv[2])