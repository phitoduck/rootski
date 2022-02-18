import boto3
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from textwrap import dedent

#####################
# --- Constants --- #
#####################

BACKUP_BUCKET = os.environ["BACKUP_BUCKET"]
BACKUP_DIR = Path(os.environ["BACKUP_DIR"])
BACKUP_DB__AWS_ACCESS_KEY_ID = os.environ["BACKUP_DB__AWS_ACCESS_KEY_ID"]
BACKUP_DB__AWS_SECRET_ACCESS_KEY = os.environ["BACKUP_DB__AWS_SECRET_ACCESS_KEY"]
BACKUP_INTERVAL = os.environ["BACKUP_INTERVAL"]
CONNECTION_STRING = "postgresql://{username}:{password}@{host}:{port}/{database}".format(
    username=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
    host=os.environ["POSTGRES_HOST"],
    port=os.environ["POSTGRES_PORT"],
    database=os.environ["POSTGRES_DB"],
)
FILENAME_DATETIME_FORMAT = "rootski-db-%m-%d-%Y_%Hh-%Mm-%Ss.sql.gz"

############################
# --- Helper Functions --- #
############################


def parse_timedelta(time_str):
    """Parse strings of the form "1d12h" or "1h30m" or "70s" into timedelta objects."""
    time_str_regex_pattern = re.compile(
        r"((?P<days>\d+?)d)?((?P<hours>\d+?)h)?((?P<minutes>\d+?)m)?((?P<seconds>\d+?)s)?"
    )

    parts = time_str_regex_pattern.match(time_str)
    if not parts:
        return
    parts = parts.groupdict()
    time_params = {}
    for name, param in parts.items():
        if param:
            time_params[name] = int(param)
    return timedelta(**time_params)


def run_shell_command(command, env_vars):
    """Run a shell command and return the output."""
    process = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True, env=env_vars)
    output, _ = process.communicate()
    print(output.decode("utf-8"))


###################
# --- Backup  --- #
###################


def make_object_name():
    return datetime.now().strftime(FILENAME_DATETIME_FORMAT)


def make_backup_fpath(object_name):
    return BACKUP_DIR / object_name


def create_s3_client():
    """Creates and returns an AWS S3 client for uploading backup to the cloud."""
    sess = boto3.session.Session(
        aws_access_key_id=BACKUP_DB__AWS_ACCESS_KEY_ID,
        aws_secret_access_key=BACKUP_DB__AWS_SECRET_ACCESS_KEY,
    )
    return sess.client("s3")


def create_s3_session():
    """Creates and returns an AWS session for listing and downloading backups in S3."""
    sess = boto3.session.Session(
        aws_access_key_id=BACKUP_DB__AWS_ACCESS_KEY_ID,
        aws_secret_access_key=BACKUP_DB__AWS_SECRET_ACCESS_KEY,
    )
    return sess


def upload_backup_to_s3(s3_client, backup_fpath, backup_bucket_name, backup_object_name):
    """Uploads the backup_fpath file to AWS S3."""
    with open(str(backup_fpath), "rb") as f:
        s3_client.upload_fileobj(f, backup_bucket_name, backup_object_name)


def delete_local_backup_file(backup_fpath):
    """Deletes the local backup file once it has been uplaoded to S3."""
    os.remove(str(backup_fpath))


def backup_database(object_name):
    # make sure the backup directory exists
    db_backup_gzip_fpath = make_backup_fpath(object_name)
    db_backup_gzip_fpath.parent.mkdir(parents=True, exist_ok=True)

    # backup the database
    print("Creating the backup")

    # run the backup command
    backup_cmd = (
        "pg_dumpall --dbname {conn_string} --clean --if-exists | gzip --stdout > {backup_fpath}".format(
            conn_string=CONNECTION_STRING, backup_fpath=db_backup_gzip_fpath
        )
    )
    run_shell_command(backup_cmd, env_vars={"PGPASSWORD": os.environ["POSTGRES_PASSWORD"]})

    # upload the backup to S3
    print("Backing up the database as", object_name, "to S3")
    upload_backup_to_s3(create_s3_client(), db_backup_gzip_fpath, BACKUP_BUCKET, object_name)

    # delete local backup
    delete_local_backup_file(db_backup_gzip_fpath)


def backup_database_on_interval(seconds):
    print("Starting rootski backup daemon. Backups will run every {seconds}".format(seconds=seconds))
    print(
        "Backup interval in seconds is derived from {interval} found in BACKUP_INTERVAL".format(
            interval=BACKUP_INTERVAL
        )
    )
    while True:
        time.sleep(seconds)
        backup_database(make_object_name())


###################
# --- Restore --- #
###################


