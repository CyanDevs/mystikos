import argparse
import requests
import re
from urllib3.util.retry import Retry

import datetime

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import ssl

import sqlite3

# Jenkins API implementation solely for fetching info
class JenkinsSession:

    def __init__(self, jenkins_url: str, username:str = None, api_token:str = None, debug=False):

        # Configure retries for http(s) requests
        adapter = requests.adapters.HTTPAdapter(
            max_retries=Retry(
                # Retry total defaults to 12
                total=1,
                status_forcelist=[429, 500, 502, 503, 504],
                method_whitelist=["HEAD", "GET", "OPTIONS"],
                # Binary backoff where timeout = {backoff factor} * (2 ** ({current retries} - 1))
                backoff_factor=2
            )
        )

        # Create request session and mount adapters
        self.http = requests.Session()
        self.http.mount("https://", adapter)
        self.http.mount("http://", adapter)

        # Init params
        self.url = jenkins_url
        self.username = username
        self.api_token = api_token
        self.crumb = None
        self.debug = debug

        # Fetch crumb if authentication needed
        if username and api_token:
            self.crumb = self.fetch_crumb()

    def _return_get(self, url, return_format='json'):
        """ Safely return json from a request """

        print(f'Fetching from {url}')
        if self.username and self.api_token and self.crumb:
            response = self.http.get(
                url = url,
                auth = (self.username, self.api_token),
                headers = {"Jenkins-Crumb": self.crumb}
            )
        else:
            response = self.http.get(url)
        if self.debug:
            print(
                f'GET Request {url}\n'
                f'HTTP {str(response.status_code)}\n'
                f'{response.text}\n'
                f'Received Cookies {str(response.cookies.get_dict())}'
            )
        # Catch errors (429, 500, 502, 503, 504 are already retried)
        response.raise_for_status()

        if return_format == 'json' and response.json():
            return response.json()
        elif return_format == 'text' and response.text:
            return response.text
        else:
            return None

    def fetch_crumb(self):
        """Obtains a user crumb from Jenkins API"""

        url = f'{self.url}/crumbIssuer/api/json'
        print(f'Fetching crumb from {url}')
        crumb_json = self._return_get(url, 'json')
        if crumb_json.get('crumb'):
            return crumb_json.get('crumb')

    def get_description(self):
        """Returns the description from the Jenkins Master"""

        url = f'{self.url}/api/json'
        json = self._return_get(url, 'json')
        if json.get('description'):
            return json.get('description')

    def get_job_info(self, job, options=""):
        """ Returns information about a job """

        url = f"{self.url}/job/{job}/api/json"
        if options:
            url += f"?{options}"
        json = self._return_get(url, 'json')
        return json

    def get_build_log(self, job, job_number):
        """ Returns a build's console text"""

        url = f"{self.url}/job/{job}/{job_number}/consoleText"
        text = self._return_get(url, 'text')
        return text

    def get_build_info(self, job, job_number):
        """ Returns build's JSON info"""

        url = f"{self.url}/job/{job}/{job_number}/api/json"
        json = self._return_get(url, 'json')
        return json

def connect_database(database_file):
    conn = None
    try:
        conn = sqlite3.connect(database_file)
    except sqlite3.Error as e:
        print(e)
    return conn

def generate_report(headers: list, data: list):
    """ Return html report """
    yield '<a href="https://oe-jenkins-dev.westeurope.cloudapp.azure.com/securityRealm/commenceLogin?from=%2F"><font style="font-size:18px;">Login to Jenkins here if you are not already logged in</font></a> '
    yield '<table style="white-space:nowrap; padding:4px;">'
    yield '<tr style="border: 1px solid black;">'
    for header in headers:
        yield f'<td>{header}</td>'
    yield '</tr>'
    yield '<tr>'
    for row in data:
        yield '<tr>'
        for key , value in row.items():
            if key == 'url':
                yield f'<td><a href="{value}">{row.get("name")} #{row.get("number")}</a></td>'
            elif key == 'date':
                continue
            else:
                yield f'<td>{value}</td>'
        yield '</tr>'
    yield '</table>'

