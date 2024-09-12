from pathlib import Path

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_ssm as ssm
from constructs import Construct

THIS_DIR = Path(__file__).parent
PING_LAMBDA_CODE_DIR = THIS_DIR / "../../resources/ping_lambda/"


class PingLambdaFunction(Construct):
    def __init__(
        self,
        scope: cdk.Stack,
        construct_id: str,
        lightsail_public_ip: str,
        lightsail_private_ip: str,
        test_ssm_parameter: ssm.StringParameter,
        **kwargs
    ):
        """
        :param lightsail_public_ip: public IP of lightsail instance running nginx on port 80
        :param lightsail_private_ip: private IP of lightsail instance running nginx on port 80
        :param test_ssm_parameter: parameter that this lambda function will attempt to read
        """
        super().__init__(scope, construct_id, **kwargs)

        default_vpc = ec2.Vpc.from_lookup(self, "Default-VPC", vpc_name="Default VPC", region=scope.region)

        self.security_group = ec2.SecurityGroup(
            self,
            "Security-Group-For-Ping-Lambda",
            allow_all_outbound=True,
            vpc=default_vpc,
        )

        self.lambda_ = lambda_.Function(
            self,
            "Ping-Lambda",
            allow_public_subnet=True,
            vpc=default_vpc,
            security_groups=[self.security_group],
            timeout=cdk.Duration.seconds(10),
            memory_size=512,
            runtime=lambda_.Runtime.PYTHON_3_8,
            handler="ping_lambda.handler.lambda_handler",
            code=lambda_.Code.from_asset(
                path=str(PING_LAMBDA_CODE_DIR),
                bundling=cdk.BundlingOptions(
                    image=cdk.DockerImage.from_registry(image="lambci/lambda:build-python3.8"),
                    command=[
                        "bash",
                        "-c",
                        "mkdir -p /asset-output"
                        + "&& pip install . -t /asset-output"
                        + "&& rm -rf /asset-output/boto3 /asset-output/botocore",
                    ],
                ),
            ),
            environment={
                "LIGHTSAIL_PUBLIC_IP": lightsail_public_ip,
                "LIGHTSAIL_PRIVATE_IP": lightsail_private_ip,
                "SSM_PARAM_NAME": test_ssm_parameter.parameter_name,
            },
        )

        test_ssm_parameter.grant_read(self.lambda_)