def download_backup_object(session, backup_bucket_name, backup_obj_name, backup_fpath):
    """Downloads the object_name backup from the backup_bucket_name S3 bucket."""
    s3_client = session.client("s3")
    s3_client.download_file(backup_bucket_name, backup_obj_name, str(backup_fpath))


def list_bucket_objects(session, backup_bucket_name):
    """Returns a list of all objects in the backup_bucket_name S3 bucket."""
    bucket = session.resource("s3").Bucket(backup_bucket_name)
    return [obj.key for obj in bucket.objects.all()]


def get_most_recent_backup_obj_name(session):
    # get a list of all the backup files
    backup_files = list_bucket_objects(session, BACKUP_BUCKET)

    # get the most recent backup file
    get_datetime_from_fpath = lambda fpath: datetime.strptime(fpath, FILENAME_DATETIME_FORMAT)
    most_recent_backup_fpath = max(backup_files, key=get_datetime_from_fpath)

    return most_recent_backup_fpath


def restore_database(backup_obj_name=None):
    """
    (1) drop the database
    (2) re-create it (but totally empty)
    (3) restore from the most recent backup in S3
    """

    pg_env_vars = {"PGPASSWORD": os.environ["POSTGRES_PASSWORD"]}

    print("Dropping database {db_name}".format(db_name=os.environ["POSTGRES_DB"]))
    drop_db_cmd = "dropdb --host={host} --port={port} --username={user} {db_name}".format(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        user=os.environ["POSTGRES_USER"],
        db_name=os.environ["POSTGRES_DB"],
    )
    run_shell_command(drop_db_cmd, env_vars=pg_env_vars)

    time.sleep(30)

    print("Creating empty database {db_name}".format(db_name=os.environ["POSTGRES_DB"]))
    create_db_cmd = "createdb --host={host} --port={port} --username={user} {db_name}".format(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        user=os.environ["POSTGRES_USER"],
        db_name=os.environ["POSTGRES_DB"],
    )
    run_shell_command(create_db_cmd, env_vars=pg_env_vars)

    time.sleep(30)

    # find the most recent backup or verify the specify backup exists
    session = create_s3_session()
    if backup_obj_name is None:
        backup_obj_name = get_most_recent_backup_obj_name(session)
    elif backup_obj_name not in list_bucket_objects(session, BACKUP_BUCKET):
        return False
    backup_fpath = make_backup_fpath(backup_obj_name)

    # download the backup
    download_backup_object(session, BACKUP_BUCKET, backup_obj_name, backup_fpath)

    # restore the database from a backup
    print("Restoring database from", backup_fpath)
    restore_cmd = "gunzip --keep --stdout {backup_fpath} | psql --dbname {conn_string}".format(
        backup_fpath=backup_fpath, conn_string=CONNECTION_STRING
    )
    run_shell_command(restore_cmd, env_vars=pg_env_vars)


######################
# --- Entrypoint --- #
######################


def main():
    print("System args:", sys.argv)
    print("Running database-backup process with subcommand", sys.argv[1])
    if sys.argv[1] == "backup":
        backup_database(make_object_name())
    elif sys.argv[1] == "backup-on-interval":
        backup_interval_seconds = parse_timedelta(BACKUP_INTERVAL).seconds
        backup_database_on_interval(seconds=backup_interval_seconds)
    elif sys.argv[1] == "restore-from-most-recent":
        restore_database()
    elif sys.argv[1] == "restore-from-backup":
        backup_obj_name = sys.argv[2]
        restore_database(backup_obj_name)
    else:
        print(
            dedent(
                """
        USAGE:

            python backup_or_restore.py <COMMAND> [ARGS...]

        ENVIRONMENT VARIABLES:

            BACKUP_DIR: the directory to store backups in

            BACKUP_INTERVAL: the interval to backup the database; can be numbered in
                any combination of hours, minutes, and seconds as long as
                they appear in that order (e.g. "1h30m", "70s", "2h15m")

            # connection details
            POSTGRES_USER
            POSTGRES_PASSWORD
            POSTGRES_HOST
            POSTGRES_PORT
            POSTGRES_DB

        COMMANDS:

            backup                    -- Backup the database to the BACKUP_DIR environment
                                         variable directory

            backup-on-interval        -- Run an immortal process that backs up the database
                                         every BACKUP_INTERVAL (backup behaviour is equivalent to
                                         the "backup" subcommand)

            restore-from-most-recent  -- Restore the database from the most recent backup in the
                                         BACKUP_DIR environment variable directory

            restore-from-backup <backup filename> -- Restore the database from the specified backup file
                                     <backup filename> should be one of the filenames in the BACKUP_DIR
        """
            )
        )


if __name__ == "__main__":
    main()