def send_email(author, recipient, subject, content, mailtoken):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = author
    msg['To'] = recipient

    # Change FAILURE status to bolded red
    content = re.sub('FAILURE', '<font color="red"><b>FAILURE</b></font>', content)
    # Change ABORTED status to bolded yellow
    content = re.sub('ABORTED', '<font color="yellow"><b>ABORTED</b></font>', content)
    # Change SUCCESS status to green
    content = re.sub('SUCCESS', '<font color="green"><b>SUCCESS</b></font>', content)

    msg.attach(MIMEText(content, 'html'))
    s = smtplib.SMTP(host = 'smtp.office365.com', port = '587', timeout = 60)
    s.ehlo()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS)
    s.starttls(context=context)
    s.login('oeciteam@microsoft.com', mailtoken)
    s.send_message(msg)
    s.quit()

def generator_build_nums_from_date(job_info, date, debug=False):
    """
    Given a Jenkins job json, this generator will yield all build numbers that occurred on that day
    """
    for build in job_info.get('builds', []):
        build_date = datetime.datetime.utcfromtimestamp(build['timestamp']/1000).strftime('%Y-%m-%d')
        if build_date == date:
            yield build['number']
        if debug:
            print(
                f"Found build timestamp of {build['timestamp']}"
                f"which is {build['timestamp']/1000} UTC which is {build_date}."
                f"This matches {build_date == date} to {date}."
            )


