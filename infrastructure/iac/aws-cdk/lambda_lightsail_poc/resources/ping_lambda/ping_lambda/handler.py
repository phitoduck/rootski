from os import environ
from typing import Dict

import boto3
import requests
from rich import print
from rich.console import Console
from rich.syntax import Syntax

# if TYPE_CHECKING:
#     from mypy_boto3_ssm import SSMClient
# else:
#     SSMClient = object


def lambda_handler(event, context):

    LIGHTSAIL_PUBLIC_IP = environ["LIGHTSAIL_PUBLIC_IP"]
    LIGHTSAIL_PRIVATE_IP = environ["LIGHTSAIL_PRIVATE_IP"]
    SSM_PARAM_NAME = environ["SSM_PARAM_NAME"]

    # show that we can access AWS systems manager
    try_to_fetch_ssm_parameter(param_name=SSM_PARAM_NAME)

    # show that we can access a public IP address via the internet
    make_request(ip_address=LIGHTSAIL_PUBLIC_IP)

    # show that we can access a private IP via a VPC peer connection
    make_request(ip_address=LIGHTSAIL_PRIVATE_IP)


def print_html(html: str):
    console = Console()
    syntax = Syntax(html, "html")
    console.print(syntax)


def make_request(ip_address: str):
    try:
        print(f"\nMaking a request to the lightsail server at: {ip_address}:80")
        response = requests.get(f"http://{ip_address}", timeout=3)
        print_html(response.text)
    except Exception as e:
        print(e)


def get_ssm_parameter_by_name(name: str) -> Dict[str, str]:
    ssm = boto3.client("ssm")
    response = ssm.get_parameter(
        Name=name,
        WithDecryption=True,
    )

    return response["Parameter"]["Value"]


def try_to_fetch_ssm_parameter(param_name: str):
    try:
        print(f"\nRetrieving the SSM parameter with the following name: '{param_name}'")
        param: str = get_ssm_parameter_by_name(name=param_name)
        print(f"Success! Fetched value: '{param}'")
    except Exception as e:
        print(e)


if __name__ == "__main__":
    environ["LIGHTSAIL_PUBLIC_IP"] = "52.10.247.169"
    environ["LIGHTSAIL_PRIVATE_IP"] = "127.0.0.10"

    environ["AWS_PROFILE"] = "rootski"
    environ["SSM_PARAM_NAME"] = "/ROOTSKI/BACKEND/public-ip"

    lambda_handler({}, {})