def main():

    # Parse Arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('jenkins_url', type=str)
    parser.add_argument('username', type=str)
    parser.add_argument('api_token', type=str)
    parser.add_argument('--job', type=str, dest='job')
    parser.add_argument('--date', type=str, dest='date')
    parser.add_argument('--debug', dest='debug', action='store_true')
    parser.add_argument('--mailtoken', type=str, dest='mailtoken')
    args = parser.parse_args()

    # Initialize other variables
    if args.date:
        date = args.date
    else:
        date = datetime.date.today().strftime('%Y-%m-%d')
    standalone_build_list = []
    log = ""

    # connect database
    conn = connect_database('/home/cyan/python3/reporter.db')
    nightly_db = conn.cursor()

    # Get parent job of the build
    jenkins = JenkinsSession(args.jenkins_url, args.username, args.api_token, args.debug)
    job_info = jenkins.get_job_info(args.job, "tree=builds[fullDisplayName,id,number,timestamp]")
    for match_build in generator_build_nums_from_date(job_info, date, args.debug):
        log += jenkins.get_build_log(args.job, match_build)

    # Use regex to find all standalone builds started by parent job
    re_job_match = re.finditer('Starting building.* (\S+) #(\d+)', log)
    standalone_ignore_list = ['Send-Email']
    if re_job_match:
        for match in re_job_match:
            standalone_build, standalone_build_number = match.group(1, 2)

            # Skip standalone builds that are not tests
            if standalone_build in standalone_ignore_list:
                continue

            # Check database if this standalone build has already been entered, and skip if so
            sql = (f'SELECT name, number, os, vm, result, url, date'
                   f' FROM nightly'
                   f' WHERE name = "{standalone_build}"'
                   f' AND number = {standalone_build_number};')
            nightly_db.execute(sql)
            query = nightly_db.fetchone()
            if query:
                continue

            standalone_build_info = jenkins.get_build_info(f'Mystikos/job/Standalone-Pipelines/job/{standalone_build}', standalone_build_number)

            # Fetch build parameters list
            json_parameters = [x for x in standalone_build_info.get('actions') if x.get('_class') == 'hudson.model.ParametersAction']
            if json_parameters:
                standalone_build_parameters = json_parameters[0].get('parameters')

                # Get build option "Ubuntu Version"
                json_os = [x for x in standalone_build_parameters if x.get('name') == 'UBUNTU_VERSION']
                if json_os:
                    standalone_build_os = json_os[0].get('value', 'N/A')
                else:
                    standalone_build_os = 'N/A'

                # Get build option "VM Generation"
                json_vm = [x for x in standalone_build_parameters if x.get('name') == 'VM_GENERATION']
                if json_vm:
                    standalone_build_vm = json_vm[0].get('value', 'N/A')
                else:
                    standalone_build_vm = 'N/A'

            # Get standalone build logs and extract some basic information
            print(f"Fetching logs from {standalone_build} #{standalone_build_number}")
            build_values = [
                standalone_build, # name
                standalone_build_number, # build_number
                f"Ubuntu {standalone_build_os}", # operating system used
                f"ACC-{standalone_build_vm}", # VM type
                standalone_build_info.get('result'), # Build result
                # Option 1: Classic console text
                # url = f"{args.jenkins_url}/job/Mystikos/job/Standalone-Pipelines/job/{standalone_build}/{standalone_build_number}/console"
                # Option 2: Blue Ocean logs
                f"{args.jenkins_url}/blue/organizations/jenkins/Mystikos%2FStandalone-Pipelines%2F{standalone_build}/detail/{standalone_build}/{standalone_build_number}/pipeline",
                str(date)
            ]

            # Write to DB
            values = '", "'.join(build_values)
            sql = f'INSERT INTO NIGHTLY VALUES ("{values}");'
            if args.debug:
                print(sql)
            nightly_db.execute(sql)

    # Fetch all of date's builds from nightly_db
    sql = (f'SELECT name, number, os, vm, result, url, date'
           f' FROM nightly'
           f' WHERE date = "{date}"'
           f' ORDER BY name, os, vm;')
    if args.debug:
        print(sql)
    for row in nightly_db.execute(sql):
        standalone_build_list.append({
            "name": row[0],
            "number": row[1],
            "os": row[2],
            "vm": row[3],
            "result": row[4],
            "url": row[5],
            "date": row[6]
        })
    
    # HISTORY
    # Dates for last 6 days
    previous_days = []
    for d in range(1,7):
        previous = datetime.datetime.strptime(date, '%Y-%m-%d') - datetime.timedelta(days=d)
        previous_days.append(previous.strftime('%Y-%m-%d'))
    # Fetch history of the 6 previous days
    for build in standalone_build_list:
        for day in previous_days:
            sql = (f'SELECT result'
                   f' FROM nightly'
                   f' WHERE name = \"{build.get("name")}\"'
                   f' AND os = \"{build.get("os")}\"'
                   f' AND vm = \"{build.get("vm")}\"'
                   f' AND date = \"{day}\";')
            nightly_db.execute(sql)
            query = nightly_db.fetchone()
            if query:
                if args.debug:
                    print(build['name'], day, query[0])
                build[day] = query[0]
 
     # Close db connection
    conn.commit()
    conn.close()

    # Compose email
    headers = ['Name', 'Build #', 'Operating System', 'VM Type', 'Result', 'Url']
    headers += previous_days
    content = ('\n'.join(generate_report(headers, standalone_build_list)))

    if args.debug:
        recipients = 'chrisyan@microsoft.com'
    else:
        recipients = 'zhanb@microsoft.com, feliu@microsoft.com, mikbras@microsoft.com, paulall@microsoft.com, radhikaj@microsoft.com, sahaben@microsoft.com, sagoel@microsoft.com, vitikoo@microsoft.com, xuejya@microsoft.com, yunhwan@microsoft.com, zijiewu@microsoft.com, rosan@microsoft.com, chrisyan@microsoft.com'

    send_email(
        'oeciteam@microsoft.com',
        recipients,
        f'Mystikos Nightly Test Report {date}',
        content,
        args.mailtoken
    )

    print(f"Report {date} sent to {recipients}")

if __name__ == '__main__':
    main()
